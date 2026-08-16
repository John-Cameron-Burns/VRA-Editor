"""Where this app's own operational files live: config, the version-
control audit trail, and the vocabulary-lookup cache -- kept in one
dedicated folder, separate from wherever the archive itself is
configured to live (see config.py's [locations]). Nothing under here
is archival content.

config.ini's own location can't be configurable -- something has to be
fixed for the app to find it in the first place -- so it always
bootstraps from BOOTSTRAP_DIR. Everything else this module hands out
(the git dir, the cache dir) honours an `app_data` entry in config.ini
if the user has set one, falling back to BOOTSTRAP_DIR otherwise.
"""

from pathlib import Path
from typing import Optional

BOOTSTRAP_DIR = Path("~/.vra-editor").expanduser()
CONFIG_PATH = BOOTSTRAP_DIR / "config.ini"


def get_app_data_dir(config_path: Optional[Path] = None) -> Path:
    """config_path overrides which vra-config.ini's [locations]
    app_data entry is consulted -- the desktop app never passes this
    (it only ever has the one, OS-default config.ini), but a caller
    reading a different config.ini (e.g. the web backend, or a test)
    needs its own app_data/git-dir/cache-dir resolution to follow
    that same config, not silently fall back to CONFIG_PATH."""
    from .config import load_locations  # deferred: config.py imports CONFIG_PATH from this module
    configured = load_locations(config_path) if config_path else load_locations()
    configured = configured.get('app_data')
    return configured if configured else BOOTSTRAP_DIR


def get_git_dir(config_path: Optional[Path] = None) -> Path:
    return get_app_data_dir(config_path) / "git"


def get_cache_dir(config_path: Optional[Path] = None) -> Path:
    return get_app_data_dir(config_path) / "cache"


def ensure_app_data_dir(config_path: Optional[Path] = None) -> Path:
    app_data_dir = get_app_data_dir(config_path)
    app_data_dir.mkdir(parents=True, exist_ok=True)
    get_cache_dir(config_path).mkdir(exist_ok=True)
    return app_data_dir
