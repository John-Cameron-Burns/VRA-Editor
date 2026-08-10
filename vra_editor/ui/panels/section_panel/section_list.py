from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import QVBoxLayout, QListWidget, QListWidgetItem, QLabel
from PySide6.QtCore import Signal

from vra_editor.core.friendly_labels import friendly_label
from vra_editor.ui.widgets.background_image_widget import BackgroundImageWidget

# Cataloguing relevance, not the XSD's roughly-alphabetical declaration
# order -- what a cataloguer wants to see/fill in first (what is it,
# what kind of thing, who made it, when) leads; anything the schema
# adds later that isn't in this list just falls in after these.
SECTION_ORDER = [
    'titleSet', 'worktypeSet', 'agentSet', 'dateSet', 'descriptionSet',
    'subjectSet', 'stylePeriodSet', 'culturalContextSet', 'materialSet',
    'techniqueSet', 'measurementsSet', 'locationSet', 'inscriptionSet',
    'sourceSet', 'rightsSet', 'stateEditionSet', 'relationSet', 'textrefSet',
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
        ordered_tags = SECTION_ORDER + [t for t in valid_tags if t not in SECTION_ORDER]

        for tag in ordered_tags:
            if tag not in valid_tags:
                continue
            node = present_by_tag.get(tag)
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
