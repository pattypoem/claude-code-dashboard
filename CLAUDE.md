# CLAUDE.md

## Project Overview

CC Dashboard - a local web app for browsing and managing Claude Code sessions. Reads session data from `~/.claude/` directory (read-only) and provides an interactive dashboard.

## Tech Stack

- **Backend**: Python 3.10+, Flask 3.0+, Flask-SocketIO 5.3+
- **Frontend**: Jinja2 templates, xterm.js, Socket.IO (all vendored in `app/static/vendor/`)
- **No database** - reads directly from Claude Code's local JSONL files

## Architecture

```
app/
├── __init__.py    # Flask app factory + SocketIO init
├── config.py      # Paths and port config
├── models.py      # Dataclasses: Session, Project, Message, Stats
├── routes.py      # HTTP routes (SSR, no frontend API calls on homepage)
├── data.py        # Data layer: JSONL scanning with mtime-based caching
├── events.py      # SocketIO handlers for terminal
├── terminal.py    # PTY management
├── filters.py     # Jinja2 template filters
├── templates/     # HTML templates
└── static/        # CSS, JS, vendor libs
```

## Key Design Decisions

- **JSONL is the primary data source** (real-time), `sessions-index.json` is only used for supplementary data (summary, sidechain flag). This is because Claude Code writes to JSONL in real-time but updates the index lazily.
- **Session display_title priority**: custom_title (/rename) > summary > last user message > first prompt > session ID
- **Empty sessions (0 messages) are filtered out** from display.
- **HTML responses have `Cache-Control: no-store`** to ensure fresh data on refresh.
- Homepage is fully server-side rendered; no client-side API calls for session data.

## Commands

```bash
# Run the app (uses venv)
./venv/bin/python3 run.py

# Default: http://127.0.0.1:5050
# Port configurable via CC_DASHBOARD_PORT env var
```

## Claude Code Local Data Structure

Located at `~/.claude/projects/<project-key>/`:

- `<session-id>.jsonl` - Real-time conversation log, one JSON object per line
- `sessions-index.json` - Session index (often stale, may have empty entries)
- JSONL record types of interest: `user`, `assistant`, `custom-title`, `summary`, `progress`
