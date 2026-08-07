from lxml import etree

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
