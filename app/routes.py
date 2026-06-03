"""All routes for CC Dashboard."""

from flask import Blueprint, render_template, request, jsonify

from .data import (
    get_all_sessions,
    get_session_by_id,
    get_session_messages,
    get_stats,
    group_by_project,
    search_sessions,
)

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    """Dashboard: sessions grouped by project, with optional search.

    Background (headless/SDK) sessions are hidden unless ?bg=1 is set.
    """
    query = request.args.get("q", "").strip()
    show_bg = request.args.get("bg") == "1"

    if query:
        matched = search_sessions(query, include_background=True)
    else:
        matched = get_all_sessions(include_background=True)

    hidden_count = sum(1 for s in matched if s.is_background)
    shown = matched if show_bg else [s for s in matched if not s.is_background]
    projects = group_by_project(shown)

    return render_template(
        "index.html", projects=projects, query=query,
        show_bg=show_bg, hidden_count=hidden_count,
    )


@bp.route("/session/<session_id>")
def session_detail(session_id):
    """Session detail: render conversation messages."""
    session = get_session_by_id(session_id)
    if not session:
        return render_template("index.html", projects=[], query="", error="Session not found"), 404

    messages = get_session_messages(session)
    return render_template("session.html", session=session, messages=messages)


@bp.route("/stats")
def stats():
    """Statistics overview page."""
    stats_data = get_stats()
    return render_template("stats.html", stats=stats_data)


@bp.route("/api/search")
def api_search():
    """Search API returning HTML partial."""
    query = request.args.get("q", "").strip()
    show_bg = request.args.get("bg") == "1"
    sessions = search_sessions(query, include_background=show_bg)
    projects = group_by_project(sessions)
    return render_template("partials/search_results.html", projects=projects)


@bp.route("/terminal")
def terminal_page():
    """Interactive terminal page."""
    projects = get_projects_with_sessions()
    return render_template("terminal.html", projects=projects)


@bp.route("/api/resume-command/<session_id>")
def api_resume_command(session_id):
    """Return resume command JSON."""
    session = get_session_by_id(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    return jsonify({"command": session.resume_command, "session_id": session_id})
