import shutil
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

from .display_i18n import build_display_html, parse_display_html

# Register standard VRA Core 4 and XML namespaces to maintain clean tag formatting
NAMESPACES = {
    'vra': 'http://www.vraweb.org/vracore4.htm',
    'xml': 'http://www.w3.org/XML/1998/namespace',
    'xsi': 'http://www.w3.org/2001/XMLSchema-instance'
}

for prefix, uri in NAMESPACES.items():
    ET.register_namespace(prefix, uri)

_XML_LANG_ATTR = '{http://www.w3.org/XML/1998/namespace}lang'

# display/notes: the schema allows only one per Set, so a same-tag
# "conflict" here isn't a second item -- it's the same field in another
# language, and has to be merged into the one element that's allowed to
# exist (this app's own div-per-language convention), not appended as an
# invalid second sibling.
_SINGLE_PER_SET_TAGS = {'display', 'notes'}

# The only leaf element type in the schema (dateWrapperType, used only by
# earliestDate/latestDate) that carries no vraAttributes at all -- xml:lang
# isn't a valid attribute on these, so a same-tag conflict here is a
# genuine data discrepancy between the source files, not a translation.
_NO_LANG_TAGS = {'earliestDate', 'latestDate'}


def _localname(tag: str) -> str:
    return tag.split('}', 1)[1] if tag.startswith('{') else tag


def _record_lang(root: ET.Element) -> str:
    """The xml:lang declared on a source file's own record element
    (<work>/<image>/<collection>), or '' if it doesn't declare one."""
    if _localname(root.tag) in ('work', 'image', 'collection'):
        return root.get(_XML_LANG_ATTR, '')
    for child in root:
        if isinstance(child.tag, str) and _localname(child.tag) in ('work', 'image', 'collection'):
            return child.get(_XML_LANG_ATTR, '')
    return ''


def _merge_single_per_set(target_elem: ET.Element, source_elem: ET.Element,
                           target_lang: str, source_lang: str) -> None:
    """Folds source_elem's text into target_elem (a <display> or <notes>)
    as an additional language entry, instead of leaving it a separate,
    schema-invalid second element."""
    translations = parse_display_html(target_elem.text)
    if not translations:
        existing_text = (target_elem.text or '').strip()
        translations = {target_lang: existing_text} if existing_text else {}
    new_text = (source_elem.text or '').strip()
    if new_text:
        translations[source_lang] = new_text
    target_elem.text = build_display_html(translations)


def extract_vra_id(root: ET.Element) -> str:
    """Extracts the VRA record ID from root or sub-elements (<work>, <image>, etc.)."""
    # Check root attribute
    if 'id' in root.attrib:
        return root.attrib['id']

    # Check top-level VRA elements (work, image, collection)
    for child in root:
        if 'id' in child.attrib:
            return child.attrib['id']

    # Fallback search anywhere in the tree
    for elem in root.iter():
        if 'id' in elem.attrib:
            return elem.attrib['id']

    return None


def is_identical_element(e1: ET.Element, e2: ET.Element) -> bool:
    """Checks if two XML elements are structurally and textually identical."""
    if e1.tag != e2.tag or e1.attrib != e2.attrib:
        return False
    if (e1.text or '').strip() != (e2.text or '').strip():
        return False
    if (e1.tail or '').strip() != (e2.tail or '').strip():
        return False
    if len(e1) != len(e2):
        return False
    return all(is_identical_element(c1, c2) for c1, c2 in zip(e1, e2))


def merge_xml_elements(target: ET.Element, source: ET.Element,
                        target_lang: str = '', source_lang: str = '', report=None):
    """
    Recursively merges `source` XML nodes into `target`.
    Combines set containers (e.g., <titleSet>) and appends unique language elements.

    target_lang/source_lang are each source file's own declared xml:lang
    (see _record_lang), threaded through the recursion unchanged so a
    leaf collision several levels deep (e.g. agent > dates > earliestDate)
    still knows which language each side came from. report, if given, is
    called with a message string for anything that needed a judgment call
    -- currently only genuine data conflicts on elements that can't carry
    xml:lang (see _NO_LANG_TAGS).
    """
    if report is None:
        report = lambda _msg: None

    # Copy any missing attributes from source element to target
    for attr_key, attr_val in source.attrib.items():
        if attr_key not in target.attrib:
            target.attrib[attr_key] = attr_val

    for source_child in list(source):
        tag = _localname(source_child.tag)
        matching_targets = [t for t in target if t.tag == source_child.tag]

        if matching_targets and len(source_child) > 0:
            # A container with an existing same-tag sibling -- recurse to
            # merge its own fields rather than treating the whole thing
            # as one leaf value to compare/duplicate.
            merge_xml_elements(matching_targets[0], source_child, target_lang, source_lang, report)
            continue

        if not matching_targets:
            # Genuinely new -- nothing to reconcile against. Leaves still
            # get tagged with source_lang (when eligible) so they read as
            # "this field, in that language" rather than an untraceable
            # extra value.
            if source_lang and len(source_child) == 0 and tag not in _NO_LANG_TAGS:
                source_child.set(_XML_LANG_ATTR, source_lang)
            target.append(source_child)
            continue

        # A same-tag leaf already exists in target. Either it's a plain
        # duplicate (skip), or the same field expressed in another
        # language -- which used to get silently appended as an
        # untagged, and sometimes schema-invalid, extra sibling.
        if any(is_identical_element(t, source_child) for t in matching_targets):
            continue

        if tag in _SINGLE_PER_SET_TAGS:
            _merge_single_per_set(matching_targets[0], source_child, target_lang, source_lang)
        elif tag in _NO_LANG_TAGS:
            report(
                f"    [!] <{tag}> conflict: keeping '{matching_targets[0].text}', "
                f"discarding source's '{source_child.text}' -- this element can't "
                f"carry xml:lang, so the two source files disagreeing here needs "
                f"a human to reconcile, not a merge."
            )
        else:
            if source_lang:
                source_child.set(_XML_LANG_ATTR, source_lang)
            target.append(source_child)


def process_vra_directory(input_dir: str, output_dir: str, progress_callback=None):
    """Scans input_dir -- including nested subfolders -- for VRA-Core XML
    files, merges files that share a record ID, and writes one file per
    record into output_dir. A merged record lands under the same
    subfolder its first (primary) source file was found in, e.g.
    input_dir/collectionA/foo.xml produces output_dir/collectionA/<id>.xml,
    not a flattened output_dir/<id>.xml -- callers further down the
    pipeline (Submit/Approve/Reject) preserve that same relative path
    from then on. Source files are moved into a "done" subfolder of
    input_dir once handled -- whether that meant writing/merging them or
    skipping because a file with that record ID already exists anywhere
    under output_dir -- each mirroring its own original subfolder there
    too, so re-running only ever processes what's newly arrived, and a
    record ID already present in output_dir isn't overwritten.

    progress_callback, if given, is called as
    progress_callback(current: int, total: int, message: str) at each
    step -- current/total are both 0 during the initial scan (before
    the record count is known) and 1..total afterward, which callers
    can use to drive an indeterminate-then-determinate progress bar.
    Falls back to plain print() when no callback is given, so this
    still works as a standalone script.
    """

    def report(current: int, total: int, message: str):
        if progress_callback:
            progress_callback(current, total, message)
        else:
            print(message)

    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    done_path = input_path / "done"

    # 1. Scan and group XML files by record ID
    records_by_id = defaultdict(list)

    report(0, 0, f"Scanning '{input_dir}' (including subfolders) for VRA-Core XML files...")
    for file_path in sorted(input_path.rglob("*.xml")):
        if file_path.is_relative_to(done_path):
            continue  # already-processed files from a previous run -- not new arrivals
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            rec_id = extract_vra_id(root)

            if rec_id:
                records_by_id[rec_id].append((file_path, tree))
            else:
                report(0, 0, f" [!] Warning: No 'id' attribute found in '{file_path.name}'. Skipping.")
        except ET.ParseError as e:
            report(0, 0, f" [!] Error parsing '{file_path.name}': {e}")

    # 2. Merge records, save to output directory, move sources to done/
    total = len(records_by_id)
    report(0, total, f"Found {total} unique record ID(s). Processing...")

    if total:
        done_path.mkdir(parents=True, exist_ok=True)

    for index, (rec_id, files) in enumerate(records_by_id.items(), start=1):
        primary_path, primary_tree = files[0]
        primary_root = primary_tree.getroot()

        if len(files) > 1:
            report(index, total, f" -> Merging {len(files)} files for ID '{rec_id}'...")
            primary_lang = _record_lang(primary_root)
            for _, secondary_tree in files[1:]:
                secondary_root = secondary_tree.getroot()
                secondary_lang = _record_lang(secondary_root)
                merge_xml_elements(
                    primary_root, secondary_root, primary_lang, secondary_lang,
                    report=lambda msg: report(index, total, msg),
                )
        else:
            report(index, total, f" -> Writing single file for ID '{rec_id}'...")

        # Format XML output with clean indentation
        if hasattr(ET, 'indent'):
            ET.indent(primary_tree, space="  ")

        # Record IDs are meant to be globally unique, so the existence
        # check looks anywhere under output_dir, not just in the
        # subfolder this batch would land in -- the same ID showing up
        # under a different subfolder is still a duplicate, not a
        # legitimately different record.
        existing = next(output_path.rglob(f"{rec_id}.xml"), None)
        if existing is not None:
            report(index, total,
                   f" [!] '{rec_id}' already exists in '{existing.relative_to(output_path)}' -- not overwritten.")
        else:
            relative_dir = primary_path.parent.relative_to(input_path)
            out_file = output_path / relative_dir / f"{rec_id}.xml"
            out_file.parent.mkdir(parents=True, exist_ok=True)
            primary_tree.write(out_file, encoding="utf-8", xml_declaration=True)

        # Whether written or skipped as a duplicate, this ingest batch is
        # done with these source files -- move them out either way so a
        # re-run doesn't keep re-reporting the same already-handled ones.
        # Each source file mirrors its own original subfolder under
        # done/, which need not match the merged record's own (a
        # secondary file for the same ID could have arrived from a
        # different subfolder than the primary).
        for file_path, _ in files:
            relative_dir = file_path.parent.relative_to(input_path)
            dest_dir = done_path / relative_dir
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / file_path.name
            if dest.exists():
                dest.unlink()
            shutil.move(str(file_path), str(dest))
        report(index, total, f" -> Moved {len(files)} source file(s) for '{rec_id}' to '{done_path.name}/'.")

    report(total, total, f"Finished! Processed {total} record(s).")


if __name__ == "__main__":
    # Specify your source and target directories here
    INPUT_DIR = "./vra_files"
    OUTPUT_DIR = "./merged_vra_files"

    process_vra_directory(INPUT_DIR, OUTPUT_DIR)
