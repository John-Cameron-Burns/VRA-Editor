from lxml import etree

VRA_NS = "http://www.vraweb.org/vracore4.htm"
NSMAP = {None: VRA_NS}

class VraXmlParser:
    """Pure Python XML generator and parser."""

    @staticmethod
    def create_sample_xml() -> str:
        root = etree.Element(f"{{{VRA_NS}}}vra", nsmap=NSMAP)
        work = etree.SubElement(root, f"{{{VRA_NS}}}work", id="w_101")
        
        # Agent Set
        agent_set = etree.SubElement(work, f"{{{VRA_NS}}}agentSet")
        agent = etree.SubElement(agent_set, f"{{{VRA_NS}}}agent")
        name = etree.SubElement(agent, f"{{{VRA_NS}}}name")
        name.text = "Vincent van Gogh"
        role = etree.SubElement(agent, f"{{{VRA_NS}}}role")
        role.text = "Artist"

        # Title Set
        title_set = etree.SubElement(work, f"{{{VRA_NS}}}titleSet")
        title = etree.SubElement(title_set, f"{{{VRA_NS}}}title")
        title.text = "Starry Night"

        return etree.tostring(root, pretty_print=True, encoding="utf-8").decode("utf-8")
