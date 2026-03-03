"""Configuration for CC Dashboard."""

import os
from pathlib import Path


class Config:
    CLAUDE_HOME = Path(os.environ.get("CLAUDE_HOME", Path.home() / ".claude"))
    PROJECTS_DIR = CLAUDE_HOME / "projects"
    STATS_CACHE = CLAUDE_HOME / "stats-cache.json"
    PORT = int(os.environ.get("CC_DASHBOARD_PORT", 5050))
    SECRET_KEY = os.environ.get("SECRET_KEY", "cc-dashboard-dev-key")
