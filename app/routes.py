"""All routes for CC Dashboard."""

from flask import Blueprint, render_template, request, jsonify

from .data import get_projects_with_sessions, get_session_by_id, get_session_messages, get_stats, search_sessions

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    """Dashboard: sessions grouped by project, with optional search."""
    query = request.args.get("q", "").strip()
    if query:
        sessions = search_sessions(query)
        # Group filtered sessions by project
        project_map = {}
        for s in sessions:
            key = s.project_key
            if key not in project_map:
                project_map[key] = {"key": key, "path": s.project_path, "sessions": []}
            project_map[key]["sessions"].append(s)
        projects = sorted(project_map.values(), key=lambda p: p["sessions"][0].modified, reverse=True)
    else:
        projects = get_projects_with_sessions()

    return render_template("index.html", projects=projects, query=query)


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
    sessions = search_sessions(query)
    # Group by project
    project_map = {}
    for s in sessions:
        key = s.project_key
        if key not in project_map:
            project_map[key] = {"key": key, "path": s.project_path, "sessions": []}
        project_map[key]["sessions"].append(s)
    projects = sorted(project_map.values(), key=lambda p: p["sessions"][0].modified, reverse=True)
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
