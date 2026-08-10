from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import QVBoxLayout, QTreeWidget, QTreeWidgetItem, QMenu

from vra_editor.core.xml_parser import VraXmlParser, VraTreeNode
from vra_editor.ui.widgets.background_image_widget import BackgroundImageWidget

_NODE_TYPE_ROLE = 100
_NODE_DATA_ROLE = 101
_NODE_ELEMENT_ROLE = 102
_NODE_CHILD_SPECS_ROLE = 103


class VraTreePanel(BackgroundImageWidget):
    """Left Panel: XML Hierarchy Tree."""

    element_selected = Signal(str, dict, object)  # node_type, data, lxml element
    add_child_requested = Signal(object, str, list)  # parent element, tag, sibling schema order
    remove_requested = Signal(object)  # lxml element to remove

    def __init__(self, image_path=None, parent=None):
        super().__init__(image_path, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 8, 8)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("VRA Core 4 Structure")
        # Translucent rather than the tree view's usual opaque white, so
        # the panel's background image reads as a faint texture behind
        # it instead of being completely hidden -- still light enough
        # that item text stays fully legible.
        self.tree.setStyleSheet(
            "QTreeWidget { background-color: rgba(255, 255, 255, 217); border: 1px solid #ccc; }"
        )
        layout.addWidget(self.tree)

        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)

        for key in (QKeySequence.StandardKey.Delete, QKeySequence("Backspace")):
            shortcut = QShortcut(key, self.tree)
            shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
            shortcut.activated.connect(self._delete_selected)

    def load_document(self, parser: VraXmlParser):
        """Rebuilds the tree from whatever document `parser` currently
        has loaded. Called whenever DocumentController.document_loaded
        fires."""
        self.tree.clear()
        for node in parser.build_tree():
            self._add_node(self.tree, node)
        self.tree.expandAll()

    def select_element(self, element):
        """Finds the tree item for `element` (by identity) and selects
        it, as if the user had clicked it. Used after inserting a new
        element so the user lands straight on what they just added."""
        if element is None:
            return
        match = self._find_item(self.tree.invisibleRootItem(), element)
        if match is not None:
            self.tree.setCurrentItem(match)
            self.tree.scrollToItem(match)
            self._on_item_clicked(match, 0)

    def _find_item(self, parent_item, element):
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            if child.data(0, _NODE_ELEMENT_ROLE) is element:
                return child
            found = self._find_item(child, element)
            if found is not None:
                return found
        return None

    def _add_node(self, parent, node: VraTreeNode) -> QTreeWidgetItem:
        item = QTreeWidgetItem(parent, [node.label])
        item.setData(0, _NODE_TYPE_ROLE, node.node_type)
        item.setData(0, _NODE_DATA_ROLE, node.data)
        item.setData(0, _NODE_ELEMENT_ROLE, node.element)
        item.setData(0, _NODE_CHILD_SPECS_ROLE, node.child_specs)
        if node.node_type == 'set':
            font = item.font(0)
            font.setBold(True)
            item.setFont(0, font)
        for child in node.children:
            self._add_node(item, child)
        return item

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        node_type = item.data(0, _NODE_TYPE_ROLE)
        node_data = item.data(0, _NODE_DATA_ROLE) or {}
        element = item.data(0, _NODE_ELEMENT_ROLE)
        if node_type:
            self.element_selected.emit(node_type, node_data, element)

    def _on_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        if item is None:
            return

        child_specs = item.data(0, _NODE_CHILD_SPECS_ROLE) or ()
        element = item.data(0, _NODE_ELEMENT_ROLE)
        node_type = item.data(0, _NODE_TYPE_ROLE)

        menu = QMenu(self)
        if child_specs:
            add_menu = menu.addMenu("Add")
            sibling_order = [spec.tag for spec in child_specs]
            for spec in child_specs:
                action = add_menu.addAction(spec.tag)
                action.triggered.connect(
                    lambda _checked=False, e=element, t=spec.tag, order=sibling_order:
                    self.add_child_requested.emit(e, t, order)
                )

        if self._is_removable(item):
            remove_action = menu.addAction("Remove")
            remove_action.triggered.connect(
                lambda _checked=False, e=element: self.remove_requested.emit(e)
            )

        if not menu.isEmpty():
            menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _is_removable(self, item: QTreeWidgetItem) -> bool:
        node_type = item.data(0, _NODE_TYPE_ROLE)
        element = item.data(0, _NODE_ELEMENT_ROLE)
        return node_type != 'record' and element is not None

    def _delete_selected(self):
        item = self.tree.currentItem()
        if item is None or not self._is_removable(item):
            return
        self.remove_requested.emit(item.data(0, _NODE_ELEMENT_ROLE))
