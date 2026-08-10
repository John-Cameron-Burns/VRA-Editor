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

BOOTSTRAP_DIR = Path("~/.vra-editor").expanduser()
CONFIG_PATH = BOOTSTRAP_DIR / "config.ini"


def get_app_data_dir() -> Path:
    from .config import load_locations  # deferred: config.py imports CONFIG_PATH from this module
    configured = load_locations().get('app_data')
    return configured if configured else BOOTSTRAP_DIR


def get_git_dir() -> Path:
    return get_app_data_dir() / "git"


def get_cache_dir() -> Path:
    return get_app_data_dir() / "cache"


def ensure_app_data_dir() -> Path:
    app_data_dir = get_app_data_dir()
    app_data_dir.mkdir(parents=True, exist_ok=True)
    get_cache_dir().mkdir(exist_ok=True)
    return app_data_dir
