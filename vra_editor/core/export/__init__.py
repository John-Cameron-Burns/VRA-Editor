"""Crosswalks from VRA Core 4 to other metadata schemas -- pure Python,
no PySide6, same as the rest of vra_editor.core. Each module here takes
a loaded record's own lxml element (work/image/collection, as produced
by VraXmlParser.build_tree()) and produces another schema's XML text.
"""
