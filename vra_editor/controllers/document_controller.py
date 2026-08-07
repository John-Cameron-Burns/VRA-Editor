from PySide6.QtCore import QObject, Signal
from vra_editor.core.xml_parser import VraXmlParser

class DocumentController(QObject):
    """Coordinates application state between models and UI updates."""

    xml_updated = Signal(str)

    def __init__(self):
        super().__init__()
        self.current_xml = VraXmlParser.create_sample_xml()

    def get_initial_xml(self) -> str:
        return self.current_xml

    def update_agent_data(self, name: str, role: str):
        # Update logic: updates raw XML string representation
        self.current_xml = self.current_xml.replace(
            "Vincent van Gogh", name if name else "Vincent van Gogh"
        )
        self.xml_updated.emit(self.current_xml)
