"""Moving a record between the archive's shared working locations
(edit/ingest/pending/rejected/reviewed/released).

This is the logic behind DocumentController's submit_file/approve_file/
reject_file (and save_file's own destination-write step) -- extracted
here since none of it actually touches Qt: it's schema validation, a
path move that preserves the record's subfolder structure, and moving
a sibling media file along with it. DocumentController wraps
move_to_location as a thin adapter that also tracks its own
"currently open file" state and emits signals; a stateless caller
(e.g. a web request handler) can call it directly.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from lxml import etree

from vra_editor.core import media_files
from vra_editor.core.schema_validator import SchemaValidator


class LocationUnavailableError(Exception):
    """Raised when location_key's destination folder itself can't be
    written to (e.g. a network share that's offline) -- distinct from
    LocationTransitionResult's own (success, message) contract, which
    is reserved for schema-validation failures and missing/
    unconfigured locations (a Settings problem, not a connectivity
    one)."""
    pass


@dataclass(frozen=True)
class LocationTransitionResult:
    success: bool
    message: str  # the validation/configuration error on failure, or the new path on success
    dest_path: Optional[Path] = None


def relative_record_path(src_path: Path, locations: dict) -> Path:
    """src_path's path relative to whichever of locations
    (edit/ingest/pending/rejected/reviewed/released) it currently sits
    under, so a submit/approve/reject move can reproduce that same
    subfolder structure at the destination instead of flattening it to
    just the filename. Falls back to the bare filename if src_path
    isn't under any configured location -- shouldn't normally happen,
    but better than raising over it."""
    for root in locations.values():
        try:
            return src_path.relative_to(root.resolve())
        except ValueError:
            continue
    return Path(src_path.name)


def move_to_location(
    xml_root, location_key: str, locations: dict, src_path: Path,
    validator: SchemaValidator, validate: bool,
    media_extensions=media_files.DEFAULT_MEDIA_EXTENSIONS,
) -> LocationTransitionResult:
    """Writes xml_root to location_key's configured folder (from
    locations, e.g. config.load_locations()'s return), preserving
    whatever subfolder path src_path currently has relative to its own
    location (see relative_record_path) -- edit/collectionA/foo.xml
    submits to pending/collectionA/foo.xml, not a flattened
    pending/foo.xml -- then removes it from wherever it was, and moves
    any sibling media file (see media_files.py) along with it.

    validate gates whether this transition requires a schema-valid
    document first: Submit does (it's the actual gate keeping invalid
    records out of the review queue); Approve/Reject don't (the
    document was already validated at Submit time, and a reviewer
    needs to be able to reject something broken without first having
    to fix it themselves).

    Raises LocationUnavailableError if location_key's folder can't
    actually be written to.
    """
    xml_bytes = etree.tostring(xml_root, pretty_print=True, xml_declaration=True, encoding='UTF-8')
    if validate:
        valid, message = validator.validate(xml_bytes)
        if not valid:
            return LocationTransitionResult(False, message)

    dest_dir = locations.get(location_key)
    if dest_dir is None:
        return LocationTransitionResult(False, f"No '{location_key}' folder configured in vra-config.ini.")

    src_path = src_path.resolve()
    dest_path = (dest_dir / relative_record_path(src_path, locations)).resolve()
    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(dest_path, 'wb') as f:
            f.write(xml_bytes)

        if src_path != dest_path and src_path.exists():
            src_path.unlink()

        # A sibling media file (same base name, e.g. foo.tif next to
        # foo.xml) rides along on every submit/approve/reject, so the
        # pair never gets split across folders.
        media_files.move_sibling_media(src_path, dest_path, media_extensions)
    except OSError as e:
        raise LocationUnavailableError(
            f"Couldn't move this record to '{location_key}' -- {dest_dir} isn't reachable right now ({e})."
        ) from e

    return LocationTransitionResult(True, str(dest_path), dest_path)
