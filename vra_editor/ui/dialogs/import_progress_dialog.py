from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QProgressBar, QPlainTextEdit, QDialogButtonBox,
)

from vra_editor.config import load_media_extensions
from vra_editor.core.ingest import process_vra_directory


class ImportProgressDialog(QDialog):
    """Runs process_vra_directory (merge same-record-ID files from the
    'ingest' folder into 'edit') and shows live progress.

    Runs synchronously on the GUI thread -- an ingest batch is local
    disk I/O, not a network call, so calling processEvents() from the
    progress callback keeps the window responsive without needing a
    full QThread. Close is disabled until the run finishes so the
    dialog can't be dismissed mid-batch by accident.
    """

    def __init__(self, ingest_dir, edit_dir, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import")
        self.setModal(True)
        self.resize(560, 400)

        self.ingest_dir = ingest_dir
        self.edit_dir = edit_dir

        layout = QVBoxLayout(self)

        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Close)
        self.buttons.rejected.connect(self.accept)
        self.buttons.button(QDialogButtonBox.Close).setEnabled(False)
        layout.addWidget(self.buttons)

        # Let the dialog paint itself before the (blocking) run starts.
        QTimer.singleShot(0, self._run)

    def _run(self):
        try:
            process_vra_directory(
                str(self.ingest_dir), str(self.edit_dir),
                progress_callback=self._on_progress,
                media_extensions=load_media_extensions(),
            )
        except Exception as e:
            self._log(f" [!] Import failed: {e}")
        self.buttons.button(QDialogButtonBox.Close).setEnabled(True)

    def _on_progress(self, current: int, total: int, message: str):
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(current)
        else:
            self.progress_bar.setRange(0, 0)  # indeterminate -- shown during the initial scan
        self._log(message)
        QApplication.processEvents()

    def _log(self, message: str):
        self.log_view.appendPlainText(message)
