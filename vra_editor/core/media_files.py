"""Keeping a sibling media file (an image/video/audio file sharing a VRA
record's own base filename) paired with that record's XML as it moves
through the pipeline -- Import, Submit, Approve, Reject.

Deliberately pure stdlib (shutil + pathlib only, no Qt/pyexiv2/PIL) so
core/ingest.py -- which stays standalone-scriptable, independent of both
Qt and config.ini -- can use this without inheriting a GUI dependency.
Distinct from media_metadata.py's image-specific extension handling
(EXIF/IPTC reads are meaningfully image-only); this module only cares
about filenames, not content.
"""

import shutil
from pathlib import Path
from typing import Optional

DEFAULT_MEDIA_EXTENSIONS = (
    '.tif', '.tiff', '.jpg', '.jpeg', '.png', '.svg',
    '.mp4', '.mov', '.avi', '.mkv', '.wmv', '.m4v',
    '.mp3', '.wav', '.m4a', '.aac', '.flac', '.ogg',
)


def find_sibling_media(xml_path, extensions=DEFAULT_MEDIA_EXTENSIONS) -> Optional[Path]:
    """The first file next to xml_path sharing its stem and one of
    extensions, or None. First-match-wins by extensions' own order."""
    xml_path = Path(xml_path)
    for ext in extensions:
        candidate = xml_path.with_suffix(ext)
        if candidate.exists():
            return candidate
    return None


def _dest_media_path(sibling: Path, dest_xml_path) -> Path:
    return Path(dest_xml_path).with_suffix(sibling.suffix)


def copy_sibling_media(src_xml_path, dest_xml_path, extensions=DEFAULT_MEDIA_EXTENSIONS) -> Optional[Path]:
    """If a sibling sits next to src_xml_path, copies it to sit next to
    dest_xml_path (same stem, original extension), overwriting any stale
    file already there. Leaves the source in place -- see
    move_sibling_media for the move variant. None if there's no
    sibling to copy."""
    sibling = find_sibling_media(src_xml_path, extensions)
    if sibling is None:
        return None
    dest = _dest_media_path(sibling, dest_xml_path)
    if dest == sibling:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    shutil.copy2(str(sibling), str(dest))
    return dest


def move_sibling_media(src_xml_path, dest_xml_path, extensions=DEFAULT_MEDIA_EXTENSIONS) -> Optional[Path]:
    """As copy_sibling_media, but moves the sibling rather than copying
    it -- for transitions where only one copy of the record should ever
    exist (Submit/Approve/Reject, and moving an ingest source into
    done/). None if there's no sibling to move."""
    sibling = find_sibling_media(src_xml_path, extensions)
    if sibling is None:
        return None
    dest = _dest_media_path(sibling, dest_xml_path)
    if dest == sibling:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    shutil.move(str(sibling), str(dest))
    return dest
