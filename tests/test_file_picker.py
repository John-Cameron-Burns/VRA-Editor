"""VraFilePickerDialog's merged-sources mode (see main_window._on_open,
which now browses 'edit' and 'rejected' together so a record a
reviewer sent back has somewhere it can be reopened from). Run
headless -- QT_QPA_PLATFORM is forced to 'offscreen' below, before
PySide6 is imported, so these don't need a real display."""

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtWidgets import QApplication

from vra_editor.ui.dialogs.file_picker import VraFilePickerDialog


@pytest.fixture(scope='module')
def qapp():
    return QApplication.instance() or QApplication([])


def _write_record(folder, name):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text('<work/>')


def test_single_folder_has_no_status_column(qapp, tmp_path):
    edit_dir = tmp_path / 'edit'
    _write_record(edit_dir, 'rec1.xml')

    dlg = VraFilePickerDialog(directory=edit_dir, file_filter='*.xml')
    assert dlg.table.columnCount() == 2
    assert dlg.table.rowCount() == 1


def test_merged_sources_get_a_status_column_and_labels(qapp, tmp_path):
    edit_dir = tmp_path / 'edit'
    rejected_dir = tmp_path / 'rejected'
    _write_record(edit_dir, 'rec1.xml')
    _write_record(rejected_dir, 'rec2.xml')

    dlg = VraFilePickerDialog(
        directory={'Editable': edit_dir, 'Rejected': rejected_dir}, file_filter='*.xml',
    )
    assert dlg.table.columnCount() == 3
    assert dlg.table.rowCount() == 2
    labels = {dlg.table.item(row, 0).text(): dlg.table.item(row, 2).text() for row in range(dlg.table.rowCount())}
    assert labels == {'rec1.xml': 'Editable', 'rec2.xml': 'Rejected'}


def test_merged_sources_tolerates_one_missing_folder(qapp, tmp_path):
    edit_dir = tmp_path / 'edit'
    _write_record(edit_dir, 'rec1.xml')

    dlg = VraFilePickerDialog(
        directory={'Editable': edit_dir, 'Rejected': tmp_path / 'rejected'}, file_filter='*.xml',
    )
    assert dlg.table.rowCount() == 1


def test_missing_folder_message_lists_every_missing_source(qapp, tmp_path):
    dlg = VraFilePickerDialog(directory={'Editable': tmp_path / 'nope1', 'Rejected': tmp_path / 'nope2'})
    assert 'not found' in dlg.info_label.text().lower()
    assert dlg.table.rowCount() == 0


def test_selecting_a_row_sets_selected_path_on_accept(qapp, tmp_path):
    edit_dir = tmp_path / 'edit'
    rejected_dir = tmp_path / 'rejected'
    _write_record(edit_dir, 'rec1.xml')
    _write_record(rejected_dir, 'rec2.xml')
    rejected_path = rejected_dir / 'rec2.xml'

    dlg = VraFilePickerDialog(directory={'Editable': edit_dir, 'Rejected': rejected_dir}, file_filter='*.xml')
    row = next(r for r in range(dlg.table.rowCount()) if dlg.table.item(r, 0).text() == 'rec2.xml')
    dlg.table.selectRow(row)
    dlg._accept_selection()
    assert dlg.selected_path == rejected_path
