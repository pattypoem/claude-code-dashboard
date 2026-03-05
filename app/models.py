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
