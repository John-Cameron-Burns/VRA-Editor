# VRA Core 4 Editor Architecture

This application strictly separates domain logic from user interface elements to ensure easy long-term maintenance.

## Folder Overview

- `main.py`: Entry point for the application.
- `vra_editor/core/`: **Pure Python logic.** Handles XML parsing (via lxml), dataclasses, and XSD schema validation. Contains zero PySide6/Qt code.
- `vra_editor/controllers/`: Application state management, document workflows, and event handling.
- `vra_editor/ui/`: PySide6 graphical components.
  - `main_window.py`: Layout assembly container using QSplitter.
  - `panels/tree_panel/`: Hierarchy navigation tree.
  - `panels/form_panel/`: Individual modular forms for editing specific VRA tags.
  - `panels/xml_preview/`: Syntax/raw text preview.
- `vra_editor/resources/`: Stylesheets and static assets.

## How to Add a New Element Form
1. Add a new editor widget in `vra_editor/ui/panels/form_panel/`.
2. Register the widget inside `FormContainerPanel` in `form_container.py`.
3. Connect signal updates to `DocumentController`.
