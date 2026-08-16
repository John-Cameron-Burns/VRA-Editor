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
  - `commit_to_git.py` / `audit_log.py`: The archive's shared revision history (a dulwich repo kept under the app's own data folder) and reading it back for the Audits dialog. `commit_to_git.add_file_to_repo` accepts an optional `author` override (see `format_author_identity`) for callers that already know who's acting from somewhere other than the OS login -- used by `webapp/` to attribute commits to the authenticated user (LDAP and/or local-OS-account, see `auth.py`). Both it and `app_data.py`'s `get_app_data_dir`/`get_git_dir`/`get_cache_dir` also accept an optional `config_path` override, so a caller reading a different `vra-config.ini` than the OS default (again, `webapp/`, or a test) gets consistent locations/git-dir/cache-dir resolution throughout -- without it, git commits and locks would silently follow the wrong config.
  - `ingest.py`: Merges newly-arrived source files into the edit folder.
  - `record_transitions.py`: The submit/approve/reject move (validate, write to the new location preserving subfolder structure, move any sibling media) -- extracted out of `DocumentController` since none of it touches Qt. `DocumentController._move_to_location` is a thin wrapper around `move_to_location()` that also tracks its own open-file state and emits signals. `webapp/`'s submit endpoint calls it directly.
  - `record_titles.py`: Best-effort record title/file-size extraction for a "browse a folder of records" UI (used by `ui/dialogs/file_picker.py` and `webapp/routes/folder_routes.py`) -- kept Qt-free and separate from that dialog module so it stays importable from a headless process.
  - `record_locks.py`: Advisory per-record locking (SQLite under `app_data.get_cache_dir()`, same pattern as `vocab_cache.py`) so two concurrent editors don't silently clobber each other -- wired into `webapp/`; the desktop app has the same unprotected-concurrent-edit gap on a shared network drive but doesn't use this yet.
  - `export/`: Crosswalks from VRA Core 4 to other metadata schemas -- one module per target (`dublin_core.py`, `lido.py`), each taking a record's own lxml element and returning that schema's XML text.
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
- `webapp/`: Flask backend for the browser companion app -- LDAP and/or local-OS-account authentication (`auth.py` -- LDAP via `ldap3`, local accounts via PAM/`python-pam` on Linux or Win32 `LogonUser`/`pywin32` on Windows; at least one must be configured, checked at startup), the JSON API (`routes/`), and `tree_json.py` (serializes `VraTreeNode` -- the same schema-driven model the desktop's Simple/Advanced views render -- to JSON, addressing nodes by position from the record root since a fresh document is loaded per request). Imports `vra_editor.core.*` directly, the same way `main.py` imports `vra_editor.ui`. Entirely additive: nothing in `vra_editor/ui/` changes or is reused here. See `requirements-web.txt` (kept separate from `requirements.txt` so PyInstaller never bundles Flask/ldap3/waitress into the desktop app).
- `tests/`: Pytest suite for `webapp/`, isolated from any real config/archive (`conftest.py`'s `test_archive` fixture builds a throwaway one per test). Needs a running LDAP server -- either `docker-compose.web-test.yml` locally (`docker compose -f docker-compose.web-test.yml up -d`, then its bootstrap script) or `VRA_TEST_LDAP_SERVER=ldap://<host>:389` pointed at another one; tests needing it skip cleanly (not a confusing connection error) if neither is reachable. Local-account-backend tests are unit-level by default (the PAM/Windows glue functions are exercised against fake `sys.modules` entries, no real OS accounts needed), with an opt-in real-account integration path behind `VRA_TEST_LOCAL_USER`/`VRA_TEST_LOCAL_PASSWORD`, skipped by default.
- `frontend/`: Vue 3 SPA for the browser companion app -- `views/` (Login, folder list, record editor), `components/TreeNode.vue` (recursively renders `webapp/tree_json.py`'s output -- the same generic, schema-driven tree the desktop renders, so a section/field appears here automatically as `vra_structure.py`'s schema-derived rules evolve, no per-element frontend code needed), `session.js` (mirrors the server's signed-cookie session state), `api.js` (fetch wrapper). `vite.config.js` proxies `/api` to Flask on `:8000` in dev, so the browser sees one origin -- no CORS setup, and it matches how the eventual reverse-proxy deployment will also look. `npm run build` outputs static assets to `frontend/dist/` for that proxy to serve.

## How to Add a New Element Form
1. Add a new editor widget in `vra_editor/ui/panels/form_panel/`.
2. Register the widget inside `FormContainerPanel` in `form_container.py`.
3. Connect signal updates to `DocumentController`.
