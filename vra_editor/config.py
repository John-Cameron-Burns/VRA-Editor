import configparser
import shutil
from pathlib import Path

from .app_data import BOOTSTRAP_DIR, CONFIG_PATH
from .core.media_files import DEFAULT_MEDIA_EXTENSIONS
from .utils import strip_quotes

DEFAULT_CONFIG_PATH = CONFIG_PATH
_LEGACY_CONFIG_PATH = Path("~/vra-config.ini").expanduser()  # pre-app_data.py location

LOCATION_KEYS = ['edit', 'ingest', 'pending', 'rejected', 'reviewed', 'released']
OPTION_TEXT_KEYS = ['image_pattern', 'collection_pattern', 'work_pattern', 'media_extensions']


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


def load_media_extensions(config_path: Path = DEFAULT_CONFIG_PATH) -> tuple[str, ...]:
    """The comma-separated [options] media_extensions list -- what counts
    as "the sibling media file" for a record when Import/Submit/Approve/
    Reject carry one alongside its XML (see core/media_files.py). Falls
    back to DEFAULT_MEDIA_EXTENSIONS when the key is absent or blank."""
    parser = load_config(config_path)
    if not parser.has_section('options'):
        return DEFAULT_MEDIA_EXTENSIONS
    raw = strip_quotes(parser['options'].get('media_extensions', ''))
    if not raw.strip():
        return DEFAULT_MEDIA_EXTENSIONS
    extensions = []
    for entry in raw.split(','):
        entry = entry.strip()
        if not entry:
            continue
        extensions.append(entry if entry.startswith('.') else f'.{entry}')
    return tuple(extensions) if extensions else DEFAULT_MEDIA_EXTENSIONS
