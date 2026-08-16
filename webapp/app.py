"""Flask app factory for the VRA Editor web backend."""

from pathlib import Path
from typing import Optional

from flask import Flask, abort, send_from_directory

from .config import load_web_config, validate_auth_config
from .routes.audit_routes import audit_bp
from .routes.auth_routes import auth_bp
from .routes.export_routes import export_bp
from .routes.folder_routes import folder_bp
from .routes.import_routes import import_bp
from .routes.media_routes import media_bp
from .routes.record_routes import record_bp
from .routes.structure_routes import structure_bp
from .routes.vocab_routes import vocab_bp

# frontend/'s production build (npm run build), if present -- lets this
# one process serve the whole app on one port with no reverse proxy in
# front, for a standalone/test deployment. A real deployment behind
# IIS/Apache/nginx would instead have the proxy serve these static
# files directly and only forward /api/* here; either way, this is the
# same origin structure the frontend already assumes (see
# frontend/vite.config.js's dev-time /api proxy).
_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


def create_app(config_path: Optional[Path] = None) -> Flask:
    """config_path overrides vra_editor.config.DEFAULT_CONFIG_PATH for
    every config-reading call made during this app's requests (see
    auth.config_path_for_request) -- used by tests to point at an
    isolated temp config.ini instead of the real
    ~/.vra-editor/config.ini."""
    app = Flask(__name__)
    # Fail at process start, not on some user's first login attempt --
    # today load_ldap_config only raised inside authenticate() itself.
    validate_auth_config(config_path) if config_path else validate_auth_config()
    web_config = load_web_config(config_path) if config_path else load_web_config()
    app.config['SECRET_KEY'] = web_config['secret_key']
    app.config['VRA_CONFIG_PATH'] = config_path

    app.register_blueprint(audit_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(export_bp)
    app.register_blueprint(folder_bp)
    app.register_blueprint(import_bp)
    app.register_blueprint(media_bp)
    app.register_blueprint(record_bp)
    app.register_blueprint(structure_bp)
    app.register_blueprint(vocab_bp)

    if _FRONTEND_DIST.is_dir():
        @app.route('/', defaults={'path': ''})
        @app.route('/<path:path>')
        def serve_frontend(path):
            # The catch-all below would otherwise also match an unknown
            # /api/* path (a real 404) and serve index.html for it
            # instead -- guard explicitly rather than relying on
            # Werkzeug's static-vs-dynamic rule precedence for the
            # known blueprint routes.
            if path.startswith('api/'):
                abort(404)
            candidate = _FRONTEND_DIST / path
            if path and candidate.is_file():
                return send_from_directory(str(_FRONTEND_DIST), path)
            return send_from_directory(str(_FRONTEND_DIST), 'index.html')

    return app
