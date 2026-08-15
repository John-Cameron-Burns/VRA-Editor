"""Entrypoint for running the web backend under a production WSGI
server from the repo root, e.g.:

    waitress-serve --host=0.0.0.0 --port=8000 --call webapp.wsgi:create_app_from_env

Honors VRA_CONFIG_PATH if set, so a deployment can point at a
vra-config.ini that isn't the OS-default ~/.vra-editor/config.ini
(e.g. a dedicated service account with no meaningful home directory)
without needing to fake one.
"""

import os
from pathlib import Path

from webapp.app import create_app


def create_app_from_env():
    config_path = os.environ.get('VRA_CONFIG_PATH')
    return create_app(config_path=Path(config_path) if config_path else None)
