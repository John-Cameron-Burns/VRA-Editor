"""Lets a scholar keep working on the 'edit' archive with no network at
all (e.g. a field trip), by copying it to a local folder they'll point
Settings' 'edit' location at for the duration, then reconciling their
offline edits back into the real, primary 'edit' folder once they're
back online.

Deliberately plain filesystem comparison, not git -- the primary side
isn't meaningfully version-controlled (core/commit_to_git.py's audit
history only has a commit when a user happens to give one a comment),
so what matters is its current on-disk content either way. A frozen
snapshot taken at staging time is the only "base" reconciliation needs,
compared directly against local's and primary's current content.

Pure stdlib + core/media_files.py -- no PySide6 dependency, same
reasoning as media_files.py's own module docstring: this stays usable
from a script or a test without dragging in Qt.
"""

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .media_files import DEFAULT_MEDIA_EXTENSIONS, copy_sibling_media, find_sibling_media

LIVE_SUBDIR = "edit"
SNAPSHOT_SUBDIR = ".snapshot"
ORIGIN_MARKER = ".vra_staging_origin"

# Ordered worst-to-best -- see _combine_status. A record needing
# attention on *either* its XML or its sibling media surfaces at
# whichever status is worse.
_STATUS_PRIORITY = ['conflict', 'removed_on_primary', 'new', 'updated', 'unchanged']


@dataclass(frozen=True)
class ReconcileItem:
    """One record (its XML and, if present, sibling media) that needs
    attention when reconciling a staging folder back into primary.
    Content isn't kept here -- apply_clean/apply_resolution re-read
    from disk at apply time, so this stays cheap to hold many of even
    when some records carry large media files."""
    relative_path: Path  # the XML's path, relative to the location root
    status: str  # 'new' | 'updated' | 'conflict' | 'removed_on_primary'


def start_staging(primary_dir: Path, staging_dir: Path, media_extensions=DEFAULT_MEDIA_EXTENSIONS) -> None:
    """Copies primary_dir's current contents into staging_dir/edit/ (the
    live copy the app will actually be pointed at) and staging_dir/.snapshot/
    (a frozen, untouched copy reconciliation later compares against).
    Also records primary_dir's own path, so reconcile_* doesn't need it
    re-supplied later."""
    primary_dir = Path(primary_dir).resolve()
    staging_dir = Path(staging_dir).resolve()
    live_dir = staging_dir / LIVE_SUBDIR
    snapshot_dir = staging_dir / SNAPSHOT_SUBDIR

    for xml_path in primary_dir.rglob("*.xml"):
        relative = xml_path.relative_to(primary_dir)
        for dest_root in (live_dir, snapshot_dir):
            dest = dest_root / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(xml_path, dest)
        sibling = find_sibling_media(xml_path, media_extensions)
        if sibling is not None:
            for dest_root in (live_dir, snapshot_dir):
                dest = (dest_root / relative).with_suffix(sibling.suffix)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(sibling, dest)

    staging_dir.mkdir(parents=True, exist_ok=True)
    (staging_dir / ORIGIN_MARKER).write_text(str(primary_dir))


def read_staging_origin(staging_dir: Path) -> Optional[Path]:
    """The primary folder this staging_dir was started from, or None if
    staging_dir isn't a staging folder at all (no marker file)."""
    marker = Path(staging_dir) / ORIGIN_MARKER
    if not marker.is_file():
        return None
    return Path(marker.read_text().strip())


def _combine_status(xml_status: str, media_status: str) -> str:
    for status in _STATUS_PRIORITY:
        if status in (xml_status, media_status):
            return status
    return 'unchanged'


def _classify(base_bytes: Optional[bytes], local_bytes: Optional[bytes], primary_bytes: Optional[bytes]) -> str:
    """The core 3-way comparison: was this file created, changed on one
    side, changed differently on both, or removed out from under a
    local edit? 'unchanged' covers every case nothing here needs to
    act on, including a file untouched everywhere and one that changed
    identically on both sides."""
    if base_bytes is None and local_bytes is not None:
        # Created locally, while offline.
        if primary_bytes is None:
            return 'new'
        # Something with the same path/id also appeared independently
        # on primary -- fine if it's the exact same content, otherwise
        # a genuine collision needing a human's attention.
        return 'unchanged' if primary_bytes == local_bytes else 'conflict'

    if base_bytes is not None and local_bytes is not None:
        local_changed = local_bytes != base_bytes
        if not local_changed:
            # Nothing to push to primary either way -- deliberately
            # 'unchanged' even if primary itself moved on (e.g. someone
            # else approved it away) while this record sat untouched
            # locally. This function reconciles *this scholar's own*
            # offline edits back in, not a general "what changed on
            # primary while I was away" report -- so removed_on_primary
            # below only fires when there's a local edit at stake.
            return 'unchanged'
        if primary_bytes is None:
            return 'removed_on_primary'
        if primary_bytes == base_bytes:
            return 'updated'  # safe: only local changed
        if primary_bytes == local_bytes:
            return 'unchanged'  # both changed, but converged on the same content
        return 'conflict'  # changed differently on both sides

    if base_bytes is not None and local_bytes is None:
        # Deleted from the local staging copy -- not something this
        # app's own UI does today, so treated conservatively as needing
        # a human's attention rather than auto-propagated either way.
        return 'conflict'

    return 'unchanged'  # neither base nor local has it -- not this function's concern


def plan_reconciliation(
    staging_dir: Path, primary_dir: Path, media_extensions=DEFAULT_MEDIA_EXTENSIONS,
) -> list[ReconcileItem]:
    """Every record needing attention to reconcile staging_dir's live
    working copy back into primary_dir -- 'unchanged' records (the vast
    majority, in practice: everything nobody touched offline) aren't
    included at all."""
    staging_dir = Path(staging_dir).resolve()
    primary_dir = Path(primary_dir).resolve()
    live_dir = staging_dir / LIVE_SUBDIR
    snapshot_dir = staging_dir / SNAPSHOT_SUBDIR

    candidates = {p.relative_to(live_dir) for p in live_dir.rglob("*.xml")}
    candidates |= {p.relative_to(snapshot_dir) for p in snapshot_dir.rglob("*.xml")}

    items = []
    for relative in sorted(candidates):
        base_xml = snapshot_dir / relative
        local_xml = live_dir / relative
        primary_xml = primary_dir / relative

        xml_status = _classify(
            base_xml.read_bytes() if base_xml.is_file() else None,
            local_xml.read_bytes() if local_xml.is_file() else None,
            primary_xml.read_bytes() if primary_xml.is_file() else None,
        )

        base_media = find_sibling_media(base_xml, media_extensions) if base_xml.is_file() else None
        local_media = find_sibling_media(local_xml, media_extensions) if local_xml.is_file() else None
        primary_media = find_sibling_media(primary_xml, media_extensions) if primary_xml.is_file() else None
        media_status = _classify(
            base_media.read_bytes() if base_media else None,
            local_media.read_bytes() if local_media else None,
            primary_media.read_bytes() if primary_media else None,
        )

        combined = _combine_status(xml_status, media_status)
        if combined != 'unchanged':
            items.append(ReconcileItem(relative_path=relative, status=combined))

    return items


def apply_clean(
    items: list[ReconcileItem], staging_dir: Path, primary_dir: Path, media_extensions=DEFAULT_MEDIA_EXTENSIONS,
) -> tuple[list[ReconcileItem], list[tuple[ReconcileItem, str]]]:
    """Copies every 'new'/'updated' item's local content (XML + sibling
    media) into primary -- 'conflict'/'removed_on_primary' items are
    left untouched, they need apply_resolution instead. Returns
    (applied, failed) rather than raising, so a partial failure (e.g.
    primary drops mid-batch) is reported instead of losing track of
    what did and didn't make it across."""
    staging_dir = Path(staging_dir).resolve()
    primary_dir = Path(primary_dir).resolve()
    live_dir = staging_dir / LIVE_SUBDIR

    applied, failed = [], []
    for item in items:
        if item.status not in ('new', 'updated'):
            continue
        try:
            _copy_record(live_dir / item.relative_path, primary_dir / item.relative_path, media_extensions)
            applied.append(item)
        except OSError as e:
            failed.append((item, str(e)))
    return applied, failed


def apply_resolution(
    item: ReconcileItem, choice: str, staging_dir: Path, primary_dir: Path,
    media_extensions=DEFAULT_MEDIA_EXTENSIONS,
) -> None:
    """Resolves one 'conflict'/'removed_on_primary' item:
      - 'keep_local': primary gets local's version (same as apply_clean
        would have, had this not been a conflict).
      - 'keep_primary': the local staging copy is overwritten with
        primary's current content instead, discarding the local edit --
        so local and primary agree afterward, the same way a real "keep
        theirs" merge resolution updates your working copy.
      - 'skip': neither side is touched; re-running plan_reconciliation
        will surface this item again next time.
    """
    staging_dir = Path(staging_dir).resolve()
    primary_dir = Path(primary_dir).resolve()
    live_dir = staging_dir / LIVE_SUBDIR

    if choice == 'skip':
        return
    if choice == 'keep_local':
        _copy_record(live_dir / item.relative_path, primary_dir / item.relative_path, media_extensions)
        return
    if choice == 'keep_primary':
        primary_xml = primary_dir / item.relative_path
        local_xml = live_dir / item.relative_path
        if primary_xml.is_file():
            _copy_record(primary_xml, local_xml, media_extensions)
        else:
            # Primary no longer has it (the removed_on_primary case) --
            # "keep primary" means accepting that, so the local copy
            # (and its media, if any) goes too.
            local_xml.unlink(missing_ok=True)
            sibling = find_sibling_media(local_xml, media_extensions)
            if sibling is not None:
                sibling.unlink(missing_ok=True)
        return
    raise ValueError(f"Unknown resolution choice: {choice!r}")


def _copy_record(src_xml: Path, dest_xml: Path, media_extensions) -> None:
    """Copies one record's XML and, if present, sibling media from
    src_xml's location to dest_xml's -- shared by apply_clean and both
    of apply_resolution's copying branches."""
    dest_xml.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_xml, dest_xml)
    copy_sibling_media(src_xml, dest_xml, media_extensions)
