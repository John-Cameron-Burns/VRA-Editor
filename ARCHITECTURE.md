# VRA Core 4 Editor Architecture

This application strictly separates domain logic from user interface elements to ensure easy long-term maintenance.

## Folder Overview

- `main.py`: Entry point for the application.
- `vra_editor/core/`: **Pure Python logic.** Zero PySide6/Qt code.
  - `xml_parser.py` / `vra_structure.py`: Schema-driven XML tree walking, mutation, and the VRA Core 4 element/child map (built from the bundled XSDs, not hand-coded).
  - `schema_validator.py`: XSD validation against the strict schema.
  - `friendly_labels.py`: Tag-name-to-human-label and enum-value humanizing.
  - `display_i18n.py`: The `<display>`/`<notes>` div-per-language encoding.
  - `review_notes.py`: Reviewer notes, stored as an XML comment rather than document content.
  - `media_metadata.py`: Image dimension/EXIF/IPTC reading and EXIF/IPTC writing (Pillow + pyexiv2), used by the media-linking feature.
  - `authority_lookup.py` / `vocab_cache.py`: VIAF/Getty/GNS/Library of Congress vocabulary search, backed by a local SQLite FTS cache.
  - `commit_to_git.py` / `audit_log.py`: The archive's shared revision history (a dulwich repo kept under the app's own data folder) and reading it back for the Audits dialog.
  - `ingest.py`: Merges newly-arrived source files into the edit folder.
- `vra_editor/controllers/document_controller.py`: Owns document state (the loaded record, undo stack, dirty tracking) and announces changes via Qt signals. Everything the UI does to a document goes through here.
- `vra_editor/ui/`: PySide6 graphical components.
  - `main_window.py`: Top-level layout, the grouped toolbar, and mode handling.
  - `panels/section_panel/`: The default Simple view -- section list plus per-section forms.
  - `panels/form_panel/`: Advanced view's structure tree and single-element editor.
  - `panels/tree_panel/`: Advanced view's element tree widget.
  - `panels/xml_preview/`: Raw XML preview with highlight-on-select.
  - `panels/center_pane.py` / `panels/media_preview_panel.py`: The linked-media preview band and its Inject/Extract/Thumbnail tools.
  - `panels/review_notes_panel.py`: Reviewer notes panel.
  - `dialogs/`: Settings, Help (renders `resources/user_manual.md`), Audits (revision history + restore), vocabulary search, file picker, import progress.
  - `widgets/`: Small reusable pieces (auto-growing text edit, painted background image).
- `vra_editor/resources/`: Runtime data the app actually loads -- `vra_core4.xsd`/`vra_core4_strict.xsd`/`xml.xsd` (schema validation) and `user_manual.md` (Help). Nothing else here ships in the packaged app; see `packaging/VRA_Editor.spec`.
- `packaging/VRA_Editor.spec`: PyInstaller spec for building the distributable macOS `.app`.

## How to Add a New Element Form
1. Add a new editor widget in `vra_editor/ui/panels/form_panel/`.
2. Register the widget inside `FormContainerPanel` in `form_container.py`.
3. Connect signal updates to `DocumentController`.
