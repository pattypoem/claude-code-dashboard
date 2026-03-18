#!/usr/bin/env python3
"""CC Dashboard - Claude Code session manager."""

from app import create_app, socketio

app = create_app()


def main():
    socketio.run(
        app,
        host="127.0.0.1",
        port=app.config["PORT"],
        debug=True,
        use_reloader=False,
        allow_unsafe_werkzeug=True,
    )


if __name__ == "__main__":
    main()
