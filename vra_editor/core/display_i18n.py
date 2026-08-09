"""
Embeds multiple language variants of a VRA display/notes value as HTML
<div lang="..."> fragments inside ONE <display> or <notes> text element,
instead of duplicating the enclosing Set per language.

This keeps the element schema-valid (display/notes stay plain string
content -- there's still exactly one <display> per Set), at the cost
of layering an app-specific convention on top of it: other VRA Core
consumers will see the raw escaped markup as the display text, not
parsed-out translations. That trade-off is deliberate here.
"""

import xml.etree.ElementTree as ET

DisplayTranslations = dict[str, str]  # {lang_code: text}, e.g. {'en': '...', 'fr': '...'}


def build_display_html(translations: DisplayTranslations) -> str:
    """{'en': 'Landscape with figures', 'fr': 'Paysage avec figures'}
    -> '<div lang="en">Landscape with figures</div><div lang="fr">Paysage avec figures</div>'

    Returns the raw HTML string. Assign it directly to an element's
    .text -- ElementTree escapes '<'/'>'/'&' automatically when the
    tree is serialized, so the file stays well-formed XML.
    """
    parts = []
    for lang, text in translations.items():
        div = ET.Element('div', lang=lang)
        div.text = text
        parts.append(ET.tostring(div, encoding='unicode'))
    return ''.join(parts)


def parse_display_html(raw_text: str | None) -> DisplayTranslations:
    """Reverse of build_display_html. Given an element's .text (already
    unescaped by ElementTree on parse), extracts {lang: text} for each
    embedded <div lang="...">. Returns {} for empty/malformed input --
    callers should treat that as "no translations found" and fall back
    to displaying raw_text as a single untranslated value.
    """
    if not raw_text or not raw_text.strip():
        return {}
    try:
        root = ET.fromstring(f"<root>{raw_text}</root>")
    except ET.ParseError:
        return {}
    return {
        div.get('lang', ''): (div.text or '').strip()
        for div in root.findall('div')
    }


def set_display(display_elem: ET.Element, translations: DisplayTranslations):
    """Convenience: write translations onto an existing <display> element."""
    display_elem.text = build_display_html(translations)


def get_display(display_elem: ET.Element) -> DisplayTranslations:
    """Convenience: read translations back out of a <display> element."""
    return parse_display_html(display_elem.text)


if __name__ == '__main__':
    # Round-trip demo
    dateset = ET.Element('dateSet')
    display = ET.SubElement(dateset, 'display')
    set_display(display, {
        'en': '1776 (creation)',
        'fr': '1776 (création)',
    })

    date = ET.SubElement(dateset, 'date', type='creation')
    ET.SubElement(date, 'earliestDate').text = '1776'
    ET.SubElement(date, 'latestDate').text = '1776'

    xml_bytes = ET.tostring(dateset, encoding='unicode')
    print("Serialized (note the escaped divs inside <display>):\n")
    print(xml_bytes)

    # Parse it back
    parsed = ET.fromstring(xml_bytes)
    round_tripped = get_display(parsed.find('display'))
    print("\nParsed back out:", round_tripped)
