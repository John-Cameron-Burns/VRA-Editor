import configparser
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QDialog, QWidget, QFormLayout, QVBoxLayout, QHBoxLayout,
    QLineEdit, QCheckBox, QPushButton, QFileDialog, QLabel,
    QDialogButtonBox, QGroupBox, QMessageBox, QTabWidget,
)

from ...app_data import BOOTSTRAP_DIR
from ...config import (
    DEFAULT_CONFIG_PATH, LOCATION_KEYS, OPTION_TEXT_KEYS,
    to_bool,
)
from ...core import archive_signature, offline_staging
from ...core.media_files import DEFAULT_MEDIA_EXTENSIONS
from ...utils import strip_quotes
from .install_web_app_dialog import InstallWebAppDialog
from .offline_reconcile_dialog import OfflineReconcileDialog

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
        # Tabbed rather than one long stack of groups -- with every
        # section visible at once, this dialog outgrew a lot of screens
        # entirely (no scroll area either, so Web Server -- the last
        # group -- became unreachable). Only one tab's content
        # contributes to the visible height at a time now.
        self.resize(560, 440)

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

        tabs = QTabWidget()
        tabs.addTab(self._build_locations_tab(), "Locations")
        tabs.addTab(self._build_offline_tab(), "Offline Work")
        tabs.addTab(self._build_user_options_tab(), "User && Options")
        tabs.addTab(self._build_web_app_tab(), "Web Server")
        outer.addWidget(tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _build_locations_tab(self) -> QWidget:
        # Clutter folder first, archive folders below it -- setting the
        # former immediately tries to auto-fill the latter (see
        # _auto_detect_sibling_locations), so it reads top-to-bottom as
        # cause then effect.
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(self._build_app_data_group())
        layout.addWidget(self._build_locations_group())
        layout.addStretch()
        return tab

    def _build_offline_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self._populate_offline_layout(layout)
        layout.addStretch()
        return tab

    def _build_user_options_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(self._build_user_group())
        layout.addWidget(self._build_options_group())
        layout.addStretch()
        return tab

    def _build_web_app_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self._populate_web_app_layout(layout)
        layout.addStretch()
        return tab

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
        browse_btn.clicked.connect(self._on_browse_app_data)
        self.app_data_edit.editingFinished.connect(self._auto_detect_sibling_locations)
        row_layout.addWidget(self.app_data_edit)
        row_layout.addWidget(browse_btn)

        form.addRow("Clutter folder:", row)
        note = QLabel(
            "Where this app keeps its own files -- the edit/review version "
            "history and the vocabulary-lookup cache -- separate from the "
            "archive itself. Leave blank to use the default above. Setting "
            "this to an existing archive's folder automatically fills in any "
            "of the folders below that are still blank and found nearby -- "
            "as siblings or as children of this folder."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #666;")
        form.addRow(note)

        return group

    def _on_browse_app_data(self):
        self._browse_for(self.app_data_edit)
        self._auto_detect_sibling_locations()

    def _auto_detect_sibling_locations(self):
        """Fills in any still-blank archive-folder field whose name
        (edit/ingest/pending/rejected/reviewed/released) is found as a
        sibling or a child of the clutter folder just set -- sibling
        checked first, so a flat archive layout wins over a candidate
        nested inside the clutter folder itself. Never overwrites a
        field that already has something in it.

        A same-named folder alone isn't trusted blindly: if either the
        clutter folder or an earlier-matched candidate already carries
        an archive_signature, later candidates must carry the same one
        to be accepted -- otherwise a coincidentally-named folder from
        an unrelated archive could get silently wired in. With no
        signature anywhere yet (a fresh archive, nothing saved through
        this feature before), falls back to a plain name match."""
        app_data_text = self.app_data_edit.text().strip()
        if not app_data_text:
            return
        app_data_path = Path(app_data_text)
        if not app_data_path.is_dir():
            return

        inferred_id = archive_signature.read_signature(app_data_path)

        for base in (app_data_path.parent, app_data_path):
            try:
                entries = {entry.name.lower(): entry for entry in base.iterdir() if entry.is_dir()}
            except OSError:
                continue
            for key in LOCATION_KEYS:
                edit = self._location_edits[key]
                if edit.text().strip():
                    continue
                candidate = entries.get(key)
                if candidate is None:
                    continue
                candidate_id = archive_signature.read_signature(candidate)
                if inferred_id is not None:
                    if candidate_id != inferred_id:
                        continue
                elif candidate_id is not None:
                    inferred_id = candidate_id
                edit.setText(str(candidate))

    def _populate_offline_layout(self, layout: QVBoxLayout):
        note = QLabel(
            "For working with no network at all (e.g. a field trip): copies "
            "the Edit folder above to a local folder and points Edit at it, "
            "then folds your offline edits back in once you're back online."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #666;")
        layout.addWidget(note)

        button_row = QHBoxLayout()
        start_button = QPushButton("Start Offline Staging...")
        start_button.setToolTip(
            "Copies the Edit folder to a local folder you choose, and points Edit at it."
        )
        start_button.clicked.connect(self._on_start_staging)
        button_row.addWidget(start_button)
        reconcile_button = QPushButton("Reconcile Offline Changes...")
        reconcile_button.setToolTip(
            "Folds edits made in a staging folder back into the real Edit folder."
        )
        reconcile_button.clicked.connect(self._on_reconcile_offline)
        button_row.addWidget(reconcile_button)
        button_row.addStretch()
        layout.addLayout(button_row)

    def _on_start_staging(self):
        primary = self._location_edits['edit'].text().strip()
        if not primary:
            QMessageBox.warning(
                self, "No Edit folder set", "Set the Edit folder above (and Save) before staging offline.",
            )
            return
        primary_path = Path(primary)
        if not primary_path.is_dir():
            QMessageBox.warning(
                self, "Edit folder not found", f"{primary_path} doesn't exist or isn't reachable right now.",
            )
            return

        chosen = QFileDialog.getExistingDirectory(
            self, "Choose a local folder for offline staging", str(Path.home()),
        )
        if not chosen:
            return
        staging_path = Path(chosen)

        try:
            offline_staging.start_staging(primary_path, staging_path)
        except OSError as e:
            QMessageBox.critical(self, "Couldn't start staging", str(e))
            return

        self._location_edits['edit'].setText(str(staging_path / offline_staging.LIVE_SUBDIR))
        QMessageBox.information(
            self, "Offline staging ready",
            f"Copied the Edit folder to {staging_path}.\n\n"
            "Click Save below to actually switch Edit over to it. When you're back "
            "online, come back here and use \"Reconcile Offline Changes...\" -- it "
            f"remembers the original Edit folder ({primary_path}) for you.",
        )

    def _on_reconcile_offline(self):
        current_edit = self._location_edits['edit'].text().strip()
        if not current_edit:
            QMessageBox.warning(self, "No Edit folder set", "Set the Edit folder above first.")
            return

        staging_dir = Path(current_edit)
        # "Start Offline Staging..." points Edit at staging_dir/edit (the
        # live working copy) -- the staging folder itself, which is what
        # read_staging_origin needs, is that path's parent.
        if staging_dir.name == offline_staging.LIVE_SUBDIR:
            staging_dir = staging_dir.parent
        primary_dir = offline_staging.read_staging_origin(staging_dir)
        if primary_dir is None:
            QMessageBox.warning(
                self, "Not an offline staging folder",
                f'"{current_edit}" doesn\'t look like it was created by "Start Offline '
                'Staging..." -- there\'s nothing to reconcile.',
            )
            return

        dlg = OfflineReconcileDialog(staging_dir, primary_dir, parent=self)
        dlg.exec()

        box = QMessageBox(
            QMessageBox.Icon.Question, "Switch back to the primary folder?",
            f'Point "Edit" back at {primary_dir} now?',
            parent=self,
        )
        switch_btn = box.addButton("Switch Back", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Not Yet", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is switch_btn:
            self._location_edits['edit'].setText(str(primary_dir))
            QMessageBox.information(self, "Ready", "Click Save below to switch Edit back to the primary folder.")

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
            if key == 'media_extensions':
                # Matches load_media_extensions()'s own fallback -- shown
                # as a placeholder rather than pre-filled text, so it's
                # clearly "what applies if you leave this blank" and not
                # mistaken for a saved value. Also as a tooltip, since
                # the field is too narrow to show the full list at once.
                default_text = ', '.join(DEFAULT_MEDIA_EXTENSIONS)
                edit.setPlaceholderText(f"(default: {default_text})")
                edit.setToolTip(f"Used when this is left blank:\n{default_text}")
            self._option_edits[key] = edit
            form.addRow(f"{key}:", edit)

        return group

    def _populate_web_app_layout(self, layout: QVBoxLayout):
        note = QLabel(
            "Generates a script that deploys this app's browser-based companion "
            "as a real background service on this machine (Nginx/Apache on "
            "Linux, IIS on Windows) -- a one-time, rarely-needed setup step."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #666;")
        layout.addWidget(note)

        button_row = QHBoxLayout()
        install_button = QPushButton("Install as Web Server...")
        install_button.setToolTip("Install as web-server on this machine")
        install_button.clicked.connect(self._on_install_web_app)
        button_row.addWidget(install_button)
        button_row.addStretch()
        layout.addLayout(button_row)

    def _on_install_web_app(self):
        dlg = InstallWebAppDialog(parent=self)
        dlg.exec()  # modal -- generates a script to disk, makes no changes to this app's own state

    def _browse_for(self, line_edit: QLineEdit):
        start_dir = line_edit.text() or str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "Select folder", start_dir)
        if chosen:
            line_edit.setText(chosen)

    def _write_archive_signatures(self, location_paths: dict):
        """Drops/refreshes the hidden archive-id marker (see
        core/archive_signature.py) into every configured, existing
        folder here -- clutter folder included -- so a later Settings
        session pointing its clutter folder somewhere nearby can verify
        these really belong together, not just share a folder name.
        Reuses whichever ID any of these folders already carries
        (so re-saving Settings doesn't churn it); mints a fresh one
        only if none of them has one yet."""
        existing_dirs = [Path(p) for p in location_paths.values() if p and Path(p).is_dir()]
        if not existing_dirs:
            return
        archive_id = None
        for folder in existing_dirs:
            archive_id = archive_signature.read_signature(folder)
            if archive_id is not None:
                break
        if archive_id is None:
            archive_id = archive_signature.new_archive_id()
        for folder in existing_dirs:
            archive_signature.write_signature(folder, archive_id)

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

        # Harmless no-op for a fully-populated config (every candidate
        # field is already non-blank) -- worth running anyway for a
        # config with real gaps, e.g. after a partial hand-edit.
        self._auto_detect_sibling_locations()

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

        self._write_archive_signatures(parser['locations'])

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
