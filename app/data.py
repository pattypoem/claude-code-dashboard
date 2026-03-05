"""Data access layer for Claude Code files. Read-only with mtime-based caching."""

import json
import os
from pathlib import Path
from typing import Optional

from .config import Config
from .models import Message, Project, Session, Stats

# In-memory cache: path -> (mtime, data)
_cache: dict[str, tuple[float, object]] = {}


def _read_json_cached(path: Path) -> Optional[dict]:
    """Read a JSON file with mtime caching."""
    path_str = str(path)
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None

    cached = _cache.get(path_str)
    if cached and cached[0] == mtime:
        return cached[1]

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        _cache[path_str] = (mtime, data)
        return data
    except (json.JSONDecodeError, OSError):
        return None


def _read_jsonl_cached(path: Path) -> Optional[list[dict]]:
    """Read a JSONL file with mtime caching."""
    path_str = str(path)
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None

    cached = _cache.get(path_str)
    if cached and cached[0] == mtime:
        return cached[1]

    lines = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        lines.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        _cache[path_str] = (mtime, lines)
        return lines
    except OSError:
        return None


def get_all_sessions() -> list[Session]:
    """Get all sessions from all projects."""
    sessions = []
    projects_dir = Config.PROJECTS_DIR
    if not projects_dir.is_dir():
        return sessions

    for project_dir in sorted(projects_dir.iterdir()):
        if not project_dir.is_dir():
            continue
        project_key = project_dir.name

        # Read index only for supplementary data (summary, sidechain flag)
        index_path = project_dir / "sessions-index.json"
        index_data = _read_json_cached(index_path)
        index_lookup: dict[str, dict] = {}
        original_path = _decode_project_key(project_key)
        if index_data:
            original_path = index_data.get("originalPath", original_path)
            for entry in index_data.get("entries", []):
                sid = entry.get("sessionId", "")
                if sid:
                    index_lookup[sid] = entry

        # Always scan JSONL files as primary source (real-time)
        for jsonl_file in sorted(project_dir.glob("*.jsonl")):
            session_id = jsonl_file.stem
            index_entry = index_lookup.get(session_id, {})

            if index_entry.get("isSidechain"):
                continue

            first_line = _peek_first_user_message(jsonl_file)
            meta = _extract_session_meta(jsonl_file)
            session = Session(
                session_id=session_id,
                project_key=project_key,
                project_path=meta.get("project_path", original_path),
                first_prompt=first_line,
                summary=meta.get("summary", "") or index_entry.get("summary", ""),
                custom_title=meta.get("custom_title", ""),
                last_user_message=meta.get("last_user_message", ""),
                message_count=meta.get("message_count", 0),
                created=meta.get("created", ""),
                modified=meta.get("modified", ""),
                git_branch=meta.get("git_branch", ""),
                jsonl_path=str(jsonl_file),
            )
            sessions.append(session)

    # Filter out empty sessions (no messages and no meaningful title)
    sessions = [s for s in sessions if s.message_count > 0]

    # Sort by modified time, newest first
    sessions.sort(key=lambda s: s.modified or s.created, reverse=True)
    return sessions


def _decode_project_key(key: str) -> str:
    """Decode project key like '-Users-admin-MiroFish' to '/Users/admin/MiroFish'."""
    if key.startswith("-"):
        return "/" + key[1:].replace("-", "/")
    return key


def _peek_first_user_message(jsonl_path: Path) -> str:
    """Get first real user message from a JSONL file (quick scan)."""
    try:
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                    if d.get("type") == "user":
                        content = d.get("message", {}).get("content", "")
                        if isinstance(content, str):
                            # Skip command/system messages
                            if "<command-name>" in content or "<local-command" in content:
                                continue
                            if len(content) > 10:
                                return content[:200]
                        elif isinstance(content, list):
                            for block in content:
                                if isinstance(block, dict) and block.get("type") == "text":
                                    text = block.get("text", "")
                                    if len(text) > 10:
                                        return text[:200]
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return ""


def _extract_session_meta(jsonl_path: Path) -> dict:
    """Extract basic metadata from a JSONL file."""
    meta = {
        "message_count": 0, "created": "", "modified": "",
        "git_branch": "", "project_path": "",
        "custom_title": "", "summary": "", "last_user_message": "",
    }
    first_ts = None
    last_ts = None
    try:
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                    msg_type = d.get("type")
                    if msg_type == "custom-title":
                        meta["custom_title"] = d.get("customTitle", "")
                    elif msg_type == "summary":
                        meta["summary"] = d.get("summary", "")
                    elif msg_type in ("user", "assistant"):
                        meta["message_count"] += 1
                        ts = d.get("timestamp")
                        if ts:
                            if first_ts is None:
                                first_ts = ts
                            last_ts = ts
                        if not meta["git_branch"] and d.get("gitBranch"):
                            meta["git_branch"] = d["gitBranch"]
                        if not meta["project_path"] and d.get("cwd"):
                            meta["project_path"] = d["cwd"]
                        if msg_type == "user":
                            content = d.get("message", {}).get("content", "")
                            text = _extract_user_text(content)
                            if text:
                                meta["last_user_message"] = text
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    meta["created"] = first_ts or ""
    meta["modified"] = last_ts or ""
    return meta


def _extract_user_text(content) -> str:
    """Extract plain text from user message content, skipping commands."""
    if isinstance(content, str):
        if "<command-name>" in content or "<local-command" in content:
            return ""
        return content[:200].strip() if len(content) > 10 else ""
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                if "<command-name>" in text or "<local-command" in text:
                    continue
                if len(text) > 10:
                    return text[:200].strip()
    return ""


def get_projects_with_sessions() -> list[Project]:
    """Get sessions grouped by project."""
    sessions = get_all_sessions()
    project_map: dict[str, Project] = {}

    for session in sessions:
        key = session.project_key
        if key not in project_map:
            project_map[key] = Project(
                key=key,
                path=session.project_path,
                sessions=[],
            )
        project_map[key].sessions.append(session)

    projects = list(project_map.values())
    # Sort projects by most recent session
    projects.sort(
        key=lambda p: max((s.modified or s.created) for s in p.sessions) if p.sessions else "",
        reverse=True,
    )
    return projects


def get_session_by_id(session_id: str) -> Optional[Session]:
    """Find a session by its ID."""
    for session in get_all_sessions():
        if session.session_id == session_id:
            return session
    return None


def get_session_messages(session: Session) -> list[Message]:
    """Read all user/assistant messages from a session's JSONL file."""
    jsonl_path = session.jsonl_path
    if not jsonl_path:
        # Try to find it
        jsonl_path = str(Config.PROJECTS_DIR / session.project_key / f"{session.session_id}.jsonl")

    path = Path(jsonl_path)
    raw_lines = _read_jsonl_cached(path)
    if not raw_lines:
        return []

    messages = []
    for entry in raw_lines:
        msg_type = entry.get("type")
        if msg_type not in ("user", "assistant"):
            continue

        msg_data = entry.get("message", {})
        role = msg_data.get("role", msg_type)
        content = msg_data.get("content", "")

        # Normalize content to list of blocks
        if isinstance(content, str):
            # Skip command/system messages for user
            if role == "user" and ("<command-name>" in content or "<local-command" in content):
                continue
            content_blocks = [{"type": "text", "text": content}]
        elif isinstance(content, list):
            content_blocks = content
        else:
            continue

        # Skip empty user messages
        if role == "user":
            has_text = any(
                isinstance(b, dict) and b.get("type") == "text" and b.get("text", "").strip()
                for b in content_blocks
            )
            if not has_text:
                continue

        messages.append(
            Message(
                role=role,
                content=content_blocks,
                timestamp=entry.get("timestamp"),
                model=msg_data.get("model"),
                uuid=entry.get("uuid"),
            )
        )

    return messages


def get_stats() -> Stats:
    """Read stats from stats-cache.json."""
    data = _read_json_cached(Config.STATS_CACHE)
    if not data:
        return Stats()

    return Stats(
        total_sessions=data.get("totalSessions", 0),
        total_messages=data.get("totalMessages", 0),
        daily_activity=data.get("dailyActivity", []),
        model_usage=data.get("modelUsage", {}),
        hour_counts=data.get("hourCounts", {}),
        longest_session=data.get("longestSession", {}),
        first_session_date=data.get("firstSessionDate", ""),
        daily_model_tokens=data.get("dailyModelTokens", []),
    )


def search_sessions(query: str) -> list[Session]:
    """Search sessions by title, summary, or first prompt."""
    if not query:
        return get_all_sessions()

    query_lower = query.lower()
    results = []
    for session in get_all_sessions():
        if (
            query_lower in session.summary.lower()
            or query_lower in session.first_prompt.lower()
            or query_lower in session.session_id.lower()
            or query_lower in session.project_path.lower()
        ):
            results.append(session)
    return results
