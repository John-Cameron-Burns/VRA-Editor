from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QDialogButtonBox, QAbstractItemView,
)

from vra_editor.core import record_locks
from vra_editor.core.record_titles import extract_title, human_size


class VraFilePickerDialog(QDialog):
    """Modal file picker restricted to one or more folders (including
    their subfolders -- e.g. records Import filed under
    edit/collectionA/ are still found here, not just ones sitting flat
    in edit/ itself), listing each record's parsed VRA title next to
    its path.

    directory is either a single Path (the common case), or {label:
    Path} to merge several locations into one list -- e.g. Open
    browsing both 'edit' and 'rejected' together, so a record a
    reviewer sent back has somewhere it can be reopened from (see
    main_window._on_open). Either way, XML listings get a Status
    column: the source label (when merged), a "Locked by ..." note
    (see core/record_locks.py) if someone else already has that record
    open, or both. This is just a hint -- opening a locked record is
    actually refused where it's requested (main_window._open_from_folder),
    not prevented here.

    Usage:
        dlg = VraFilePickerDialog(directory=locations['edit'], parent=self)
        if dlg.exec() == QDialog.Accepted:
            path = dlg.selected_path
    """

    def __init__(self, directory: Path | dict[str, Path], title: str = "Select record", parent=None,
                 file_filter: str | list[str] = "*.xml"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(560, 420)

        self.sources: dict[str, Path] = directory if isinstance(directory, dict) else {'': directory}
        self.file_filters = [file_filter] if isinstance(file_filter, str) else list(file_filter)
        self.selected_path: Path | None = None
        self._show_source_label = len(self.sources) > 1
        # Locks are a record (XML) concept -- meaningless for a non-XML
        # filter, e.g. browsing for an image file to link.
        self._is_xml = self.file_filters == ['*.xml']
        self._show_status = self._show_source_label or self._is_xml

        layout = QVBoxLayout(self)

        folders_text = ', '.join(str(d) for d in self.sources.values())
        self.info_label = QLabel(f"Folder: {folders_text}")
        layout.addWidget(self.info_label)

        # The second column parses each file as VRA XML for a title preview
        # -- meaningless (and wasted work) for a non-XML filter, e.g. picking
        # an image file, so it becomes a plain file-size column instead.
        is_xml = self._is_xml
        columns = (['File', 'Title'] if is_xml else ['File', 'Size']) + (['Status'] if self._show_status else [])
        self.table = QTableWidget(0, len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.itemDoubleClicked.connect(self._accept_selection)
        layout.addWidget(self.table)

        buttons = QDialogButtonBox(QDialogButtonBox.Open | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept_selection)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._populate()

    def _populate(self):
        self.table.setRowCount(0)

        existing = {label: folder for label, folder in self.sources.items() if folder.exists()}
        if not existing:
            missing = ', '.join(str(d) for d in self.sources.values())
            self.info_label.setText(f"Folder not found: {missing}")
            return

        is_xml = self.file_filters == ['*.xml']
        rows = []  # (label, folder, path)
        for label, folder in existing.items():
            seen = set()
            for pattern in self.file_filters:
                for path in folder.rglob(pattern):
                    if path not in seen:
                        seen.add(path)
                        rows.append((label, folder, path))
        # Grouped by source label first (a no-op when there's only one,
        # keeping the original single-folder ordering unchanged), then
        # by path within it.
        rows.sort(key=lambda r: (r[0], r[2]))

        self.table.setRowCount(len(rows))
        for row, (label, folder, path) in enumerate(rows):
            # Relative path, not just the filename -- otherwise two
            # records in different subfolders (or a subfolder and the
            # root) would be indistinguishable in the list.
            file_item = QTableWidgetItem(str(path.relative_to(folder)))
            file_item.setData(Qt.UserRole, str(path))
            second_item = QTableWidgetItem(extract_title(path) if is_xml else human_size(path.stat().st_size))
            self.table.setItem(row, 0, file_item)
            self.table.setItem(row, 1, second_item)
            if self._show_status:
                self.table.setItem(row, 2, QTableWidgetItem(self._status_text(label, path)))

        if rows:
            self.table.selectRow(0)

    def _status_text(self, label: str, path: Path) -> str:
        parts = [label] if self._show_source_label and label else []
        if self._is_xml:
            lock = record_locks.status(path)
            if lock and not lock['expired']:
                parts.append(f"Locked by {lock['holder']}")
        return ' — '.join(parts)

    def _accept_selection(self, *_ignored):
        row = self.table.currentRow()
        if row < 0:
            return
        path_str = self.table.item(row, 0).data(Qt.UserRole)
        self.selected_path = Path(path_str)
        self.accept()
