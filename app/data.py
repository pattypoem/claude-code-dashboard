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


def get_all_sessions(include_background: bool = False) -> list[Session]:
    """Get all sessions from all projects.

    Background sessions (headless/SDK-launched, e.g. scheduled subagent runs)
    are hidden by default; pass include_background=True to keep them.
    """
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
                entrypoint=meta.get("entrypoint", ""),
                last_input_tokens=meta.get("last_input_tokens", 0),
                total_output_tokens=meta.get("total_output_tokens", 0),
            )
            sessions.append(session)

    # Filter out empty sessions (no messages and no meaningful title)
    sessions = [s for s in sessions if s.message_count > 0]

    # Hide background (headless/SDK) sessions unless explicitly requested
    if not include_background:
        sessions = [s for s in sessions if not s.is_background]

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
        "entrypoint": "",
        "last_input_tokens": 0, "total_output_tokens": 0,
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
                        if not meta["entrypoint"] and d.get("entrypoint"):
                            meta["entrypoint"] = d["entrypoint"]
                        if msg_type == "assistant":
                            usage = d.get("message", {}).get("usage", {})
                            if usage:
                                inp = (usage.get("input_tokens", 0)
                                       + usage.get("cache_read_input_tokens", 0)
                                       + usage.get("cache_creation_input_tokens", 0))
                                # Track the most recent turn's input as the
                                # session's "current context size".
                                if inp > 0:
                                    meta["last_input_tokens"] = inp
                                meta["total_output_tokens"] += usage.get("output_tokens", 0)
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


def group_by_project(sessions: list[Session]) -> list[Project]:
    """Group a list of sessions into projects, sorted by most recent activity."""
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


def get_projects_with_sessions(include_background: bool = False) -> list[Project]:
    """Get sessions grouped by project."""
    return group_by_project(get_all_sessions(include_background=include_background))


def get_session_by_id(session_id: str) -> Optional[Session]:
    """Find a session by its ID (background sessions included, so direct links resolve)."""
    for session in get_all_sessions(include_background=True):
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
    """Compute stats directly from JSONL files.

    Claude Code's own stats-cache.json updates lazily and was often stale,
    so we recompute on each request. Background (sdk-cli) sessions ARE
    counted — token spend matters whether interactive or not.
    """
    # Use same filter as the session list (skip sidechain + empty) but INCLUDE
    # background sessions: tokens spent by headless tasks are still real spend.
    sessions = get_all_sessions(include_background=True)
    total_sessions = len(sessions)
    total_messages = 0
    first_session_ts = ""
    longest_count = 0
    daily: dict[str, dict] = {}  # date -> {messageCount, sessionCount, toolCallCount}
    daily_session_seen: dict[str, set] = {}  # date -> {session_ids} for dedup
    model_usage: dict[str, dict] = {}
    hour_counts: dict[str, int] = {}

    for session in sessions:
        jsonl_file = Path(session.jsonl_path)
        if not jsonl_file.is_file():
            continue
        session_id = session.session_id
        session_msg_count = 0

        try:
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    t = d.get("type")
                    if t not in ("user", "assistant"):
                        continue

                    session_msg_count += 1
                    total_messages += 1
                    ts = d.get("timestamp", "")
                    if ts:
                        if not first_session_ts or ts < first_session_ts:
                            first_session_ts = ts
                        date_key = ts[:10]
                        try:
                            hour = int(ts[11:13])
                            hour_counts[str(hour)] = hour_counts.get(str(hour), 0) + 1
                        except ValueError:
                            pass
                        day = daily.setdefault(date_key, {
                            "date": date_key,
                            "messageCount": 0,
                            "sessionCount": 0,
                            "toolCallCount": 0,
                        })
                        day["messageCount"] += 1
                        seen = daily_session_seen.setdefault(date_key, set())
                        if session_id not in seen:
                            seen.add(session_id)
                            day["sessionCount"] += 1

                    if t == "assistant":
                        msg = d.get("message", {})
                        usage = msg.get("usage", {})
                        model = msg.get("model")
                        if model and usage:
                            m = model_usage.setdefault(model, {
                                "inputTokens": 0,
                                "outputTokens": 0,
                                "cacheReadInputTokens": 0,
                                "cacheCreationInputTokens": 0,
                            })
                            m["inputTokens"] += usage.get("input_tokens", 0)
                            m["outputTokens"] += usage.get("output_tokens", 0)
                            m["cacheReadInputTokens"] += usage.get("cache_read_input_tokens", 0)
                            m["cacheCreationInputTokens"] += usage.get("cache_creation_input_tokens", 0)
                        content = msg.get("content", [])
                        if isinstance(content, list):
                            for block in content:
                                if isinstance(block, dict) and block.get("type") == "tool_use":
                                    date_key = ts[:10] if ts else ""
                                    if date_key and date_key in daily:
                                        daily[date_key]["toolCallCount"] += 1
        except OSError:
            continue

        if session_msg_count > longest_count:
            longest_count = session_msg_count

    daily_activity = sorted(daily.values(), key=lambda x: x["date"])

    return Stats(
        total_sessions=total_sessions,
        total_messages=total_messages,
        daily_activity=daily_activity,
        model_usage=model_usage,
        hour_counts=hour_counts,
        longest_session={"messageCount": longest_count} if longest_count else {},
        first_session_date=first_session_ts,
        daily_model_tokens=[],
    )


def search_sessions(query: str, include_background: bool = False) -> list[Session]:
    """Search sessions by title, summary, or first prompt."""
    if not query:
        return get_all_sessions(include_background=include_background)

    query_lower = query.lower()
    results = []
    for session in get_all_sessions(include_background=include_background):
        if (
            query_lower in session.summary.lower()
            or query_lower in session.first_prompt.lower()
            or query_lower in session.session_id.lower()
            or query_lower in session.project_path.lower()
        ):
            results.append(session)
    return results
