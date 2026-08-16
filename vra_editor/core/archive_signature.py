"""A hidden marker file dropped into each of an archive's folders --
the clutter/app_data folder plus edit/ingest/pending/rejected/reviewed/
released -- so Settings' clutter-folder auto-detection (see
ui/dialogs/settings_dialog.py) can confirm a same-named folder found
nearby genuinely belongs to the same archive configuration, rather
than silently wiring together two unrelated folders that just happen
to share a name like "edit".

Not a security boundary -- a plain text file, trivially fakeable --
just enough to keep a name-based heuristic honest.
"""

import uuid
from pathlib import Path
from typing import Optional

SIGNATURE_FILENAME = '.vra-editor-archive-id'

_HEADER = (
    "# VRA Editor -- marks this folder as belonging to one archive\n"
    "# configuration, so Settings' clutter-folder auto-detection can\n"
    "# confirm a same-named folder found nearby really belongs here,\n"
    "# rather than just coincidentally sharing a name. Safe to delete\n"
    "# -- auto-detection then falls back to a name-only match.\n"
)


def read_signature(folder: Path) -> Optional[str]:
    """The archive ID recorded in folder, or None if it has none (never
    configured through this feature, or the file was removed)."""
    sig_path = folder / SIGNATURE_FILENAME
    if not sig_path.is_file():
        return None
    for line in sig_path.read_text(errors='ignore').splitlines():
        line = line.strip()
        if line and not line.startswith('#'):
            return line
    return None


def write_signature(folder: Path, archive_id: str) -> None:
    """Best-effort -- a folder that cannot be written to (permissions,
    a read-only mount) just means future auto-detection cannot verify
    it, not a failure worth interrupting a Settings save over."""
    sig_path = folder / SIGNATURE_FILENAME
    try:
        sig_path.write_text(_HEADER + f"{archive_id}\n")
    except OSError:
        pass


def new_archive_id() -> str:
    return uuid.uuid4().hex
