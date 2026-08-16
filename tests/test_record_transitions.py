"""Tests for vra_editor.core.record_transitions.move_to_location -- the
logic behind the desktop app's Save/Submit/Approve/Reject buttons.
Pure Python/lxml, no Qt needed (this module never touches it).

Specifically covers: Submit/Approve must not fail just because their
destination folder (pending/reviewed/etc.) doesn't exist on disk yet
-- a very ordinary state for a freshly-configured archive, or a
location an operator has renamed/moved. move_to_location creates it
on demand via mkdir(parents=True, exist_ok=True); only a genuine
write failure (permissions, an offline network share) should raise.
"""

from pathlib import Path

import pytest
from lxml import etree

from vra_editor.core.record_transitions import (
    LocationUnavailableError,
    move_to_location,
)


def _make_xml_root():
    return etree.fromstring(b"<work><titleSet><title>Test</title></titleSet></work>")


def _write_source_record(edit_dir: Path, name: str = 'rec1.xml') -> Path:
    edit_dir.mkdir(parents=True, exist_ok=True)
    src = edit_dir / name
    src.write_bytes(etree.tostring(_make_xml_root(), xml_declaration=True, encoding='UTF-8'))
    return src


def test_move_to_location_creates_missing_destination_folder(tmp_path):
    edit_dir = tmp_path / 'edit'
    pending_dir = tmp_path / 'pending'  # deliberately not created
    src = _write_source_record(edit_dir)
    assert not pending_dir.exists()

    result = move_to_location(
        _make_xml_root(), 'pending', {'edit': edit_dir, 'pending': pending_dir},
        src, validator=None, validate=False,
    )

    assert result.success is True
    assert pending_dir.is_dir()
    assert result.dest_path == pending_dir / 'rec1.xml'
    assert result.dest_path.is_file()
    assert not src.exists()  # moved, not copied


def test_move_to_location_creates_missing_nested_destination_folder(tmp_path):
    """A record living in a subfolder (edit/collectionA/rec1.xml)
    should reproduce that same subfolder at the destination, creating
    however many missing directory levels that needs."""
    edit_dir = tmp_path / 'edit'
    pending_dir = tmp_path / 'pending'
    src = _write_source_record(edit_dir / 'collectionA')

    result = move_to_location(
        _make_xml_root(), 'pending', {'edit': edit_dir, 'pending': pending_dir},
        src, validator=None, validate=False,
    )

    assert result.success is True
    assert result.dest_path == pending_dir / 'collectionA' / 'rec1.xml'
    assert result.dest_path.is_file()


def test_move_to_location_returns_false_when_location_not_configured(tmp_path):
    """A [locations] entry that's simply missing from config.ini is a
    Settings problem, not a connectivity one -- reported as a plain
    (False, message) result, never an exception."""
    edit_dir = tmp_path / 'edit'
    src = _write_source_record(edit_dir)

    result = move_to_location(
        _make_xml_root(), 'pending', {'edit': edit_dir},  # no 'pending' key at all
        src, validator=None, validate=False,
    )

    assert result.success is False
    assert 'pending' in result.message
    assert src.exists()  # nothing was touched


def test_move_to_location_raises_location_unavailable_on_real_write_failure(tmp_path):
    """Distinguishes a genuinely unreachable destination (can't be
    written to, e.g. a dead network share) from a merely-missing-but-
    creatable one -- forced here by making the 'destination' path a
    FILE, so mkdir(parents=True) on it fails with a real OSError."""
    edit_dir = tmp_path / 'edit'
    src = _write_source_record(edit_dir)

    blocked_path = tmp_path / 'pending'
    blocked_path.write_text('not a directory')  # occupies the name with a file

    with pytest.raises(LocationUnavailableError):
        move_to_location(
            _make_xml_root(), 'pending', {'edit': edit_dir, 'pending': blocked_path},
            src, validator=None, validate=False,
        )
    assert src.exists()  # the move never happened -- source is untouched


def test_move_to_location_moves_sibling_media_along(tmp_path):
    edit_dir = tmp_path / 'edit'
    pending_dir = tmp_path / 'pending'  # missing -- also exercises the create-on-demand path
    src = _write_source_record(edit_dir)
    media = edit_dir / 'rec1.tif'
    media.write_bytes(b'fake image data')

    result = move_to_location(
        _make_xml_root(), 'pending', {'edit': edit_dir, 'pending': pending_dir},
        src, validator=None, validate=False,
    )

    assert result.success is True
    assert (pending_dir / 'rec1.tif').is_file()
    assert not media.exists()
