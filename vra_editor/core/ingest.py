import shutil
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

# Register standard VRA Core 4 and XML namespaces to maintain clean tag formatting
NAMESPACES = {
    'vra': 'http://www.vraweb.org/vracore4.htm',
    'xml': 'http://www.w3.org/XML/1998/namespace',
    'xsi': 'http://www.w3.org/2001/XMLSchema-instance'
}

for prefix, uri in NAMESPACES.items():
    ET.register_namespace(prefix, uri)


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


def merge_xml_elements(target: ET.Element, source: ET.Element):
    """
    Recursively merges `source` XML nodes into `target`.
    Combines set containers (e.g., <titleSet>) and appends unique language elements.
    """
    # Copy any missing attributes from source element to target
    for attr_key, attr_val in source.attrib.items():
        if attr_key not in target.attrib:
            target.attrib[attr_key] = attr_val

    for source_child in list(source):
        matching_targets = [t for t in target if t.tag == source_child.tag]

        # If source_child is a container set with child elements, recurse into target container
        if matching_targets and len(source_child) > 0:
            merge_xml_elements(matching_targets[0], source_child)
        else:
            # If it's a leaf node or new element, append if it doesn't already exist
            if not any(is_identical_element(t, source_child) for t in target):
                target.append(source_child)


def process_vra_directory(input_dir: str, output_dir: str, progress_callback=None):
    """Scans input_dir for VRA-Core XML files, merges files that share a
    record ID, and writes one file per record into output_dir. Source
    files are moved into a "done" subfolder of input_dir once handled --
    whether that meant writing/merging them or skipping because a file
    with that record ID already exists in output_dir -- so re-running
    only ever processes what's newly arrived, and a record ID already
    present in output_dir isn't overwritten.

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

    report(0, 0, f"Scanning '{input_dir}' for VRA-Core XML files...")
    for file_path in sorted(input_path.glob("*.xml")):
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
            for _, secondary_tree in files[1:]:
                merge_xml_elements(primary_root, secondary_tree.getroot())
        else:
            report(index, total, f" -> Writing single file for ID '{rec_id}'...")

        # Format XML output with clean indentation
        if hasattr(ET, 'indent'):
            ET.indent(primary_tree, space="  ")

        out_file = output_path / f"{rec_id}.xml"
        if out_file.exists():
            report(index, total, f" [!] '{rec_id}' already exists in '{output_dir}' -- not overwritten.")
        else:
            primary_tree.write(out_file, encoding="utf-8", xml_declaration=True)

        # Whether written or skipped as a duplicate, this ingest batch is
        # done with these source files -- move them out either way so a
        # re-run doesn't keep re-reporting the same already-handled ones.
        for file_path, _ in files:
            dest = done_path / file_path.name
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
