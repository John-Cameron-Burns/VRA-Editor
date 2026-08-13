from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import QVBoxLayout, QListWidget, QListWidgetItem, QLabel
from PySide6.QtCore import Qt, Signal

from vra_editor.core.friendly_labels import friendly_label
from vra_editor.ui.widgets.background_image_widget import BackgroundImageWidget

# Three tiers, each in a deliberately-chosen order (not cataloguing
# frequency, not the XSD's roughly-alphabetical declaration order) --
# how central a section is to describing the work, from "practically
# every record has this" down to "only some records need this". Any
# schema-valid Set that doesn't appear in any tier below (shouldn't
# normally happen -- every current VRA Core 4 Set is accounted for)
# still shows up, in an "Other" tier at the end, rather than silently
# vanishing from the list.
SECTION_GROUPS = [
    ("Basic", [
        'inscriptionSet', 'dateSet', 'locationSet', 'descriptionSet',
        'titleSet', 'relationSet',
    ]),
    ("Advanced", [
        'agentSet', 'rightsSet', 'sourceSet', 'materialSet',
        'techniqueSet', 'worktypeSet', 'measurementsSet',
    ]),
    ("Optional", [
        'subjectSet', 'culturalContextSet', 'stylePeriodSet',
        'stateEditionSet', 'textrefSet',
    ]),
]

_NODE_ROLE = 100
_ADD_TAG_ROLE = 101
_SIBLING_ORDER_ROLE = 102


class SectionListPanel(BackgroundImageWidget):
    """Left-hand navigation for the sectioned form: one row per Set
    present in the record (Titles, People, Dates, ...), plus a greyed
    "+ Add" row for any Set type this record doesn't have yet."""

    section_selected = Signal(object)  # VraTreeNode for the chosen Set
    add_section_requested = Signal(str, list)  # tag, sibling_order

    def __init__(self, image_path=None, parent=None):
        super().__init__(image_path, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 8, 8)

        header = QLabel("<b>Sections</b>")
        layout.addWidget(header)
        # Unlike list_widget below, this label has no opaque background
        # of its own -- without this, the raw background image would
        # show through right behind/around the title instead of staying
        # clear of it the way _MARGIN alone keeps it off the panel edges.
        self.set_top_inset(header.sizeHint().height() + layout.contentsMargins().top())

        self.list_widget = QListWidget()
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        # Translucent rather than the item view's usual opaque white, so
        # the panel's background image reads as a faint texture behind
        # the list instead of being completely hidden by it -- still
        # light enough that item text stays fully legible.
        self.list_widget.setStyleSheet(
            "QListWidget { background-color: rgba(255, 255, 255, 217); border: 1px solid #ccc; }"
        )
        layout.addWidget(self.list_widget)

    def load_record(self, record_node):
        """record_node is the top-level VraTreeNode from build_tree(),
        or None if nothing's loaded."""
        self.list_widget.clear()
        if record_node is None:
            return

        present_by_tag = {
            n.data.get('tag'): n for n in record_node.children if n.node_type == 'set'
        }
        # A collection's schema-valid children also include nested work/image
        # sub-records -- those are whole other records, not metadata Sets,
        # so they don't belong in this list at all.
        valid_tags = [spec.tag for spec in record_node.child_specs if spec.tag.endswith('Set')]
        grouped_tags = {tag for _, tags in SECTION_GROUPS for tag in tags}
        groups = list(SECTION_GROUPS)
        leftover = [t for t in valid_tags if t not in grouped_tags]
        if leftover:
            groups = groups + [("Other", leftover)]

        for label, tags in groups:
            tags_in_record = [t for t in tags if t in valid_tags]
            if not tags_in_record:
                continue  # this record type doesn't have any Set from this tier at all
            self._add_group_header(label)
            for tag in tags_in_record:
                self._add_section_item(tag, present_by_tag.get(tag), valid_tags)

    def _add_group_header(self, label: str):
        item = QListWidgetItem(label.upper())
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        font = item.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() - 1)
        font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 110)
        item.setFont(font)
        item.setForeground(QBrush(QColor("#5B655F")))
        item.setBackground(QBrush(QColor(46, 125, 91, 28)))  # faint tint of the app's own accent green
        self.list_widget.addItem(item)

    def _add_section_item(self, tag: str, node, valid_tags: list):
        if node is not None:
            count = len([c for c in node.children if c.node_type != 'display'])
            suffix = f"  ({count})" if count else ""
            item = QListWidgetItem(f"{friendly_label(tag)}{suffix}")
            # Bold + full contrast: this section has content, matching
            # the tree view's own convention of bolding Set-level nodes.
            # Foreground set explicitly (not left to the OS palette) --
            # the list's background is forced to near-white above, and
            # in dark mode the palette's default text color is white too,
            # which would make these invisible against it.
            font = item.font()
            font.setBold(True)
            item.setFont(font)
            item.setForeground(QBrush(QColor("#1a1a1a")))
            item.setData(_NODE_ROLE, node)
        else:
            item = QListWidgetItem(f"+ Add {friendly_label(tag)}")
            # Italic + muted, not just muted: reads as an available
            # action rather than a disabled/empty version of the rows
            # above it.
            font = item.font()
            font.setItalic(True)
            item.setFont(font)
            item.setForeground(QBrush(QColor("#888")))
            item.setToolTip(f"Add a {friendly_label(tag)} section to this record")
            item.setData(_ADD_TAG_ROLE, tag)
            item.setData(_SIBLING_ORDER_ROLE, valid_tags)
        self.list_widget.addItem(item)

    def _on_item_clicked(self, item: QListWidgetItem):
        node = item.data(_NODE_ROLE)
        if node is not None:
            self.section_selected.emit(node)
            return
        tag = item.data(_ADD_TAG_ROLE)
        if tag is not None:
            self.add_section_requested.emit(tag, item.data(_SIBLING_ORDER_ROLE))
