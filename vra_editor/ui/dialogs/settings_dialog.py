import configparser
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QDialog, QWidget, QFormLayout, QVBoxLayout, QHBoxLayout,
    QLineEdit, QCheckBox, QPushButton, QFileDialog, QLabel,
    QDialogButtonBox, QGroupBox, QMessageBox,
)

from ...app_data import BOOTSTRAP_DIR
from ...config import (
    DEFAULT_CONFIG_PATH, LOCATION_KEYS, OPTION_TEXT_KEYS,
    to_bool,
)
from ...utils import strip_quotes

# Not an archive workflow stage like the LOCATION_KEYS -- shown in its own
# group in the UI -- but still just a path, saved under the same
# [locations] section so app_data.get_app_data_dir() can read it back
# with the same load_locations() call the archive folders use.
APP_DATA_KEY = 'app_data'

# Human-friendly row labels for LOCATION_KEYS -- config.py and
# document_controller.py use the bare lowercase keys everywhere else,
# but "edit:" on its own doesn't read as a folder setting at a glance.
_LOCATION_LABELS = {
    'edit': 'Edit folder',
    'ingest': 'Ingest folder',
    'pending': 'Pending folder',
    'rejected': 'Rejected folder',
    'reviewed': 'Reviewed folder',
    'released': 'Released folder',
}


# noinspection PyUnresolvedReferences
class SettingsDialog(QDialog):
    """Modal dialog for editing vra-config.ini.

    Usage:
        dlg = SettingsDialog(parent=self)
        dlg.exec()   # modal -- blocks until Save/Cancel
    """

    def __init__(self, config_path: Path = DEFAULT_CONFIG_PATH, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.resize(480, 360)

        self.config_path = config_path
        self._location_edits: dict[str, QLineEdit] = {}
        self._option_edits: dict[str, QLineEdit] = {}
        self.fullname_edit: Optional[QLineEdit] = None
        self.auto_ingest_check: Optional[QCheckBox] = None
        self.app_data_edit: Optional[QLineEdit] = None

        self._build_ui()
        self._load()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        outer = QVBoxLayout(self)

        outer.addWidget(self._build_locations_group())
        outer.addWidget(self._build_app_data_group())
        outer.addWidget(self._build_user_group())
        outer.addWidget(self._build_options_group())

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _build_locations_group(self) -> QGroupBox:
        group = QGroupBox("Locations")
        form = QFormLayout(group)
        # Left-aligned rather than QFormLayout's default of hugging the
        # field, so every label starts at the same left edge -- but that
        # leaves ragged whitespace after the shorter ones (e.g. "Edit
        # folder" next to "Rejected folder"), which is what the dot
        # leader below fills in.
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        metrics = QFontMetrics(self.font())
        widest = max(metrics.horizontalAdvance(f"{lbl} ") for lbl in _LOCATION_LABELS.values())
        dot_width = metrics.horizontalAdvance('.')

        # QLineEdit's own sizeHint (a generic ~125px, unrelated to what
        # it actually renders at) isn't a usable baseline for "50%
        # wider" -- its horizontal Expanding size policy means its real
        # width is whatever's left in the dialog after the label column
        # and Browse button, which is what a scholar actually sees these
        # boxes clipped to. Estimate that leftover directly and widen
        # off of it instead, so setting this minimum actually grows the
        # dialog (QDialog enlarges past resize() to honor a child's
        # minimumWidth) rather than being a no-op inside space it
        # already had.
        browse_width = QPushButton("Browse...").sizeHint().width()
        natural_field_width = self.width() - widest - browse_width - 90
        target_field_width = int(natural_field_width * 1.5)

        for key in LOCATION_KEYS:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)

            edit = QLineEdit()
            edit.setMinimumWidth(target_field_width)
            browse_btn = QPushButton("Browse...")
            browse_btn.setToolTip(f"Choose the {key} folder.")
            browse_btn.clicked.connect(lambda _checked, e=edit: self._browse_for(e))

            row_layout.addWidget(edit)
            row_layout.addWidget(browse_btn)

            self._location_edits[key] = edit

            base = f"{_LOCATION_LABELS.get(key, key)} "
            leader_len = max(int((widest - metrics.horizontalAdvance(base)) / dot_width), 3)
            form.addRow(f"{base}{'.' * leader_len} ", row)

        return group

    def _build_app_data_group(self) -> QGroupBox:
        group = QGroupBox("Application Data")
        form = QFormLayout(group)

        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)

        self.app_data_edit = QLineEdit()
        self.app_data_edit.setPlaceholderText(f"(default: {BOOTSTRAP_DIR})")
        browse_btn = QPushButton("Browse...")
        browse_btn.setToolTip("Choose where this app stores its own files.")
        browse_btn.clicked.connect(lambda: self._browse_for(self.app_data_edit))
        row_layout.addWidget(self.app_data_edit)
        row_layout.addWidget(browse_btn)

        form.addRow("Clutter folder:", row)
        note = QLabel(
            "Where this app keeps its own files -- the edit/review version "
            "history and the vocabulary-lookup cache -- separate from the "
            "archive itself. Leave blank to use the default above."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #666;")
        form.addRow(note)

        return group

    def _build_user_group(self) -> QGroupBox:
        group = QGroupBox("User")
        form = QFormLayout(group)
        self.fullname_edit = QLineEdit()
        form.addRow("Full name:", self.fullname_edit)
        return group

    def _build_options_group(self) -> QGroupBox:
        group = QGroupBox("Options")
        form = QFormLayout(group)

        self.auto_ingest_check = QCheckBox()
        self.auto_ingest_check.setToolTip(
            "Automatically merge newly-arrived source files into the edit "
            "folder, without waiting for Import to be clicked."
        )
        form.addRow("Auto ingest:", self.auto_ingest_check)

        for key in OPTION_TEXT_KEYS:
            edit = QLineEdit()
            self._option_edits[key] = edit
            form.addRow(f"{key}:", edit)

        return group

    def _browse_for(self, line_edit: QLineEdit):
        start_dir = line_edit.text() or str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "Select folder", start_dir)
        if chosen:
            line_edit.setText(chosen)

    # ------------------------------------------------------------------
    # Load / save
    # ------------------------------------------------------------------

    def _load(self):
        parser = configparser.ConfigParser()
        if self.config_path.exists():
            parser.read(self.config_path)

        locations = parser['locations'] if parser.has_section('locations') else {}
        for key, edit in self._location_edits.items():
            edit.setText(locations.get(key, ''))
        self.app_data_edit.setText(locations.get(APP_DATA_KEY, ''))

        user = parser['user'] if parser.has_section('user') else {}
        self.fullname_edit.setText(strip_quotes(user.get('FullName', '')))

        options = parser['options'] if parser.has_section('options') else {}
        self.auto_ingest_check.setChecked(to_bool(options.get('auto_ingest', 'false')))
        for key, edit in self._option_edits.items():
            edit.setText(options.get(key, ''))

    def _on_save(self):
        parser = configparser.ConfigParser()
        parser['locations'] = {
            key: edit.text().strip() for key, edit in self._location_edits.items()
        }
        app_data_path = self.app_data_edit.text().strip()
        if app_data_path:
            # Omitted entirely when blank, not written as app_data= --
            # get_app_data_dir() treats "not in the dict at all" as
            # "use the default", but an empty string would resolve to
            # Path('') instead.
            parser['locations'][APP_DATA_KEY] = app_data_path

        for key, path in parser['locations'].items():
            if not path:
                continue
            try:
                Path(path).mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                QMessageBox.critical(self, "Create dir failed", f"Could not create {path}:\n{exc}")

        parser['user'] = {
            'FullName': self.fullname_edit.text().strip(),
        }
        parser['options'] = {
            'auto_ingest': 'true' if self.auto_ingest_check.isChecked() else 'false',
            **{key: edit.text().strip() for key, edit in self._option_edits.items()},
        }

        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, 'w') as f:
                parser.write(f)
        except OSError as exc:
            QMessageBox.critical(self, "Save failed", f"Could not write {self.config_path}:\n{exc}")
            return

        self.accept()
