"""Flask app factory for CC Dashboard."""

from flask import Flask
from flask_socketio import SocketIO

from .config import Config
from .filters import register_filters
from .routes import bp

socketio = SocketIO(async_mode="threading")


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    register_filters(app)
    app.register_blueprint(bp)

    socketio.init_app(app)

    from .events import register_events
    register_events(socketio)

    @app.after_request
    def set_no_cache(response):
        if response.content_type and "text/html" in response.content_type:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        return response

    return app
