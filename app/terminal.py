"""PTY-based terminal management for interactive Claude sessions."""

import atexit
import fcntl
import os
import pty
import select
import signal
import struct
import termios
import threading
import time
import uuid

MAX_SCROLLBACK = 100_000  # bytes


class Terminal:
    """A single PTY-backed terminal process."""

    def __init__(self, tid, cmd, cwd=None, label=""):
        self.id = tid
        self.label = label
        self.cwd = cwd or os.path.expanduser("~")
        self.created_at = time.time()
        self.pid = None
        self.fd = None
        self.alive = False
        self.scrollback = b""
        self._lock = threading.Lock()
        self._start(cmd)

    def _start(self, cmd):
        env = os.environ.copy()
        env["TERM"] = "xterm-256color"
        env["COLORTERM"] = "truecolor"

        pid, fd = pty.fork()
        if pid == 0:
            # Child process
            try:
                os.chdir(self.cwd)
            except OSError:
                os.chdir(os.path.expanduser("~"))
            os.execvpe(cmd[0], cmd, env)
        else:
            self.pid = pid
            self.fd = fd
            self.alive = True
            self.resize(30, 120)

    def read(self, size=4096):
        data = os.read(self.fd, size)
        if data:
            with self._lock:
                self.scrollback += data
                if len(self.scrollback) > MAX_SCROLLBACK:
                    self.scrollback = self.scrollback[-MAX_SCROLLBACK:]
        return data

    def write(self, data):
        if isinstance(data, str):
            data = data.encode()
        os.write(self.fd, data)

    def resize(self, rows, cols):
        try:
            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(self.fd, termios.TIOCSWINSZ, winsize)
        except (OSError, IOError):
            pass

    def terminate(self):
        if not self.alive:
            return
        self.alive = False
        try:
            os.kill(self.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            os.close(self.fd)
        except OSError:
            pass
        try:
            os.waitpid(self.pid, os.WNOHANG)
        except ChildProcessError:
            pass

    def get_scrollback(self):
        with self._lock:
            return self.scrollback

    def to_dict(self):
        return {
            "id": self.id,
            "label": self.label,
            "cwd": self.cwd,
            "alive": self.alive,
            "created_at": self.created_at,
        }


class TerminalManager:
    """Manages multiple PTY terminals."""

    def __init__(self):
        self.terminals: dict[str, Terminal] = {}
        self._readers: dict[str, threading.Thread] = {}

    def create(self, cmd, cwd=None, label=""):
        tid = uuid.uuid4().hex[:8]
        term = Terminal(tid, cmd, cwd, label)
        self.terminals[tid] = term
        return term

    def get(self, tid):
        return self.terminals.get(tid)

    def list_active(self):
        # Reap zombies
        for term in list(self.terminals.values()):
            if term.alive:
                try:
                    pid, _ = os.waitpid(term.pid, os.WNOHANG)
                    if pid != 0:
                        term.alive = False
                except ChildProcessError:
                    term.alive = False
        return [t.to_dict() for t in self.terminals.values()]

    def remove(self, tid):
        term = self.terminals.pop(tid, None)
        if term:
            term.terminate()
        self._readers.pop(tid, None)

    def start_reading(self, tid, socketio):
        """Start a background reader thread that emits PTY output to the SocketIO room."""
        term = self.get(tid)
        if not term or not term.alive:
            return
        # Don't start a second reader for the same terminal
        existing = self._readers.get(tid)
        if existing and existing.is_alive():
            return

        def reader():
            while term.alive:
                try:
                    r, _, _ = select.select([term.fd], [], [], 0.1)
                    if r:
                        data = term.read()
                        if data:
                            socketio.emit(
                                "terminal:output",
                                {"terminal_id": tid, "data": data.decode("utf-8", errors="replace")},
                                room=tid,
                                namespace="/",
                            )
                        else:
                            break
                except (OSError, IOError):
                    break

            term.alive = False
            socketio.emit("terminal:exit", {"terminal_id": tid}, room=tid, namespace="/")
            self._readers.pop(tid, None)

        t = threading.Thread(target=reader, daemon=True)
        t.start()
        self._readers[tid] = t

    def cleanup_all(self):
        for tid in list(self.terminals):
            self.remove(tid)


manager = TerminalManager()
atexit.register(manager.cleanup_all)
