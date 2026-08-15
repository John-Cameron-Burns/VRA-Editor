from pathlib import Path

from lxml import etree

RESOURCES_DIR = Path(__file__).resolve().parent.parent / "resources"
# vra_core4.xsd is explicitly the *unrestricted* variant ("all attributes are
# uncontrolled", per its own header) -- every sample record's own
# xsi:schemaLocation declares conformance to the *strict* schema instead,
# which redefines vra_core4_strict.xsd's controlled-vocabulary attributes
# (title type, relation type, ...) as real enumerations. Validating against
# the unrestricted one let invalid attribute values silently pass.
DEFAULT_XSD_PATH = RESOURCES_DIR / "vra_core4_strict.xsd"


class SchemaValidator:
    """Validates XML against VRA Core 4 XSD definitions."""

    def __init__(self, xsd_path: str = None):
        self.xsd_path = xsd_path

    def validate(self, xml_bytes: bytes) -> tuple[bool, str]:
        if not self.xsd_path:
            return True, "Validation skipped (No XSD file set)"
        try:
            schema_doc = etree.parse(self.xsd_path)
            schema = etree.XMLSchema(schema_doc)
            doc = etree.fromstring(xml_bytes)
            schema.assertValid(doc)
            return True, "XML Valid"
        except Exception as e:
            return False, str(e)
