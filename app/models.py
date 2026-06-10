"""Data classes for CC Dashboard."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Message:
    role: str  # "user" or "assistant"
    content: list  # list of content blocks
    timestamp: Optional[str] = None
    model: Optional[str] = None
    uuid: Optional[str] = None


@dataclass
class Session:
    session_id: str
    project_key: str  # encoded project dir name e.g. "-Users-admin-MiroFish"
    project_path: str  # original path e.g. "/Users/admin/MiroFish"
    first_prompt: str = ""
    summary: str = ""
    custom_title: str = ""  # from /rename command
    last_user_message: str = ""
    message_count: int = 0
    created: str = ""
    modified: str = ""
    git_branch: str = ""
    jsonl_path: str = ""
    entrypoint: str = ""  # "cli" = interactive, "sdk-cli" = headless/background task
    last_input_tokens: int = 0   # tokens sent on the most recent assistant call (input + cache)
    total_output_tokens: int = 0  # cumulative output tokens generated in this session
    compact_pending: bool = False  # True if /compact happened after the last assistant turn

    @property
    def is_background(self) -> bool:
        """True for sessions launched non-interactively (SDK/headless),
        e.g. scheduled subagent runs. These are noise in the session list."""
        return self.entrypoint == "sdk-cli"

    # Claude Code auto-compacts around 80% of the model's context window.
    # Users here run 1M-context models (the [1m] variant), so compact triggers
    # at ~800K tokens of input (input + cache_read + cache_creation).
    CONTEXT_AUTOCOMPACT_TOKENS = 800_000

    @property
    def ctx_percent(self) -> int:
        """Latest turn's input as a % of the auto-compact threshold (capped at 100)."""
        if not self.last_input_tokens:
            return 0
        return min(100, round(self.last_input_tokens / self.CONTEXT_AUTOCOMPACT_TOKENS * 100))

    @property
    def ctx_level(self) -> str:
        """Bucket for color-coding: 'low' / 'med' / 'high'."""
        p = self.ctx_percent
        if p >= 85:
            return "high"
        if p >= 60:
            return "med"
        return "low"

    @property
    def is_recent(self) -> bool:
        """True if last activity was within the last 10 days.
        Property (not method) so Jinja's rejectattr/selectattr work."""
        from datetime import datetime, timezone, timedelta
        ts = self.modified or self.created
        if not ts:
            return False
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return False
        return (datetime.now(timezone.utc) - dt) <= timedelta(days=10)

    @property
    def display_title(self) -> str:
        if self.custom_title:
            return self.custom_title
        if self.summary:
            return self.summary
        if self.last_user_message:
            return self.last_user_message[:80]
        if self.first_prompt:
            return self.first_prompt[:80]
        return self.session_id[:12]

    @property
    def project_name(self) -> str:
        if self.project_path:
            return self.project_path.rstrip("/").split("/")[-1] or self.project_path
        return self.project_key

    @property
    def resume_command(self) -> str:
        parts = []
        if self.project_path and self.project_path != "/":
            parts.append(f"cd {self.project_path}")
        parts.append(f"claude --resume {self.session_id}")
        return " && ".join(parts)


@dataclass
class Project:
    key: str  # directory name
    path: str  # original project path
    sessions: list = field(default_factory=list)

    @property
    def name(self) -> str:
        if self.path:
            return self.path.rstrip("/").split("/")[-1] or self.path
        # Decode key like "-Users-admin-MiroFish" -> "MiroFish"
        parts = self.key.split("-")
        return parts[-1] if parts else self.key


@dataclass
class Stats:
    total_sessions: int = 0
    total_messages: int = 0
    daily_activity: list = field(default_factory=list)
    model_usage: dict = field(default_factory=dict)
    hour_counts: dict = field(default_factory=dict)
    longest_session: dict = field(default_factory=dict)
    first_session_date: str = ""
    daily_model_tokens: list = field(default_factory=list)
