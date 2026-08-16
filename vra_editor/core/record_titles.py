"""Display-friendly labels for a VRA record file, for use in any
"browse a folder of records" UI -- the desktop file picker
(ui/dialogs/file_picker.py) and the web backend's folder-list endpoint
both need this. Deliberately Qt-free (plain xml.etree.ElementTree)
despite living in core/, since ui/dialogs/file_picker.py otherwise
pulls PySide6 in as a side effect of the dialog class defined
alongside it -- unusable from a headless web process.
"""

import xml.etree.ElementTree as ET
from pathlib import Path


def extract_title(path: Path) -> str:
    """Best-effort extraction of a VRA record's display title.

    Looks for any <title> element regardless of namespace prefix.
    A titleSet can list several titles (translations, alternates,
    etc.), so preference order is:
      1. type="main"   -- VRA Core's designated main title
      2. pref="true"   -- fallback if no type="main" is present
      3. the first <title> found
    Falls back to the filename stem if the file can't be parsed or
    has no title at all.
    """
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return path.stem

    titles = [
        el for el in root.iter()
        if el.tag.rsplit('}', 1)[-1] == 'title' and el.text and el.text.strip()
    ]
    if not titles:
        return path.stem

    for el in titles:
        if el.get('type', '').strip().lower() == 'main':
            return el.text.strip()

    for el in titles:
        if el.get('pref', '').strip().lower() == 'true':
            return el.text.strip()
    return titles[0].text.strip()


def human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if size < 1024 or unit == 'GB':
            return f"{size:.0f} {unit}" if unit == 'B' else f"{size:.1f} {unit}"
        size /= 1024
