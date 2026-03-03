"""SocketIO event handlers for terminal interaction."""

import logging
import os

from flask import request
from flask_socketio import emit, join_room

from .terminal import manager

log = logging.getLogger(__name__)


def register_events(socketio):

    @socketio.on("connect")
    def handle_connect():
        log.info("Client connected: %s", request.sid)

    @socketio.on("disconnect")
    def handle_disconnect():
        log.info("Client disconnected: %s", request.sid)

    @socketio.on("terminal:create")
    def handle_create(data):
        session_id = data.get("session_id")
        cwd = data.get("cwd") or os.path.expanduser("~")

        # Build the claude command via login shell so PATH is correct
        shell = os.environ.get("SHELL", "/bin/zsh")
        claude_args = ""
        if session_id:
            claude_args = f" --resume {session_id}"
            label = f"Resume {session_id[:8]}"
        else:
            label = f"claude @ {os.path.basename(cwd)}"

        cmd = [shell, "-l", "-c", f"claude{claude_args}"]
        log.info("Creating terminal: cmd=%s cwd=%s", cmd, cwd)

        try:
            term = manager.create(cmd, cwd, label)
            log.info("Terminal created: id=%s pid=%s", term.id, term.pid)
            join_room(term.id)
            emit("terminal:created", term.to_dict())
            manager.start_reading(term.id, socketio)
        except Exception as e:
            log.exception("Failed to create terminal")
            emit("terminal:error", {"message": str(e)})

    @socketio.on("terminal:attach")
    def handle_attach(data):
        tid = data.get("terminal_id")
        term = manager.get(tid)
        if not term:
            log.warning("Attach failed: terminal %s not found", tid)
            emit("terminal:error", {"message": "Terminal not found"})
            return

        log.info("Attaching to terminal: %s (alive=%s)", tid, term.alive)
        join_room(tid)

        # Send buffered scrollback to this client only
        scrollback = term.get_scrollback()
        if scrollback:
            emit("terminal:output", {
                "terminal_id": tid,
                "data": scrollback.decode("utf-8", errors="replace"),
            })

        if not term.alive:
            emit("terminal:exit", {"terminal_id": tid})
        else:
            emit("terminal:attached", term.to_dict())
            manager.start_reading(tid, socketio)

    @socketio.on("terminal:input")
    def handle_input(data):
        tid = data.get("terminal_id")
        term = manager.get(tid)
        if term and term.alive:
            term.write(data.get("data", ""))

    @socketio.on("terminal:resize")
    def handle_resize(data):
        tid = data.get("terminal_id")
        term = manager.get(tid)
        if term:
            term.resize(data.get("rows", 24), data.get("cols", 80))

    @socketio.on("terminal:kill")
    def handle_kill(data):
        tid = data.get("terminal_id")
        log.info("Killing terminal: %s", tid)
        manager.remove(tid)
        emit("terminal:exit", {"terminal_id": tid}, room=tid)

    @socketio.on("terminal:list")
    def handle_list():
        terminals = manager.list_active()
        log.info("Listing terminals: %d total", len(terminals))
        emit("terminal:list", terminals)
