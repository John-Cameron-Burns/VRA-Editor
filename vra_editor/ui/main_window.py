from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut, QPixmap
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QPushButton, QLabel, QFrame,
    QHBoxLayout, QVBoxLayout, QSplitter, QSizePolicy, QMessageBox, QInputDialog,
    QStackedWidget,
)

from vra_editor.config import load_locations
from vra_editor.controllers.document_controller import DocumentController, LocationUnavailableError
from vra_editor.core.commit_to_git import add_file_to_repo
from vra_editor.core.update_check import DEV_BUILD_VERSION, UpdateCheckError, check_for_update, get_app_version
from vra_editor.ui.dialogs.file_picker import VraFilePickerDialog
from vra_editor.ui.dialogs.audit_dialog import AuditDialog
from vra_editor.ui.dialogs.help_dialog import HelpDialog
from vra_editor.ui.dialogs.import_progress_dialog import ImportProgressDialog
from vra_editor.ui.dialogs.media_sync_dialog import MediaSyncDialog
from vra_editor.ui.dialogs.settings_dialog import SettingsDialog
from vra_editor.ui.error_messages import friendly_validation_error
from vra_editor.ui.panels.form_panel.form_container import FormContainerPanel
from vra_editor.ui.panels.review_notes_panel import ReviewNotesPanel
from vra_editor.ui.panels.section_panel.section_form import SectionFormPanel
from vra_editor.ui.panels.section_panel.section_list import SectionListPanel
from vra_editor.ui.panels.tree_panel.tree_widget import VraTreePanel
from vra_editor.ui.widgets.background_image_widget import random_background_image
from vra_editor.ui.panels.xml_preview.code_editor import XmlPreviewPanel
from vra_editor.utils import user_name

IMAGES_DIR = Path(__file__).resolve().parent.parent / "images"
LOGO_PATH = IMAGES_DIR / "logo.png"

# The one committing action per mode (Submit hands a record on for review;
# Approve moves it into the reviewed archive) gets a distinct, deliberate
# style so it doesn't carry the same visual weight as Save/Undo/Cancel --
# actions a scholar can try and back out of freely.
PRIMARY_BUTTON_STYLE = """
QPushButton {
    background-color: #2E7D5B;
    color: white;
    font-weight: 600;
    border: none;
    border-radius: 4px;
    padding: 6px 16px;
    min-height: 20px;
}
QPushButton:hover {
    background-color: #266449;
}
QPushButton:pressed {
    background-color: #1F5239;
}
QPushButton:disabled {
    background-color: #A9C3B7;
    color: #EDEDEA;
}
"""

# Reject is the other consequential, hard-to-walk-back action alongside
# Submit/Approve (it bounces a record back to the editor), so it gets its
# own distinct treatment too -- an outlined red rather than Submit/Approve's
# solid green, so the two don't compete for the same "primary action" read
# when both could theoretically be visible.
REJECT_BUTTON_STYLE = """
QPushButton {
    background-color: white;
    color: #B3261E;
    font-weight: 600;
    border: 1px solid #B3261E;
    border-radius: 4px;
    padding: 6px 16px;
    min-height: 20px;
}
QPushButton:hover {
    background-color: #FBEAE9;
}
QPushButton:pressed {
    background-color: #F5D4D2;
}
QPushButton:disabled {
    background-color: white;
    color: #E0B4B1;
    border-color: #E0B4B1;
}
"""

# View toggles (Show XML/Review Notes/Advanced View) and admin actions
# (Settings/Autofill/About) are things a cataloguer reaches for far less
# often than Save/Submit -- styled smaller and muted so they read as
# secondary at a glance instead of competing on equal footing.
SECONDARY_BUTTON_STYLE = """
QPushButton {
    background-color: transparent;
    color: #666;
    border: 1px solid #ccc;
    border-radius: 3px;
    padding: 3px 10px;
    font-size: 11px;
}
QPushButton:hover {
    background-color: #e8e8e8;
}
QPushButton:checked {
    background-color: #DCEEFB;
    color: #0B4C7C;
    border-color: #7aa7d0;
}
"""


class ModeBar(QWidget):
    """A single row of buttons whose visible subset changes with the app mode.

    Buttons are created once and behave identically regardless of mode;
    only their visibility changes. This avoids duplicating widgets per
    mode and avoids the reparenting bug that comes from sharing widget
    instances across multiple layouts.

    groups (optional) maps each button name to a cluster key ("nav",
    "action", ...). Buttons must already be contiguous by group in
    `order` for this to render sensibly -- a thin vertical divider is
    inserted at each group boundary, so unrelated actions (leaving the
    record vs. acting on it vs. toggling a view) read as visually
    separate clusters instead of one undifferentiated row. Each
    divider's own visibility tracks whether anything in the group it
    precedes is visible in the current mode, so an empty group doesn't
    leave a stray divider with nothing next to it.
    """

    def __init__(self, variants: dict[str, list[str]], order: list[str] | None = None,
                 tooltips: dict[str, str] | None = None, groups: dict[str, str] | None = None,
                 parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        all_names = {name for names in variants.values() for name in names}
        if order is not None:
            ordered_names = [name for name in order if name in all_names]
            # Defensive: a name present in variants but missing from order
            # still gets a button (just tacked on the end), so adding a
            # new mode-bar button elsewhere can't silently vanish here.
            ordered_names += [name for name in all_names if name not in ordered_names]
        else:
            # Preserve first-seen order across all variants.
            ordered_names = []
            for names in variants.values():
                for name in names:
                    if name not in ordered_names:
                        ordered_names.append(name)

        groups = groups or {}
        self.buttons: dict[str, QPushButton] = {}
        self._group_dividers: list[tuple[QFrame, str]] = []  # (divider, group it precedes)
        current_group = None
        for name in ordered_names:
            group = groups.get(name)
            if group is not None and group != current_group and self.buttons:
                divider = QFrame()
                divider.setFrameShape(QFrame.Shape.VLine)
                divider.setFrameShadow(QFrame.Shadow.Sunken)
                layout.addWidget(divider)
                self._group_dividers.append((divider, group))
            if group is not None:
                current_group = group

            btn = QPushButton(name)
            if tooltips and name in tooltips:
                btn.setToolTip(tooltips[name])
            self.buttons[name] = btn
            layout.addWidget(btn)
        layout.addStretch()

        self.variants = variants
        self.groups = groups
        self.current_mode: str | None = None

    def set_mode(self, mode: str):
        visible = set(self.variants[mode])
        for name, btn in self.buttons.items():
            btn.setVisible(name in visible)
        self.update_dividers(visible)
        self.current_mode = mode

    def update_dividers(self, visible_names: set):
        """Shows/hides each group divider based on whether anything in
        the group it precedes is in visible_names. Split out from
        set_mode so MainWindow.apply_mode -- which drives button
        visibility itself, through the generic mode_widgets registry,
        rather than calling set_mode -- can still keep the dividers in
        sync using the same visible-set it already computed."""
        for divider, group in self._group_dividers:
            group_names = [name for name, g in self.groups.items() if g == group]
            divider.setVisible(any(name in visible_names for name in group_names))


class StatusBar(QWidget):
    """Owns the status-bar labels and exposes setters for them.

    Callers never touch individual QLabel objects directly -- they call
    set_user(...), set_file(...), etc. This keeps 'who can change the
    status bar' answerable by 'whoever calls these methods', and means
    the labels can be relabelled/restyled here without hunting down
    every call site.
    """

    FIELDS = ['User', 'File', 'Mode', 'Archive']

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(30)
        self.setStyleSheet("background-color: #f0f0f0; border-top: 1px solid #ccc;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(15)

        self._labels: dict[str, QLabel] = {}
        for name in self.FIELDS:
            lbl = QLabel(f"<b>{name}:</b> <none>")
            lbl.setMinimumWidth(100)
            self._labels[name] = lbl
            layout.addWidget(lbl)

        self._labels['File'].setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def _set(self, name: str, value: str):
        self._labels[name].setText(f"<b>{name}:</b> {value}")

    def set_user(self, value: str):
        self._set('User', value)

    def set_file(self, value: str):
        self._set('File', value)

    def set_mode(self, value: str):
        self._set('Mode', value)

    def set_archive(self, value: str):
        self._set('Archive', value)


class ModeStrip(QWidget):
    """A thin, colored context bar under the top toolbar -- the primary
    way to tell "editing" and "reviewing" apart at a glance, replacing
    the 9pt "Mode: edit" status-bar label as the only indicator. The
    distinction matters (Submit vs. Approve/Reject write to different
    archives), so it shouldn't be easy to miss.

    Hidden entirely outside edit/review -- there's no record-level
    context to show on the home screen or in Settings.
    """

    # mode -> (verb shown before the filename, background, text color)
    _STYLES = {
        'edit': ("Editing", "#DCEEFB", "#0B4C7C"),
        'review': ("Reviewing", "#FDECC8", "#7A4E00"),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(26)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        self.label = QLabel()
        layout.addWidget(self.label)
        layout.addStretch()
        self.hide()

    def set_context(self, mode: str, filename: str = ""):
        info = self._STYLES.get(mode)
        if info is None:
            self.hide()
            return
        verb, bg, fg = info
        name = Path(filename).name if filename else ""
        self.label.setText(f"{verb} — {name}" if name else verb)
        self.setStyleSheet(f"background-color: {bg};")
        self.label.setStyleSheet(f"font-weight: 600; color: {fg};")
        self.show()


class MainWindow(QMainWindow):
    # Central place for what's visible in each mode. Extend this if
    # other widgets (not just buttons) need to change with mode --
    # see register_mode_widget / apply_mode below.
    BASE_BUTTONS = ['Home', 'Open', 'Create', 'Review', 'Import']

    # Left-to-right position on the mode bar, grouped into four clusters
    # that ModeBar renders as visually separate (a divider between each,
    # see BUTTON_GROUPS below) rather than one flat row: where to go
    # (nav), what to do with the open record (action), how to look at it
    # (view), and rarely-used admin actions. Order within a cluster is
    # itself meaningful -- Approve rides in Submit's slot since the two
    # are never visible at once.
    BUTTON_ORDER = [
        'Home', 'Open', 'Create', 'Review', 'Import',
        'Save', 'Undo', 'Submit', 'Approve', 'Reject', 'Cancel',
        'Show XML', 'Review Notes', 'Advanced View', 'Sync Media',
        'Settings', 'Autofill', 'Audits', 'Help', 'About',
    ]

    # Which visual cluster each button belongs to -- see ModeBar's
    # `groups` param. Must partition BUTTON_ORDER into contiguous runs
    # per group for the dividers to land in sensible places.
    BUTTON_GROUPS = {
        'Home': 'nav', 'Open': 'nav', 'Create': 'nav', 'Review': 'nav', 'Import': 'nav',
        'Save': 'action', 'Undo': 'action', 'Submit': 'action', 'Approve': 'action',
        'Reject': 'action', 'Cancel': 'action',
        'Show XML': 'view', 'Review Notes': 'view', 'Advanced View': 'view', 'Sync Media': 'view',
        'Settings': 'admin', 'Autofill': 'admin', 'Audits': 'admin', 'Help': 'admin', 'About': 'admin',
    }

    VARIANTS = dict(
        initial=BASE_BUTTONS + ['Settings', 'Audits', 'Help', 'About'],
        edit=BASE_BUTTONS + ['Save', 'Undo', 'Show XML', 'Review Notes', 'Advanced View', 'Sync Media',
                              'Submit', 'Cancel', 'Audits', 'Help', 'About'],
        review=BASE_BUTTONS + ['Approve', 'Undo', 'Show XML', 'Review Notes', 'Advanced View', 'Sync Media',
                                'Reject', 'Cancel', 'Audits', 'Help', 'About'],
        settings=BASE_BUTTONS + ['Autofill', 'Save', 'Cancel', 'Audits', 'Help', 'About'],
    )

    BUTTON_TOOLTIPS = {
        'Home': "Return to the start screen.",
        'Open': "Open an existing record from the edit folder.",
        'Create': "Start a new, blank record.",
        'Review': "Open a record that's waiting in the review queue.",
        'Import': "Merge newly-arrived source files into the edit folder.",
        'Save': "Save this record without changing its review status.",
        'Undo': "Revert the last change (Ctrl+Z).",
        'Show XML': "Show or hide the raw XML for this record.",
        'Review Notes': "Show or hide notes a reviewer has left for the editor.",
        'Advanced View': "Switch to the structure tree and single-element editor.",
        'Sync Media': "Compare this record against an image file and fill in gaps on either side.",
        'Submit': "Send this record for review. Requires it to be schema-valid.",
        'Approve': "Move this record into the reviewed archive.",
        'Reject': "Send this record back to the editor for revision.",
        'Cancel': "Discard changes and return to the start screen.",
        'Settings': "Configure archive folders, application data, and preferences.",
        'Autofill': "Fill in settings fields with their default values.",
        'Audits': "Browse revision history and restore an old version into a new file.",
        'Help': "Open the user manual.",
        'About': "Show version and license information.",
    }

    def __init__(self):
        super().__init__()
        self.setWindowTitle("VRA Core 4 XML Editor")
        self.resize(1100, 650)

        self.doc_controller = DocumentController()

        self.mode_bar: ModeBar | None = None
        self.tree_panel = None  # Advanced-view: the elements tree
        self.form_panel = None  # Advanced-view: single-element form
        self.section_list = None  # Simple-view (default): section list
        self.section_form = None  # Simple-view (default): section form
        self.xml_preview_panel = None  # Shows the current XML
        self.status_bar: StatusBar | None = None
        self._current_section_tag: str | None = None  # which Set the Simple view is showing
        self._help_dialog: HelpDialog | None = None  # created lazily, reused across clicks

        # Registry of any widget (not just mode-bar buttons) that should
        # be shown/hidden per mode. Populate via register_mode_widget().
        self.mode_widgets: dict[str, QWidget] = {}

        self.initialise_layout()
        self.apply_mode('initial')

        undo_shortcut = QShortcut(QKeySequence.StandardKey.Undo, self)
        undo_shortcut.activated.connect(self._on_undo)

        # Deferred rather than checked inline here -- lets the window
        # actually paint and become responsive first, so a slow (not
        # just absent) network doesn't read as the app hanging on
        # launch. Silent regardless of outcome; see _check_for_updates.
        QTimer.singleShot(800, lambda: self._check_for_updates(silent=True))

    # ------------------------------------------------------------------
    # Layout construction
    # ------------------------------------------------------------------

    def initialise_layout(self):
        top_bar = self._build_top_bar()

        # Simple view (default) and Advanced view (tree + single-element
        # form) are two alternate presentations of the same document,
        # swapped together by the "Advanced View" toggle -- see
        # _on_toggle_advanced. Both drive the same DocumentController.
        # Chosen once per session, not per panel, so toggling Advanced
        # View doesn't swap the picture out from under you.
        nav_background = random_background_image()
        self.section_list = SectionListPanel(image_path=nav_background)
        self.tree_panel = VraTreePanel(image_path=nav_background)
        self.nav_stack = QStackedWidget()
        self.nav_stack.addWidget(self.section_list)  # index 0: Simple
        self.nav_stack.addWidget(self.tree_panel)    # index 1: Advanced

        self.section_form = SectionFormPanel(self.doc_controller)
        self.form_panel = FormContainerPanel()
        self.form_stack = QStackedWidget()
        self.form_stack.addWidget(self.section_form)  # index 0: Simple
        self.form_stack.addWidget(self.form_panel)    # index 1: Advanced

        splitter = QSplitter(Qt.Horizontal)
        self.xml_preview_panel = XmlPreviewPanel()
        self.review_notes_panel = ReviewNotesPanel(self.doc_controller)
        splitter.addWidget(self.nav_stack)
        splitter.addWidget(self.form_stack)
        splitter.addWidget(self.review_notes_panel)
        splitter.addWidget(self.xml_preview_panel)
        splitter.setSizes([250, 425, 250, 425])
        self._splitter = splitter
        self.xml_preview_panel.setVisible(False)  # hidden by default; toggled via the "Show XML" button
        self.review_notes_panel.setVisible(False)  # toggled via "Review Notes"; auto-shown if there's unresolved work

        self.status_bar = StatusBar()
        self.status_bar.set_user(user_name())  # fetched once; doesn't change

        self.mode_strip = ModeStrip()

        central = QWidget()
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(top_bar)
        main_layout.addWidget(self.mode_strip)
        main_layout.addWidget(splitter, stretch=1)
        main_layout.addWidget(self.status_bar)
        self.setCentralWidget(central)

        # Advanced view (unchanged from before the Simple view existed).
        self.tree_panel.element_selected.connect(self._on_element_selected)
        self.tree_panel.add_child_requested.connect(self._on_add_child_requested)
        self.tree_panel.remove_requested.connect(self._on_remove_requested)
        self.form_panel.element_data_changed.connect(self.doc_controller.update_element_data)
        self.form_panel.display_data_changed.connect(self.doc_controller.update_display_data)

        # Simple view -- SectionFormPanel/FieldRow call doc_controller
        # directly (see field_row.py), so only navigation needs wiring.
        self.section_list.section_selected.connect(self._on_section_selected)
        self.section_list.add_section_requested.connect(self._on_add_section_requested)

        # document_loaded fires on load and on any insert/remove (a
        # structural change); both views' data comes from a fresh
        # build_tree() walk each time, since the old VraTreeNode objects
        # don't survive a rebuild.
        self.doc_controller.document_loaded.connect(self._on_document_loaded)
        self.doc_controller.xml_updated.connect(self._on_xml_updated)

        # Status bar updates as a side effect of other actions: connect
        # each relevant signal straight to the matching setter. No other
        # code needs to know the status bar exists.
        self.doc_controller.file_loaded.connect(self.status_bar.set_file)
        self.doc_controller.file_loaded.connect(self._on_file_loaded)
        self.doc_controller.archive_changed.connect(self.status_bar.set_archive)
        # If a signal doesn't map 1:1 onto a setter, connect to a small
        # slot instead, e.g.:
        # self.doc_controller.document_saved.connect(
        #     lambda path: self.status_bar.set_file(f"{path} (saved)")
        # )

        self.xml_preview_panel.update_xml_text(self.doc_controller.get_initial_xml())
        self._refresh_navigation()  # show the "no record open" placeholder

    def _on_element_selected(self, node_type: str, data: dict, element):
        """Tree selection changed (Advanced view): track which lxml
        element subsequent form edits should write into, then show the
        matching editor."""
        self.doc_controller.set_current_element(element)
        self.form_panel.show_editor(node_type, data)
        self._highlight_current_element()

    def _on_add_child_requested(self, parent_element, tag: str, sibling_order: list):
        new_elem = self.doc_controller.insert_child(parent_element, tag, sibling_order)
        self.tree_panel.select_element(new_elem)

    def _on_remove_requested(self, element):
        self.doc_controller.remove_element(element)
        self.form_panel.show_editor('', {})
        self._highlight_current_element()

    def _on_section_selected(self, node):
        """A Set was chosen in the Simple view's section list. Re-fetches
        a fresh node for the same tag rather than trusting the one the
        signal carried: SectionListPanel's rows are only rebuilt on
        document_loaded (structural changes), so a plain edit -- e.g.
        adding a Display translation, which only emits xml_updated --
        would otherwise leave the just-clicked row holding a node
        snapshotted before that edit."""
        self._current_section_tag = node.data.get('tag')
        record_node = self._current_record_node()
        if record_node is None:
            return
        match = next(
            (c for c in record_node.children if c.data.get('tag') == self._current_section_tag),
            None,
        )
        self.section_form.show_section(match if match is not None else node)

    def _on_add_section_requested(self, tag: str, sibling_order: list):
        """A Set the record doesn't have yet was chosen from the
        greyed-out "+ Add" rows in the section list."""
        record_node = self._current_record_node()
        if record_node is None:
            return
        self._current_section_tag = tag  # set before insert_child: document_loaded fires from inside it
        self.doc_controller.insert_child(record_node.element, tag, sibling_order)

    def _current_record_node(self):
        if self.doc_controller.xml_doc.xml_root is None:
            return None
        records = self.doc_controller.xml_doc.build_tree()
        return records[0] if records else None

    def _on_document_loaded(self, *_ignored):
        """Fires on file load and on any insert/remove. Both views read
        from a fresh build_tree() walk -- the previous call's
        VraTreeNode objects don't survive a structural change, only the
        underlying lxml elements do."""
        self.tree_panel.load_document(self.doc_controller.xml_doc)
        self._refresh_navigation()
        self.review_notes_panel.refresh()

    def _on_file_loaded(self, path: str):
        """Surfaced automatically, not just available behind the
        toggle, so an editor opening a record a reviewer left work on
        can't miss it. Deliberately tied to file_loaded rather than
        document_loaded -- the latter also fires on every insert/remove,
        which would reopen the panel right after the user closes it if
        they then add or delete a Set."""
        if self.review_notes_panel.has_unresolved_notes():
            self.mode_bar.buttons['Review Notes'].setChecked(True)
        self.mode_strip.set_context(self.mode_bar.current_mode, path)

    def _refresh_navigation(self):
        """Re-syncs the Simple view (both the section list and whichever
        section was showing) with the document's current state. Called
        after every document_loaded, and when the Advanced-view toggle
        flips, since plain field edits only emit xml_updated -- the
        pane that was hidden during such an edit would otherwise show
        stale data the moment it becomes visible again."""
        record_node = self._current_record_node()
        self.section_list.load_record(record_node)

        if record_node is None:
            self.section_form.show_no_document()
            return

        if self._current_section_tag is not None:
            match = next(
                (c for c in record_node.children if c.data.get('tag') == self._current_section_tag),
                None,
            )
            if match is not None:
                self.section_form.show_section(match)
                return

        self.section_form.clear()

    def _on_xml_updated(self, xml_text: str):
        """The preview text got replaced (any edit, insert, or remove) --
        update it, then re-highlight whatever's currently selected,
        since its position in the text may have shifted."""
        self.xml_preview_panel.update_xml_text(xml_text)
        self._highlight_current_element()

    def _highlight_current_element(self):
        element = self.doc_controller.current_element
        if element is None:
            self.xml_preview_panel.clear_highlight()
            return
        span = self.doc_controller.xml_doc.find_element_span(element, self.doc_controller.get_initial_xml())
        if span is None:
            self.xml_preview_panel.clear_highlight()
            return
        self.xml_preview_panel.highlight_span(*span)

    def _build_top_bar(self) -> QWidget:
        top_bar = QWidget()
        # A floor, not a ceiling -- a fixed height clipped the bold/padded
        # Submit and Approve buttons on some platforms, since their styled
        # sizeHint could exceed a hard 40px cap the other, unstyled buttons
        # never approached.
        top_bar.setMinimumHeight(40)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(5, 5, 5, 5)

        if LOGO_PATH.exists():
            logo_pixmap = QPixmap(str(LOGO_PATH))
            logo = QLabel()
            logo.setPixmap(logo_pixmap.scaledToHeight(30, Qt.TransformationMode.SmoothTransformation))
            top_layout.addWidget(logo)

        self.mode_bar = ModeBar(self.VARIANTS, order=self.BUTTON_ORDER, tooltips=self.BUTTON_TOOLTIPS,
                                 groups=self.BUTTON_GROUPS)
        top_layout.addWidget(self.mode_bar)

        # Register buttons in the shared mode-widget registry too, so
        # apply_mode() can drive both the bar and any other mode-aware
        # widgets from a single call.
        for name, btn in self.mode_bar.buttons.items():
            self.register_mode_widget(name, btn)

        for name in ('Submit', 'Approve'):
            self.mode_bar.buttons[name].setStyleSheet(PRIMARY_BUTTON_STYLE)
        self.mode_bar.buttons['Reject'].setStyleSheet(REJECT_BUTTON_STYLE)
        for name in ('Show XML', 'Review Notes', 'Advanced View', 'Sync Media',
                     'Settings', 'Autofill', 'Audits', 'Help', 'About'):
            self.mode_bar.buttons[name].setStyleSheet(SECONDARY_BUTTON_STYLE)

        # A toggle, not an action -- checkable so its pressed state shows
        # whether the XML pane is currently open, and its label always
        # names the click's effect rather than a fixed state.
        show_xml_button = self.mode_bar.buttons['Show XML']
        show_xml_button.setCheckable(True)
        show_xml_button.toggled.connect(self._on_toggle_xml)

        review_notes_button = self.mode_bar.buttons['Review Notes']
        review_notes_button.setCheckable(True)
        review_notes_button.toggled.connect(self._on_toggle_review_notes)

        advanced_button = self.mode_bar.buttons['Advanced View']
        advanced_button.setCheckable(True)
        advanced_button.toggled.connect(self._on_toggle_advanced)

        self._connect_button_signals()

        return top_bar

    def _connect_button_signals(self):
        """Wire each button's behaviour exactly once, independent of mode."""
        buttons = self.mode_bar.buttons
        buttons['Home'].clicked.connect(self._on_home)
        buttons['Open'].clicked.connect(self._on_open)
        buttons['Create'].clicked.connect(self._on_create)
        buttons['Review'].clicked.connect(self._on_review)
        buttons['Settings'].clicked.connect(self._on_settings)
        buttons['Audits'].clicked.connect(self._on_audits)
        buttons['Help'].clicked.connect(self._on_help)
        buttons['About'].clicked.connect(self._on_about)
        buttons['Save'].clicked.connect(self._on_save)
        buttons['Undo'].clicked.connect(self._on_undo)
        buttons['Submit'].clicked.connect(self._on_submit)
        buttons['Cancel'].clicked.connect(self._on_cancel)
        buttons['Approve'].clicked.connect(self._on_approve)
        buttons['Reject'].clicked.connect(self._on_reject)
        buttons['Autofill'].clicked.connect(self._on_autofill)
        buttons['Import'].clicked.connect(self._on_import)
        buttons['Sync Media'].clicked.connect(self._on_sync_media)

    def _on_toggle_xml(self, checked: bool):
        self.xml_preview_panel.setVisible(checked)
        self.mode_bar.buttons['Show XML'].setText('Hide XML' if checked else 'Show XML')

    def _on_toggle_review_notes(self, checked: bool):
        self.review_notes_panel.setVisible(checked)
        if checked:
            self.review_notes_panel.refresh()

    def _on_toggle_advanced(self, checked: bool):
        self.nav_stack.setCurrentIndex(1 if checked else 0)
        self.form_stack.setCurrentIndex(1 if checked else 0)
        self.mode_bar.buttons['Advanced View'].setText('Simple View' if checked else 'Advanced View')
        # Plain field edits only emit xml_updated, not document_loaded,
        # so whichever pane was hidden during one would otherwise show
        # stale data the moment it becomes visible again.
        self._refresh_navigation()
        if checked:
            self.tree_panel.load_document(self.doc_controller.xml_doc)

    # ------------------------------------------------------------------
    # Mode handling
    # ------------------------------------------------------------------

    def register_mode_widget(self, name: str, widget: QWidget):
        """Register any widget (button, panel, label...) that should be
        shown/hidden based on which names appear in self.VARIANTS[mode]."""
        self.mode_widgets[name] = widget

    def apply_mode(self, mode: str):
        visible_names = set(self.VARIANTS[mode])
        for name, widget in self.mode_widgets.items():
            widget.setVisible(name in visible_names)
        # Sync Media additionally needs the open record to actually be an
        # image -- a Collection or Work can never have a file to sync
        # against. Recomputed here (rather than from a separate
        # file_loaded-driven channel) since apply_mode's sweep above would
        # otherwise re-show it on every mode transition regardless of
        # record type.
        self.mode_bar.buttons['Sync Media'].setVisible(
            'Sync Media' in visible_names and self.doc_controller.current_record_type == 'image'
        )
        self.mode_bar.update_dividers(visible_names)
        self.mode_bar.current_mode = mode
        self.status_bar.set_mode(mode)
        self.mode_strip.set_context(mode, self.doc_controller.current_file or "")

    # ------------------------------------------------------------------
    # Button handlers -- implement these; mode-independent by design
    # ------------------------------------------------------------------

    def _confirm_discard_if_dirty(self) -> bool:
        """True if it's safe to navigate away from the record that's
        open now -- either nothing's unsaved, or the user explicitly
        chose to save or discard first. False means stay put; the
        caller should abort whatever navigation it was about to do.

        Guards Home/Open/Create/Review specifically: each of those
        replaces or clears doc_controller's loaded document outright
        (see DocumentController.load_file/create_new_record/clear),
        with no prompt beforehand -- previously an in-progress edit
        was silently gone the moment any of those four was clicked."""
        if not self.doc_controller.is_dirty:
            return True
        box = QMessageBox(
            QMessageBox.Icon.Warning, "Unsaved changes",
            "This record has changes that haven't been saved. What would you like to do?",
            parent=self,
        )
        save_btn = box.addButton("Save", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Discard", QMessageBox.ButtonRole.DestructiveRole)
        cancel_btn = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel_btn)
        box.exec()
        clicked = box.clickedButton()
        if clicked is cancel_btn:
            return False
        if clicked is save_btn:
            ok, message = self.doc_controller.save_file()
            if not ok:
                self._show_validation_error(message)
                return False  # couldn't save -- stay put rather than silently discard
        return True

    def _on_home(self):
        self._return_to_start()

    def _return_to_start(self):
        if not self._confirm_discard_if_dirty():
            return
        self.doc_controller.clear()
        self.apply_mode('initial')

    def _on_open(self):
        if not self._confirm_discard_if_dirty():
            return
        if self._open_from_folder('edit', dialog_title="Open Record"):
            self.apply_mode('edit')

    def _on_create(self):
        if not self._confirm_discard_if_dirty():
            return
        record_type, ok = QInputDialog.getItem(
            self, "Create Record", "Record type:", ('work', 'image', 'collection'), 0, False,
        )
        if not ok:
            return

        record_id, ok = QInputDialog.getText(self, "Create Record", "Record ID:")
        record_id = record_id.strip()
        if not ok or not record_id:
            return
        if any(sep in record_id for sep in ('/', '\\')):
            QMessageBox.warning(self, "Invalid ID", "Record ID can't contain '/' or '\\'.")
            return

        locations = load_locations()
        edit_dir = locations.get('edit')
        if edit_dir is None:
            QMessageBox.warning(self, "Missing location", "No 'edit' folder is configured in vra-config.ini.")
            return

        dest_path = (edit_dir / f"{record_id}.xml").resolve()
        if dest_path.exists():
            QMessageBox.warning(self, "Record already exists", f"{dest_path} already exists.")
            return

        edit_dir.mkdir(parents=True, exist_ok=True)
        self.doc_controller.create_new_record(record_type, record_id, dest_path)
        self.apply_mode('edit')

    def _on_review(self):
        if not self._confirm_discard_if_dirty():
            return
        if self._open_from_folder('pending', dialog_title="Select Record to Review"):
            self.apply_mode('review')

    def _open_from_folder(self, location_key: str, dialog_title: str) -> bool:
        """Returns True if a file was actually loaded -- callers should
        only switch mode in that case, not on a cancelled dialog."""
        locations = load_locations()  # re-read so it reflects the latest Settings
        folder = locations.get(location_key)
        if folder is None:
            QMessageBox.warning(
                self, "Missing location",
                f"No '{location_key}' folder is configured in vra-config.ini.",
            )
            return False

        dlg = VraFilePickerDialog(directory=folder, title=dialog_title, parent=self)
        if dlg.exec() and dlg.selected_path is not None:
            self.doc_controller.load_file(str(dlg.selected_path))
            return True
        return False

    def _on_settings(self):
        dlg = SettingsDialog(parent=self)
        dlg.exec()  # modal -- blocks until the user Saves or Cancels
        # dlg.exec() returning doesn't itself change app mode; Settings
        # remains an overlay on whatever mode was active before it opened.

    def _on_audits(self):
        dlg = AuditDialog(parent=self)
        dlg.restore_requested.connect(lambda revision, dest_path: self._on_restore_revision(dlg, revision, dest_path))
        dlg.exec()

    def _on_restore_revision(self, dialog: AuditDialog, revision, dest_path: str):
        # Restoring replaces the currently-open document, exactly like
        # Open/Create/Review -- same guard, same reason: don't silently
        # discard unsaved work.
        if not self._confirm_discard_if_dirty():
            return
        if not self.doc_controller.restore_revision(revision, dest_path):
            QMessageBox.warning(self, "Restore failed", f"Could not restore into {dest_path}.")
            return
        self.apply_mode('edit')
        dialog.accept()

    def _on_help(self):
        # Lazily created, then reused -- non-modal, so it can stay open
        # on the side while the user works through whatever it's
        # explaining, rather than reopening (and losing scroll position/
        # find text) on every click.
        if self._help_dialog is None:
            self._help_dialog = HelpDialog(self)
        self._help_dialog.show()
        self._help_dialog.raise_()
        self._help_dialog.activateWindow()

    def _on_about(self):
        # Built manually (not QMessageBox.about()'s one-button
        # convenience form) so Check for Updates can sit alongside it --
        # same reasoning as _confirm_discard_if_dirty's own manually-
        # built box elsewhere in this file.
        box = QMessageBox(
            QMessageBox.Icon.Information, "About VRA Core 4 XML Editor",
            "<h3>VRA Core 4 XML Editor</h3>"
            f"<p>Version {get_app_version()}</p>"
            "<p>Copyright &copy; 2026 John Burns and Impact Data Metrics Limited.</p>"
            "<p>Licensed under the "
            "<a href=\"https://creativecommons.org/licenses/by-nc/4.0/\">"
            "Creative Commons Attribution-NonCommercial 4.0 International License</a> "
            "(CC BY-NC 4.0).</p>"
            "<p>See the LICENSE file included with this application for the full license text.</p>",
            parent=self,
        )
        check_btn = box.addButton("Check for Updates", QMessageBox.ButtonRole.ActionRole)
        box.addButton("Close", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is check_btn:
            self._check_for_updates(silent=False)

    def _check_for_updates(self, silent: bool):
        """Shared by the silent startup check (see __init__'s
        QTimer.singleShot) and the About dialog's on-demand button --
        the only difference is how much this says when there's nothing
        to report. A startup check that popped up a dialog on every
        single launch just to say "you're current" would be exactly the
        kind of nagging this app's own offline-first design otherwise
        goes out of its way to avoid; an explicit on-demand check should
        say something regardless of the outcome, since silence would
        just look broken."""
        if not silent and get_app_version() == DEV_BUILD_VERSION:
            # check_for_update() itself would just silently return None
            # for this case (nothing meaningful to compare a dev build
            # against) -- worth a distinct, honest message here rather
            # than a misleading "you're up to date" for a version that
            # was never actually checked.
            QMessageBox.information(
                self, "Development build",
                "Update checks aren't available when running from source -- only in a packaged build.",
            )
            return
        try:
            info = check_for_update(timeout=5.0 if silent else 10.0)
        except UpdateCheckError as e:
            if not silent:
                QMessageBox.warning(self, "Couldn't check for updates", str(e))
            return

        if info is None:
            if not silent:
                QMessageBox.information(
                    self, "You're up to date",
                    f"Version {get_app_version()} is the latest available.",
                )
            return

        box = QMessageBox(
            QMessageBox.Icon.Information, "Update available",
            f"Version {info.version} is available (you have {get_app_version()}).",
            parent=self,
        )
        open_btn = box.addButton("Open Download Page", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Later", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is open_btn:
            QDesktopServices.openUrl(QUrl(info.url))

    def _try_location_op(self, fn):
        """Runs a DocumentController save/submit/approve/reject call,
        converting a LocationUnavailableError -- the destination folder
        itself is unreachable, e.g. an offline network share -- into a
        plain warning dialog instead of letting it propagate uncaught.
        Distinct from those methods' own (bool, message) return, which
        is reserved for schema-validation failures and would otherwise
        get routed through friendly_validation_error() -- XSD-error-
        shaped-text-specific, and misleading for a connectivity
        problem. Returns None on this failure so the caller can bail
        out the same way it already does for `not ok`."""
        try:
            return fn()
        except LocationUnavailableError as e:
            QMessageBox.warning(self, "Couldn't reach that folder", str(e))
            return None

    def _on_save(self):
        outcome = self._try_location_op(self.doc_controller.save_file)
        if outcome is None:
            return
        ok, message = outcome
        if not ok:
            self._show_validation_error(message)
            return
        self.status_bar.set_file(message)
        self._prompt_and_commit(self.doc_controller.current_file)

    def _show_validation_error(self, raw_message: str):
        box = QMessageBox(
            QMessageBox.Icon.Warning, "This record isn't ready to save yet",
            friendly_validation_error(raw_message), parent=self,
        )
        box.setDetailedText(raw_message)
        box.exec()

    def _on_undo(self):
        if not self.doc_controller.undo():
            return
        self.form_panel.show_editor('', {})

    def _on_submit(self):
        outcome = self._try_location_op(self.doc_controller.submit_file)
        if outcome is None:
            return
        ok, result = outcome
        if not ok:
            self._show_validation_error(result)
            return
        self.status_bar.set_file(f"{result} (submitted)")
        self._prompt_and_commit(result)

    def _on_cancel(self):
        self._return_to_start()

    def _on_approve(self):
        outcome = self._try_location_op(self.doc_controller.approve_file)
        if outcome is None:
            return
        ok, result = outcome
        if not ok:
            QMessageBox.warning(self, "Approve failed", result)
            return
        self.status_bar.set_file(f"{result} (approved)")
        self._prompt_and_commit(result)

    def _on_reject(self):
        outcome = self._try_location_op(self.doc_controller.reject_file)
        if outcome is None:
            return
        ok, result = outcome
        if not ok:
            QMessageBox.warning(self, "Reject failed", result)
            return
        self.status_bar.set_file(f"{result} (rejected)")
        self._prompt_and_commit(result)

    def _prompt_and_commit(self, path: str):
        """Asks the user for a commit comment and, if they give one,
        commits `path` to the shared edit/reviewed version-control
        repo under their login name. Cancelling or leaving the comment
        blank skips the commit -- the save/approve itself already
        happened either way."""
        comment, accepted = QInputDialog.getMultiLineText(
            self, "Commit comment", "Describe this change for the version history:",
        )
        if not accepted or not comment.strip():
            return
        result = add_file_to_repo(path, comment.strip())
        if result is None:
            QMessageBox.warning(
                self, "Commit failed",
                f"{path} was saved, but could not be committed to the version-control repository.",
            )
        elif result == 'fallback':
            # Not a failure -- add_file_to_repo already recorded this
            # commit locally when the shared repo location wasn't
            # reachable, and folds it into the shared history
            # automatically the next time it is (see commit_to_git.py's
            # _replay_fallback). Worth a heads-up rather than silence,
            # since "Audits" won't show this commit until that happens.
            QMessageBox.information(
                self, "Recorded locally",
                f"{path} was saved and committed, but the shared version-history location "
                "isn't reachable right now. This commit was recorded locally instead, and "
                "will be added to the shared history automatically once it's reachable again.",
            )

    def _on_autofill(self):
        ...

    def _on_import(self):
        locations = load_locations()  # re-read so it reflects the latest Settings
        ingest_dir = locations.get('ingest')
        edit_dir = locations.get('edit')
        if ingest_dir is None or edit_dir is None:
            QMessageBox.warning(
                self, "Missing location",
                "Both 'ingest' and 'edit' folders must be configured in vra-config.ini.",
            )
            return

        dlg = ImportProgressDialog(ingest_dir, edit_dir, parent=self)
        dlg.exec()

    def _on_sync_media(self):
        dlg = MediaSyncDialog(self.doc_controller, parent=self)
        dlg.exec()
