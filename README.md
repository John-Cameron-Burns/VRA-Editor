VRA-Editor is a comprehensive VRA Core 4 editor that allows the creation and editing of metadata files that describe collections, works and images in humanities and arts. 

Is is designed for individuals and teams who are working with VRA Core 4 metadata in a self-managed environment where the workflow is folder based.
The general idea is that the folders should be on a network drive, though local folders are also supported.
Every change is tracked and so history and rollback is straightforwardd, and everything is full validated against the strict schema.
Trip mode allows for offline editing and reconciliation of metadata files and audit trail on return.
Use of vocab references is fully integrated and supports local caching and full text searching of vocab references.



It provides
- A form-based editor of VRA XML files
- Folder based workflow for local or LAN based management, with import and reviewing into separate folders.
- ingestion and round-tripping of metadata to image files using EXIF and IPTC
- online vocab searching and injection across GeoNet ( GNS ), Getty (AAT,ULAN, &c ) and Library of Congress Controlled Vocabularies
- Local caching and full text searching of vocab references
- Audit trails and version control/rollback using a local GIT repository
- Fully configurable folders/paths for all the locations
- Supports offline use (trip mode) via settings. Stages edit folder on departure and reconciles XML files and audit trail on return

