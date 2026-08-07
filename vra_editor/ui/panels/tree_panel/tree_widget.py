from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem

class VraTreePanel(QWidget):
    """Left Panel: XML Hierarchy Tree."""

    element_selected = Signal(str, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("VRA Core 4 Structure")
        layout.addWidget(self.tree)

        self._populate_tree()
        self.tree.itemClicked.connect(self._on_item_clicked)

    def _populate_tree(self):
        root = QTreeWidgetItem(self.tree, ["Work (id: w_101)"])
        root.setData(0, 100, "work")

        agent_node = QTreeWidgetItem(root, ["Agent: Vincent van Gogh"])
        agent_node.setData(0, 100, "agent")
        agent_node.setData(0, 101, {"name": "Vincent van Gogh", "role": "Artist"})

        title_node = QTreeWidgetItem(root, ["Title: Starry Night"])
        title_node.setData(0, 100, "title")
        title_node.setData(0, 101, {"title": "Starry Night", "type": "Repository"})

        self.tree.expandAll()

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        node_type = item.data(0, 100)
        node_data = item.data(0, 101) or {}
        if node_type:
            self.element_selected.emit(node_type, node_data)
