import configparser
import shutil
from pathlib import Path

from .app_data import BOOTSTRAP_DIR, CONFIG_PATH
from .utils import strip_quotes

DEFAULT_CONFIG_PATH = CONFIG_PATH
_LEGACY_CONFIG_PATH = Path("~/vra-config.ini").expanduser()  # pre-app_data.py location

LOCATION_KEYS = ['edit', 'ingest', 'media', 'pending', 'rejected', 'reviewed', 'released']
OPTION_TEXT_KEYS = ['image_pattern', 'collection_pattern', 'work_pattern']


def to_bool(value: str) -> bool:
    return value.strip().lower() in ('1', 'true', 'yes', 'on')


def load_config(config_path: Path = DEFAULT_CONFIG_PATH) -> configparser.ConfigParser:
    if not config_path.exists() and config_path == DEFAULT_CONFIG_PATH and _LEGACY_CONFIG_PATH.exists():
        # One-time migration: this app used to write straight to
        # ~/vra-config.ini. Copy rather than move, so the old file stays
        # put as a backup rather than silently disappearing.
        BOOTSTRAP_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy(_LEGACY_CONFIG_PATH, config_path)

    parser = configparser.ConfigParser()
    if config_path.exists():
        parser.read(config_path)
    return parser


def load_locations(config_path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Path]:
    """Returns {name: Path} for every entry in [locations], expanded.

    Re-reads the file each call so callers always see the latest values
    (e.g. right after the user edits and saves Settings).
    """
    parser = load_config(config_path)
    if not parser.has_section('locations'):
        return {}
    return {
        key: Path(strip_quotes(value)).expanduser()
        for key, value in parser['locations'].items()
    }
