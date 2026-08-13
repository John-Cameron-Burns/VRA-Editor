from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox,
)

from vra_editor.core import offline_staging

_COLUMNS = ['Record', 'Status']

_STATUS_LABELS = {
    'new': 'New (offline)',
    'updated': 'Updated (offline)',
    'conflict': 'Conflict',
    'removed_on_primary': 'Removed from primary',
}

_RESOLVABLE_STATUSES = ('conflict', 'removed_on_primary')


class OfflineReconcileDialog(QDialog):
    """Lists every record that needs attention to fold offline edits
    (see core/offline_staging.py) back into the primary 'edit' folder --
    one row per record, most of the archive not shown at all, since an
    untouched record has nothing to reconcile.

    'New'/'Updated' rows are safe to apply automatically (nothing
    changed on primary in the meantime); 'Conflict'/'Removed from
    primary' rows need a human's call, made via a manually-built
    QMessageBox (Keep Local / Keep Primary / Skip) -- same
    multi-choice-confirmation style as MainWindow's
    _confirm_discard_if_dirty, not QMessageBox.question(), which this
    app never uses.

    Runs synchronously -- plan_reconciliation reads a bounded set of
    already-known files (whatever's in the staging folder), the same
    order of magnitude as an Import batch, so no progress pump is
    needed the way ImportProgressDialog's real-directory-scan one is.
    """

    def __init__(self, staging_dir: Path, primary_dir: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Reconcile Offline Changes")
        self.setModal(True)
        self.resize(760, 480)

        self.staging_dir = Path(staging_dir)
        self.primary_dir = Path(primary_dir)
        self._all_items: list[offline_staging.ReconcileItem] = []

        layout = QVBoxLayout(self)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filter:"))
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Filename contains...")
        self.filter_input.textChanged.connect(self._apply_filter)
        filter_row.addWidget(self.filter_input, stretch=1)
        refresh_button = QPushButton("Refresh")
        refresh_button.setToolTip("Re-compare against primary's current state.")
        refresh_button.clicked.connect(self._reload)
        filter_row.addWidget(refresh_button)
        layout.addLayout(filter_row)

        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._on_resolve_clicked)
        layout.addWidget(self.table, stretch=1)

        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: #888;")
        layout.addWidget(self.status_label)

        button_row = QHBoxLayout()
        self.apply_clean_button = QPushButton("Apply Clean Changes")
        self.apply_clean_button.setToolTip(
            "Copies every 'New'/'Updated' record into the primary folder. "
            "Conflicts are left for you to resolve individually."
        )
        self.apply_clean_button.clicked.connect(self._on_apply_clean_clicked)
        button_row.addWidget(self.apply_clean_button)
        self.resolve_button = QPushButton("Resolve...")
        self.resolve_button.setToolTip("Choose how to resolve the selected conflict.")
        self.resolve_button.clicked.connect(self._on_resolve_clicked)
        button_row.addWidget(self.resolve_button)
        button_row.addStretch()
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)

        self._reload()

    def _reload(self):
        self._all_items = offline_staging.plan_reconciliation(self.staging_dir, self.primary_dir)
        self._apply_filter()

    def _apply_filter(self):
        query = self.filter_input.text().strip().lower()
        items = [i for i in self._all_items if query in str(i.relative_path).lower()] \
            if query else self._all_items
        self._populate_table(items)

    def _populate_table(self, items: list):
        self.table.setRowCount(len(items))
        for row, item in enumerate(items):
            path_item = QTableWidgetItem(str(item.relative_path))
            path_item.setData(Qt.ItemDataRole.UserRole, item)
            self.table.setItem(row, 0, path_item)
            self.table.setItem(row, 1, QTableWidgetItem(_STATUS_LABELS.get(item.status, item.status)))

        if not self._all_items:
            self.status_label.setText("Nothing to reconcile -- primary already matches your offline edits.")
        else:
            self.status_label.setText(f"{len(items)} of {len(self._all_items)} record(s)")

    def _on_apply_clean_clicked(self):
        applied, failed = offline_staging.apply_clean(self._all_items, self.staging_dir, self.primary_dir)
        if failed:
            details = "\n".join(f"{item.relative_path}: {error}" for item, error in failed)
            QMessageBox.warning(
                self, "Some records couldn't be applied",
                f"{len(applied)} record(s) were applied, but {len(failed)} failed "
                f"(primary may have become unreachable partway through):\n\n{details}",
            )
        elif applied:
            QMessageBox.information(self, "Applied", f"{len(applied)} record(s) applied to primary.")
        else:
            QMessageBox.information(self, "Nothing to apply", "No 'New'/'Updated' records to apply right now.")
        self._reload()

    def _on_resolve_clicked(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "No record selected", "Select a conflict to resolve first.")
            return
        item = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        if item.status not in _RESOLVABLE_STATUSES:
            QMessageBox.information(
                self, "Nothing to resolve",
                f'"{item.relative_path}" is a clean {_STATUS_LABELS.get(item.status, item.status).lower()} -- '
                'use "Apply Clean Changes" for this one.',
            )
            return

        box = QMessageBox(
            QMessageBox.Icon.Warning, f"Conflict: {item.relative_path}",
            self._conflict_body_text(item),
            parent=self,
        )
        keep_local_btn = box.addButton("Keep Local", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Keep Primary", QMessageBox.ButtonRole.DestructiveRole)
        cancel_btn = box.addButton("Skip for Now", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel_btn)
        box.exec()
        clicked = box.clickedButton()
        if clicked is cancel_btn:
            return
        choice = 'keep_local' if clicked is keep_local_btn else 'keep_primary'
        offline_staging.apply_resolution(item, choice, self.staging_dir, self.primary_dir)
        self._reload()

    @staticmethod
    def _conflict_body_text(item) -> str:
        if item.status == 'removed_on_primary':
            return (
                "This record was edited offline, but is no longer in the primary folder "
                "(it may have been approved, rejected, or removed while you were away).\n\n"
                "Keep Local restores it to primary with your offline edit. "
                "Keep Primary accepts that it's gone, and discards your offline edit."
            )
        return (
            "This record was edited both offline and on primary (or something with the same "
            "filename was created independently on both sides) since staging began.\n\n"
            "Keep Local overwrites primary with your offline version. "
            "Keep Primary discards your offline edit and updates your local copy to match primary."
        )
