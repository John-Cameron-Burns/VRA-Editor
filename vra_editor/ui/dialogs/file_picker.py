import xml.etree.ElementTree as ET
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QDialogButtonBox, QAbstractItemView,
)


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


def _human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if size < 1024 or unit == 'GB':
            return f"{size:.0f} {unit}" if unit == 'B' else f"{size:.1f} {unit}"
        size /= 1024


class VraFilePickerDialog(QDialog):
    """Modal file picker restricted to a single folder, listing each
    record's parsed VRA title next to its filename.

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
            for path in self.directory.glob(pattern):
                if path not in seen:
                    seen.add(path)
                    files.append(path)
        files.sort()
        self.table.setRowCount(len(files))
        for row, path in enumerate(files):
            file_item = QTableWidgetItem(path.name)
            file_item.setData(Qt.UserRole, str(path))
            second_item = QTableWidgetItem(extract_title(path) if is_xml else _human_size(path.stat().st_size))
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
