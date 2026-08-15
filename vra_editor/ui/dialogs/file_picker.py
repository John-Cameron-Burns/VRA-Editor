from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QDialogButtonBox, QAbstractItemView,
)

from vra_editor.core.record_titles import extract_title, human_size


class VraFilePickerDialog(QDialog):
    """Modal file picker restricted to a single folder (including its
    subfolders -- e.g. records Import filed under edit/collectionA/ are
    still found here, not just ones sitting flat in edit/ itself),
    listing each record's parsed VRA title next to its path.

    Usage:
        dlg = VraFilePickerDialog(directory=locations['edit'], parent=self)
        if dlg.exec() == QDialog.Accepted:
            path = dlg.selected_path
    """

    def __init__(self, directory: Path, title: str = "Select record", parent=None,
                 file_filter: str | list[str] = "*.xml"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(560, 420)

        self.directory = directory
        self.file_filters = [file_filter] if isinstance(file_filter, str) else list(file_filter)
        self.selected_path: Path | None = None

        layout = QVBoxLayout(self)

        self.info_label = QLabel(f"Folder: {directory}")
        layout.addWidget(self.info_label)

        # The second column parses each file as VRA XML for a title preview
        # -- meaningless (and wasted work) for a non-XML filter, e.g. picking
        # an image file, so it becomes a plain file-size column instead.
        is_xml = self.file_filters == ['*.xml']
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(['File', 'Title'] if is_xml else ['File', 'Size'])
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

        if not self.directory.exists():
            self.info_label.setText(f"Folder not found: {self.directory}")
            return

        is_xml = self.file_filters == ['*.xml']
        seen = set()
        files = []
        for pattern in self.file_filters:
            for path in self.directory.rglob(pattern):
                if path not in seen:
                    seen.add(path)
                    files.append(path)
        files.sort()
        self.table.setRowCount(len(files))
        for row, path in enumerate(files):
            # Relative path, not just the filename -- otherwise two
            # records in different subfolders (or a subfolder and the
            # root) would be indistinguishable in the list.
            file_item = QTableWidgetItem(str(path.relative_to(self.directory)))
            file_item.setData(Qt.UserRole, str(path))
            second_item = QTableWidgetItem(extract_title(path) if is_xml else human_size(path.stat().st_size))
            self.table.setItem(row, 0, file_item)
            self.table.setItem(row, 1, second_item)

        if files:
            self.table.selectRow(0)

    def _accept_selection(self, *_ignored):
        row = self.table.currentRow()
        if row < 0:
            return
        path_str = self.table.item(row, 0).data(Qt.UserRole)
        self.selected_path = Path(path_str)
        self.accept()
