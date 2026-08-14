from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QCheckBox,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QDialogButtonBox,
    QFileDialog, QInputDialog, QMessageBox,
)

from vra_editor.core import media_metadata

_IMAGE_FILE_FILTER = "Images (*.tif *.tiff *.jpg *.jpeg *.png);;All Files (*)"

# One row per bidirectional field, in the same order compute_media_sync's
# 'fields' dict is keyed -- (field name, display label).
_FIELD_ROWS = [
    ('title', 'Title'),
    ('description', 'Description'),
    ('rights', 'Rights'),
    ('agent', 'People'),
    ('subject', 'Subjects'),
    ('date', 'Creation Date'),
    ('location', 'Location'),
]

_CONFLICT_CHOICES = ['Leave as-is', 'Use file value', 'Use record value']
# location has no file-write path (there's no GPS-EXIF writer, only a
# reader -- see DocumentController._FILE_WRITABLE_FIELDS), so "use record
# value" -- which would mean pushing it into the file -- isn't offered.
_LOCATION_CONFLICT_CHOICES = ['Leave as-is', 'Use file value']


def _display_value(value) -> str:
    if isinstance(value, list):
        return ', '.join(value) if value else '—'
    return value if value else '—'


def _format_bytes(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if size < 1024 or unit == 'GB':
            return f"{size:.0f} {unit}" if unit == 'B' else f"{size:.1f} {unit}"
        size /= 1024


class MediaSyncDialog(QDialog):
    """Combined Extract/Inject replacement: picks an image file (there's
    no persisted link to read one from -- see
    DocumentController.compute_media_sync's docstring), computes how it
    compares against the open record field by field, and lets the
    cataloguer choose which gaps to fill in which direction before
    writing anything. One "locate the file" step serves both directions,
    per the design this replaced (a docked preview band with separate
    always-on-overwrite Inject/Extract buttons).

    Measurements (width/height/resolution/file size) aren't part of the
    field table -- they're physical facts about the file with no
    sensible "write back" direction, so they're always refreshed from
    the file and just shown informationally above the table.
    """

    def __init__(self, doc_controller, parent=None):
        super().__init__(parent)
        self._doc_controller = doc_controller
        self._image_path: Path | None = None
        self._sync_data: dict | None = None
        self._row_controls: dict = {}  # field name -> QCheckBox or QComboBox

        self.setWindowTitle("Sync Media File")
        self.setModal(True)
        self.resize(640, 480)

        layout = QVBoxLayout(self)

        picker_row = QHBoxLayout()
        picker_row.addWidget(QLabel("Image file:"))
        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        picker_row.addWidget(self.path_edit, stretch=1)
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self._on_browse)
        picker_row.addWidget(browse_button)
        layout.addLayout(picker_row)

        self.measurements_label = QLabel()
        self.measurements_label.setWordWrap(True)
        layout.addWidget(self.measurements_label)

        self.table = QTableWidget(len(_FIELD_ROWS), 4)
        self.table.setHorizontalHeaderLabels(['Field', 'Record', 'File', 'Action'])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        for row, (name, label) in enumerate(_FIELD_ROWS):
            self.table.setItem(row, 0, QTableWidgetItem(label))
        layout.addWidget(self.table, stretch=1)

        self.copy_checkbox = QCheckBox("Also copy this file to sit alongside the record's XML")
        layout.addWidget(self.copy_checkbox)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.sync_button = self.buttons.addButton("Sync", QDialogButtonBox.AcceptRole)
        self.sync_button.setEnabled(False)
        self.buttons.accepted.connect(self._on_sync_clicked)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self._clear_table()
        guessed = doc_controller.guess_linked_media_path()
        if guessed is not None:
            choice = self._prompt_initial_source(guessed)
            if choice == 'matching':
                self._load_path(guessed)
            elif choice == 'browse':
                self._on_browse()
            # 'cancel' leaves the table empty -- the Browse... button
            # is still there for the user to pick a file manually.

    def _clear_table(self):
        self.measurements_label.setText("Pick an image file to compare it against this record.")
        for row, (name, _label) in enumerate(_FIELD_ROWS):
            self.table.setItem(row, 1, QTableWidgetItem(''))
            self.table.setItem(row, 2, QTableWidgetItem(''))
            self.table.setCellWidget(row, 3, None)
        self._row_controls = {}

    def _prompt_initial_source(self, guessed: Path) -> str:
        """Called once, at dialog open, only when a file matching this
        record's id was found sitting next to its XML. Returns
        'matching' | 'browse' | 'cancel' -- the dialog otherwise stayed
        silent about this before, always preloading the guessed file
        without asking."""
        box = QMessageBox(
            QMessageBox.Icon.Question, "Locate Media File",
            f'Found a file with the same name as this record: "{guessed.name}".\n\n'
            f'Use that file, or choose a different one?',
            parent=self,
        )
        use_button = box.addButton(f'Use "{guessed.name}"', QMessageBox.ButtonRole.AcceptRole)
        browse_button = box.addButton("Choose a File...", QMessageBox.ButtonRole.ActionRole)
        cancel_button = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(use_button)
        box.exec()
        clicked = box.clickedButton()

        if clicked is use_button:
            return 'matching'
        if clicked is browse_button:
            return 'browse'
        assert clicked is cancel_button
        return 'cancel'

    def _on_browse(self):
        current_file = self._doc_controller.current_file
        record_dir = Path(current_file).parent if current_file else None
        start_dir = str(record_dir) if record_dir and record_dir.exists() else str(Path.home())
        path_str, _ = QFileDialog.getOpenFileName(self, "Select Image File", start_dir, _IMAGE_FILE_FILTER)
        if not path_str:
            return
        self._load_path(Path(path_str))

    def _load_path(self, path: Path):
        try:
            sync_data = self._doc_controller.compute_media_sync(path)
        except Exception as exc:
            QMessageBox.warning(self, "Couldn't read file", f"Could not read metadata from this file:\n{exc}")
            return

        self._image_path = path
        self._sync_data = sync_data
        self.path_edit.setText(str(path))
        self.sync_button.setEnabled(True)
        self._render_measurements(sync_data['measurements'])
        self._render_fields(sync_data['fields'])

    def _render_measurements(self, measurements: dict):
        parts = [f"{measurements['width']} × {measurements['height']} px"]
        if measurements['resolution'] is not None:
            parts.append(f"{measurements['resolution']} dpi")
        parts.append(_format_bytes(measurements['file_size']))
        self.measurements_label.setText("Measurements will be updated to: " + ", ".join(parts))

    def _render_fields(self, fields: dict):
        self._row_controls = {}
        for row, (name, _label) in enumerate(_FIELD_ROWS):
            info = fields[name]
            self.table.setItem(row, 1, QTableWidgetItem(_display_value(info['record'])))
            self.table.setItem(row, 2, QTableWidgetItem(_display_value(info['file'])))

            status = info['status']
            if status == 'fill_record':
                control = QCheckBox("Fill record from file")
                control.setChecked(True)
            elif status == 'fill_file':
                control = QCheckBox("Write into file")
                control.setChecked(True)
            elif status == 'conflict':
                control = QComboBox()
                control.addItems(_LOCATION_CONFLICT_CHOICES if name == 'location' else _CONFLICT_CHOICES)
            elif status == 'in_sync':
                control = QLabel("In sync")
            else:
                control = QLabel("—")
            self.table.setCellWidget(row, 3, control)
            self._row_controls[name] = (status, control)

    def _selections(self) -> dict:
        selections = {}
        for name, (status, control) in self._row_controls.items():
            if status == 'fill_record' and isinstance(control, QCheckBox) and control.isChecked():
                selections[name] = 'record'
            elif status == 'fill_file' and isinstance(control, QCheckBox) and control.isChecked():
                selections[name] = 'file'
            elif status == 'conflict' and isinstance(control, QComboBox):
                choice = control.currentText()
                if choice == 'Use file value':
                    selections[name] = 'record'
                elif choice == 'Use record value':
                    selections[name] = 'file'
        return selections

    def _resolve_fuzzy_date(self) -> bool:
        """If the record's creation date isn't an exact calendar date,
        writing it into the file (IPTC DateCreated / EXIF
        DateTimeOriginal) would silently write nothing at all -- ask
        whether to correct it or drop the date from this sync. Returns
        False if the user backs out of Sync entirely."""
        date_text = self._doc_controller.get_creation_date_text()
        if not date_text or media_metadata.parse_vra_date(date_text) is not None:
            return True

        box = QMessageBox(
            QMessageBox.Icon.Warning, "Creation date isn't exact",
            f'This record\'s creation date is "{date_text}", which isn\'t a specific '
            f'calendar date -- IPTC/EXIF have no way to store that. Enter an exact '
            f'date, or skip writing a date at all?',
            parent=self,
        )
        enter_button = box.addButton("Enter Exact Date...", QMessageBox.ButtonRole.AcceptRole)
        skip_button = box.addButton("Skip Date", QMessageBox.ButtonRole.DestructiveRole)
        cancel_button = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel_button)
        box.exec()
        clicked = box.clickedButton()

        if clicked is cancel_button:
            return False
        if clicked is skip_button:
            return True  # leave the record's date as-is; it's simply omitted from the file write below

        while True:
            new_date, ok = QInputDialog.getText(
                self, "Enter exact date", "Creation date (YYYY-MM-DD):", text=date_text,
            )
            if not ok:
                return False
            new_date = new_date.strip()
            if media_metadata.parse_vra_date(new_date) is not None:
                self._doc_controller.set_creation_date(new_date)
                return True
            QMessageBox.warning(self, "Not a valid date", "Enter a date as YYYY-MM-DD, YYYY-MM, or YYYY.")

    def _on_sync_clicked(self):
        if self._image_path is None:
            return
        selections = self._selections()

        if selections.get('date') == 'file' and not self._resolve_fuzzy_date():
            return

        self._doc_controller.apply_media_sync(self._image_path, selections)

        if self.copy_checkbox.isChecked():
            try:
                self._doc_controller.copy_media_alongside(self._image_path)
            except Exception as exc:
                QMessageBox.warning(self, "Copy failed", f"Could not copy the file:\n{exc}")

        self.accept()
