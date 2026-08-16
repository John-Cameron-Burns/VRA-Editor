"""DocumentController's advisory locking (core/record_locks.py) --
wired into the desktop app so two people editing the same shared
archive (desktop or web, in any combination) can't silently clobber
each other, the same protection the web app already had. Run headless
(QT_QPA_PLATFORM forced offscreen below, before PySide6 is imported)
since DocumentController is a QObject."""

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path

import pytest
from lxml import etree
from PySide6.QtWidgets import QApplication

from vra_editor.controllers.document_controller import DocumentController
from vra_editor.core import record_locks


@pytest.fixture(scope='module')
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def isolated_lock_store(monkeypatch, tmp_path):
    """try_open_file/release_lock call record_locks with the desktop's
    own default config_path=None (see that module's docstring), which
    would otherwise read/create ~/.vra-editor/cache/record_locks.db on
    whatever machine runs this test. Redirect it to a throwaway
    per-test directory instead."""
    monkeypatch.setattr(record_locks, 'get_cache_dir', lambda config_path=None: tmp_path / 'lock-cache')


def _write_record(path, title='Test'):
    path.parent.mkdir(parents=True, exist_ok=True)
    root = etree.fromstring(f"<work><titleSet><title>{title}</title></titleSet></work>".encode())
    path.write_bytes(etree.tostring(root, xml_declaration=True, encoding='UTF-8'))


def test_try_open_file_acquires_the_lock(qapp, tmp_path):
    record = tmp_path / 'rec1.xml'
    _write_record(record)
    controller = DocumentController()

    ok, message = controller.try_open_file(str(record))
    assert (ok, message) == (True, "")
    assert controller.current_file == str(record)
    status = record_locks.status(record)
    assert status is not None and not status['expired']


def test_try_open_file_is_refused_when_someone_else_holds_it(qapp, tmp_path):
    record = tmp_path / 'rec1.xml'
    _write_record(record)
    record_locks.acquire(record, 'mdoe')
    controller = DocumentController()

    ok, holder = controller.try_open_file(str(record))
    assert (ok, holder) == (False, 'mdoe')
    assert controller.current_file is None  # refused -- nothing was loaded


def test_release_lock_frees_it(qapp, tmp_path):
    record = tmp_path / 'rec1.xml'
    _write_record(record)
    controller = DocumentController()
    controller.try_open_file(str(record))

    controller.release_lock()
    assert record_locks.status(record) is None


def test_opening_a_second_record_releases_the_first(qapp, tmp_path):
    record1 = tmp_path / 'rec1.xml'
    record2 = tmp_path / 'rec2.xml'
    _write_record(record1)
    _write_record(record2)
    controller = DocumentController()
    controller.try_open_file(str(record1))

    controller.try_open_file(str(record2))
    assert record_locks.status(record1) is None
    status2 = record_locks.status(record2)
    assert status2 is not None and not status2['expired']


def test_clear_releases_the_lock(qapp, tmp_path):
    record = tmp_path / 'rec1.xml'
    _write_record(record)
    controller = DocumentController()
    controller.try_open_file(str(record))

    controller.clear()
    assert record_locks.status(record) is None


def test_create_new_record_releases_a_previously_held_lock(qapp, tmp_path):
    record = tmp_path / 'rec1.xml'
    _write_record(record)
    controller = DocumentController()
    controller.try_open_file(str(record))

    controller.create_new_record('work', 'newrec', tmp_path / 'newrec.xml')
    assert record_locks.status(record) is None


def test_heartbeat_emits_lock_lost_once_the_lock_is_gone(qapp, tmp_path):
    record = tmp_path / 'rec1.xml'
    _write_record(record)
    controller = DocumentController()
    controller.try_open_file(str(record))

    # Simulate the lock expiring and someone else taking it over --
    # same end state LOCK_TTL_SECONDS elapsing for real would produce.
    record_locks.release(record, controller._lock_holder)
    record_locks.acquire(record, 'mdoe')

    lost = []
    controller.lock_lost.connect(lambda: lost.append(True))
    controller._do_heartbeat()
    assert lost == [True]


def test_heartbeat_is_a_no_op_when_nothing_is_locked(qapp, tmp_path):
    controller = DocumentController()
    lost = []
    controller.lock_lost.connect(lambda: lost.append(True))
    controller._do_heartbeat()  # should not raise or emit
    assert lost == []


def test_submit_releases_the_lock_on_the_old_path(qapp, tmp_path, monkeypatch):
    """The trickiest wiring point: after a successful Submit the record
    lives at a new path (edit -> pending), so the lock held at the old
    path must be released -- there's nothing left there to protect,
    and nobody re-acquires the new path either (matching the web app's
    own submit_record, which doesn't re-lock 'pending' on the
    editor's behalf)."""
    import vra_editor.controllers.document_controller as dc_module
    from conftest import write_sample_record

    edit_dir, pending_dir = tmp_path / 'edit', tmp_path / 'pending'
    record = write_sample_record(edit_dir, 'rec1', 'Test')  # schema-valid -- Submit validates
    monkeypatch.setattr(dc_module, 'load_locations', lambda: {'edit': edit_dir, 'pending': pending_dir})
    monkeypatch.setattr(dc_module, 'load_media_extensions', lambda: ())

    controller = DocumentController()
    controller.try_open_file(str(record))
    ok, dest = controller.submit_file()

    assert ok is True
    assert record_locks.status(record) is None
    assert record_locks.status(Path(dest)) is None
