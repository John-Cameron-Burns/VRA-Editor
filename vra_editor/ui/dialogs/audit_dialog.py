from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox, QInputDialog,
)

from vra_editor.config import load_locations
from vra_editor.core import audit_log

_COLUMNS = ['Filename', 'User', 'Date']


class AuditDialog(QDialog):
    """Lists every revision in the archive's shared git history (see
    core/audit_log.py and core/commit_to_git.py) -- one row per file
    changed in a commit, most recent first -- with a filter box and a
    button to restore the selected revision's content into a new file
    under the 'edit' location.

    Modal: this is a lookup-and-act dialog, not a reference to keep
    open on the side like Help. Doesn't own the actual restore -- it
    only picks a revision and a destination filename, then emits
    restore_requested so the caller (MainWindow) can run the same
    unsaved-changes guard Open/Create/Review already go through before
    replacing the currently-open document.
    """

    restore_requested = Signal(object, str)  # Revision, destination path

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Audits")
        self.setModal(True)
        self.resize(760, 480)

        self._all_revisions: list[audit_log.Revision] = []

        layout = QVBoxLayout(self)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filter:"))
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Filename contains...")
        self.filter_input.textChanged.connect(self._apply_filter)
        filter_row.addWidget(self.filter_input, stretch=1)
        refresh_button = QPushButton("Refresh")
        refresh_button.setToolTip("Re-read the archive's history -- in case a change was just committed.")
        refresh_button.clicked.connect(self._load_revisions)
        filter_row.addWidget(refresh_button)
        layout.addLayout(filter_row)

        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._on_restore_clicked)
        layout.addWidget(self.table, stretch=1)

        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: #888;")
        layout.addWidget(self.status_label)

        button_row = QHBoxLayout()
        button_row.addStretch()
        self.restore_button = QPushButton("Restore to New File...")
        self.restore_button.setToolTip(
            "Writes this revision's content to a new file in the edit "
            "folder (never overwrites anything) and opens it."
        )
        self.restore_button.clicked.connect(self._on_restore_clicked)
        button_row.addWidget(self.restore_button)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.reject)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)

        self._load_revisions()

    def _load_revisions(self):
        self._all_revisions = audit_log.list_revisions()
        self._apply_filter()

    def _apply_filter(self):
        query = self.filter_input.text().strip().lower()
        revisions = [r for r in self._all_revisions if query in r.filename.lower()] \
            if query else self._all_revisions
        self._populate_table(revisions)

    def _populate_table(self, revisions: list):
        self.table.setRowCount(len(revisions))
        for row, rev in enumerate(revisions):
            filename_item = QTableWidgetItem(rev.filename)
            filename_item.setData(Qt.ItemDataRole.UserRole, rev)
            self.table.setItem(row, 0, filename_item)
            self.table.setItem(row, 1, QTableWidgetItem(rev.author))
            self.table.setItem(row, 2, QTableWidgetItem(rev.date.strftime('%Y-%m-%d %H:%M')))

        if not self._all_revisions:
            self.status_label.setText(
                "No history yet -- revisions appear here after Save/Submit/Approve/Reject "
                "are given a commit comment."
            )
        else:
            self.status_label.setText(f"{len(revisions)} of {len(self._all_revisions)} revision(s)")

    def _on_restore_clicked(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "No revision selected", "Select a revision first.")
            return
        revision = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)

        edit_dir = load_locations().get('edit')
        if edit_dir is None:
            QMessageBox.warning(self, "Missing location", "No 'edit' folder is configured in vra-config.ini.")
            return

        default_name = Path(revision.filename).name
        new_name, ok = QInputDialog.getText(
            self, "Restore into new file", "Filename:", text=default_name,
        )
        if not ok:
            return
        new_name = new_name.strip()
        if not new_name:
            return
        if any(sep in new_name for sep in ('/', '\\')):
            QMessageBox.warning(self, "Invalid name", "The filename can't contain '/' or '\\'.")
            return

        dest_path = edit_dir / new_name
        if dest_path.exists():
            QMessageBox.warning(
                self, "File already exists",
                f'"{new_name}" already exists in the edit folder. Pick a different name and try again.',
            )
            return

        self.restore_requested.emit(revision, str(dest_path))
