/* CC Dashboard - Interactive Terminal (xterm.js + SocketIO) */

(function () {
    "use strict";

    /* ---- Sanity checks ---- */
    if (typeof Terminal === "undefined") {
        document.getElementById("lobby").innerHTML =
            '<div class="error-banner">Failed to load xterm.js</div>';
        return;
    }
    if (typeof io === "undefined") {
        document.getElementById("lobby").innerHTML =
            '<div class="error-banner">Failed to load socket.io client</div>';
        return;
    }

    var params = new URLSearchParams(window.location.search);
    var resumeId = params.get("resume");
    var attachId = params.get("attach");
    var cwdParam = params.get("cwd");

    var lobby = document.getElementById("lobby");
    var termView = document.getElementById("terminal-view");
    var termContainer = document.getElementById("terminal-container");
    var termInfo = document.getElementById("terminal-info");
    var termStatus = document.getElementById("terminal-status");
    var activeSection = document.getElementById("active-section");
    var activeTerminals = document.getElementById("active-terminals");

    var term = null;
    var fitAddon = null;
    var socket = null;
    var currentTerminalId = null;

    /* ---- xterm.js setup ---- */
    function initXterm() {
        if (term) return;

        term = new Terminal({
            theme: {
                background: "#1a1a2e",
                foreground: "#e0e0e0",
                cursor: "#e2b84a",
                cursorAccent: "#1a1a2e",
                selectionBackground: "rgba(226, 184, 74, 0.3)",
                black: "#1a1a2e",
                red: "#e25c5c",
                green: "#4ec97a",
                yellow: "#e2b84a",
                blue: "#5c9ee2",
                magenta: "#a87de2",
                cyan: "#5ce2e2",
                white: "#e0e0e0",
                brightBlack: "#5a6270",
                brightRed: "#ff7b7b",
                brightGreen: "#6eeb96",
                brightYellow: "#ffd76e",
                brightBlue: "#7bb8ff",
                brightMagenta: "#c49dff",
                brightCyan: "#7bffff",
                brightWhite: "#ffffff",
            },
            fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'Menlo', monospace",
            fontSize: 14,
            cursorBlink: true,
            scrollback: 5000,
        });

        fitAddon = new FitAddon.FitAddon();
        term.loadAddon(fitAddon);
        term.open(termContainer);

        term.onData(function (data) {
            if (currentTerminalId && socket && socket.connected) {
                socket.emit("terminal:input", { terminal_id: currentTerminalId, data: data });
            }
        });

        term.onResize(function (size) {
            if (currentTerminalId && socket && socket.connected) {
                socket.emit("terminal:resize", {
                    terminal_id: currentTerminalId,
                    rows: size.rows,
                    cols: size.cols,
                });
            }
        });

        window.addEventListener("resize", doFit);
    }

    function doFit() {
        if (fitAddon && termView.style.display !== "none") {
            try { fitAddon.fit(); } catch (e) { /* ignore */ }
        }
    }

    /* ---- SocketIO setup ---- */
    function connectSocket() {
        socket = io({
            transports: ["websocket", "polling"],
            reconnection: true,
            reconnectionDelay: 1000,
        });

        socket.on("connect", function () {
            console.log("[cc-dashboard] socket connected, id=" + socket.id);
            if (resumeId) {
                initXterm();
                socket.emit("terminal:create", { session_id: resumeId, cwd: cwdParam || undefined });
            } else if (attachId) {
                initXterm();
                currentTerminalId = attachId;
                socket.emit("terminal:attach", { terminal_id: attachId });
            } else {
                socket.emit("terminal:list");
            }
        });

        socket.on("connect_error", function (err) {
            console.error("[cc-dashboard] socket connect_error:", err.message);
        });

        socket.on("terminal:created", function (data) {
            console.log("[cc-dashboard] terminal created:", data.id);
            currentTerminalId = data.id;
            showTerminal(data);
        });

        socket.on("terminal:attached", function (data) {
            console.log("[cc-dashboard] terminal attached:", data.id);
            showTerminal(data);
        });

        socket.on("terminal:output", function (data) {
            if (term) term.write(data.data);
        });

        socket.on("terminal:exit", function (data) {
            console.log("[cc-dashboard] terminal exited:", data.terminal_id);
            if (term) term.write("\r\n\x1b[33m[Process exited]\x1b[0m\r\n");
            setStatus("exited");
        });

        socket.on("terminal:list", function (terminals) {
            renderActiveTerminals(terminals);
        });

        socket.on("terminal:error", function (data) {
            console.error("[cc-dashboard] terminal error:", data.message);
            if (term) {
                term.write("\r\n\x1b[31m[Error: " + data.message + "]\x1b[0m\r\n");
            }
        });

        socket.on("disconnect", function (reason) {
            console.log("[cc-dashboard] socket disconnected:", reason);
            setStatus("disconnected");
        });
    }

    /* ---- UI state management ---- */
    function showTerminal(data) {
        lobby.style.display = "none";
        termView.style.display = "flex";
        termInfo.textContent = data.label + "  " + data.cwd;
        setStatus("connected");

        // Clear URL params so refresh doesn't re-create
        history.replaceState(null, "", "/terminal?attach=" + data.id);

        setTimeout(function () {
            doFit();
            if (term) term.focus();
        }, 100);
    }

    function showLobby() {
        termView.style.display = "none";
        lobby.style.display = "block";
        currentTerminalId = null;
        history.replaceState(null, "", "/terminal");
        if (socket && socket.connected) socket.emit("terminal:list");
    }

    function setStatus(status) {
        if (!termStatus) return;
        termStatus.textContent = status;
        termStatus.className = "terminal-status-badge status-" + status;
    }

    function renderActiveTerminals(terminals) {
        var active = terminals.filter(function (t) { return t.alive; });
        if (active.length === 0) {
            activeSection.style.display = "none";
            return;
        }
        activeSection.style.display = "block";

        var html = "";
        active.forEach(function (t) {
            html += '<div class="active-terminal-card">' +
                '<div class="active-terminal-info">' +
                '<span class="active-terminal-label">' + escapeHtml(t.label) + '</span>' +
                '<span class="active-terminal-cwd">' + escapeHtml(t.cwd) + '</span>' +
                '</div>' +
                '<div class="active-terminal-actions">' +
                '<button class="btn btn-sm btn-accent attach-btn" data-tid="' + t.id + '">Attach</button>' +
                '<button class="btn btn-sm btn-danger kill-active-btn" data-tid="' + t.id + '">Kill</button>' +
                '</div>' +
                '</div>';
        });
        activeTerminals.innerHTML = html;
    }

    function escapeHtml(str) {
        var div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }

    /* ---- Event handlers ---- */
    document.addEventListener("click", function (e) {
        var attachBtn = e.target.closest(".attach-btn");
        if (attachBtn) {
            var tid = attachBtn.dataset.tid;
            initXterm();
            currentTerminalId = tid;
            socket.emit("terminal:attach", { terminal_id: tid });
            return;
        }

        var killBtn = e.target.closest(".kill-active-btn");
        if (killBtn) {
            var tid2 = killBtn.dataset.tid;
            socket.emit("terminal:kill", { terminal_id: tid2 });
            setTimeout(function () { socket.emit("terminal:list"); }, 300);
            return;
        }
    });

    document.getElementById("new-session-btn").addEventListener("click", function () {
        var sel = document.getElementById("project-select");
        var cwd = sel.value || undefined;
        initXterm();
        socket.emit("terminal:create", { cwd: cwd });
    });

    document.getElementById("back-btn").addEventListener("click", function () {
        showLobby();
    });

    document.getElementById("kill-btn").addEventListener("click", function () {
        if (currentTerminalId) {
            socket.emit("terminal:kill", { terminal_id: currentTerminalId });
        }
        showLobby();
    });

    /* ---- Initialize ---- */
    connectSocket();
})();
