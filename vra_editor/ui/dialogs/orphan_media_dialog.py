from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QDialogButtonBox, QMessageBox,
)

from vra_editor.core import ingest_ignored_cache
from vra_editor.core.ingest import stash_orphan_media

_LEAVE = 'Leave for now'
_STASH = 'Stash to done/'
_IGNORE = "Ignore (don't ask again)"
_ACTIONS = [_LEAVE, _STASH, _IGNORE]


class OrphanMediaDialog(QDialog):
    """Shown after an Import run finds media files with no matching VRA
    record (see process_vra_directory's return value) -- offers a
    per-file choice instead of just leaving them silently in the ingest
    folder forever. Leave for now: no change, reported again next
    Import. Stash to done/: moved into ingest's own done/ folder via
    stash_orphan_media, out of the way, mirroring how a normally-
    consumed source's sibling media is handled. Ignore: recorded by
    content hash in core/ingest_ignored_cache.py, so it stops being
    reported at all -- for a file that's meant to stay exactly where
    it is, with nothing moved.
    """

    def __init__(self, orphans: list, input_dir, parent=None):
        super().__init__(parent)
        self._orphans = list(orphans)
        self._input_dir = Path(input_dir)

        self.setWindowTitle("Leftover Files in Ingest")
        self.setModal(True)
        self.resize(560, 320)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            f"{len(self._orphans)} file(s) in the ingest folder don't match any VRA "
            f"record, and were left in place. Choose what to do with each:"
        ))

        self.table = QTableWidget(len(self._orphans), 2)
        self.table.setHorizontalHeaderLabels(['File', 'Action'])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)

        self._combos = []
        for row, path in enumerate(self._orphans):
            try:
                rel = path.relative_to(self._input_dir)
            except ValueError:
                rel = path
            self.table.setItem(row, 0, QTableWidgetItem(str(rel)))
            combo = QComboBox()
            combo.addItems(_ACTIONS)
            self.table.setCellWidget(row, 1, combo)
            self._combos.append(combo)
        layout.addWidget(self.table)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self._on_apply)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def _on_apply(self):
        errors = []
        for path, combo in zip(self._orphans, self._combos):
            choice = combo.currentText()
            try:
                if choice == _STASH:
                    stash_orphan_media(path, self._input_dir)
                elif choice == _IGNORE:
                    ingest_ignored_cache.mark_ignored(path)
            except Exception as exc:
                errors.append(f"{path.name}: {exc}")
        if errors:
            QMessageBox.warning(self, "Some actions failed", "\n".join(errors))
        self.accept()
