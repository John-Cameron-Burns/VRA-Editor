# VRA Core 4 XML Editor — User Manual

This guide covers day-to-day use of the editor: opening and creating
records, filling them in, syncing them with linked image files, and
moving records through review, offline or on. It describes the app as
it actually behaves — if something here doesn't match what you see on
screen, that's worth reporting.

## Contents

- Getting started
- The toolbar
- Editing a record (Simple view)
- Controlled vocabularies and authority search
- Syncing with a linked image file
- Review Notes
- Undo
- Saving, submitting, and reviewing
- The Advanced view
- Audits: browsing and restoring history
- Working offline
- Installing the web companion
- Settings
- Tips and troubleshooting

---

## Getting started

When the app opens with no record loaded, the toolbar offers four
starting points:

- **Create** — start a brand-new, blank record. You'll be asked for
  a record type (work, image, or collection) and a record ID. The
  record isn't written to disk until you Save or Submit it.
- **Open** — pick an existing record from the *edit* folder to work
  on.
- **Review** — pick a record waiting in the *pending* folder (one
  that's already been submitted) to approve or reject.
- **Import** — merge newly-arrived source files from the *ingest*
  folder into *edit*, so they show up in Open's list.

This home screen also shows a diagram of the whole record lifecycle —
Ingest, Edit, Pending, Reviewed, Released — labelled with the exact
button that moves a record from one to the next, and a reminder that
Settings is where those folders themselves get configured. Worth a
glance if you're new to the workflow.

**Home** returns you to this starting screen from anywhere.

## The toolbar

The buttons across the top are grouped into four clusters, separated
by thin vertical dividers:

1. **Navigation** — Home, Open, Create, Review, Import. Always
   available.
2. **Record actions** — Save, Undo, Submit/Approve, Reject, Cancel.
   Only shown once a record is open; act on that record specifically.
3. **View toggles** — Show XML, Review Notes, Advanced View, Sync
   Media. Switch how the current record is displayed, or open a tool
   for it; none of them change its content on their own.
4. **Admin** — Settings, Audits, Help, About. Rarely-needed, styled
   smaller and muted so they don't compete for attention.

A colored strip just below the toolbar (**Editing — filename** or
**Reviewing — filename**) shows which record you have open and
whether you're editing it or reviewing it — the two have real
differences in what the action buttons do, so it's worth a glance
before clicking Submit or Approve.

If you try to navigate away (Home, Open, Create, or Review) while a
record has unsaved changes, you'll be asked whether to save, discard,
or stay put — nothing is silently lost.

## Editing a record (Simple view)

This is the default view, and the one most cataloguing work happens
in. It has two panes:

- **Left — Sections.** One row per part of the record (Titles,
  People, Dates, Measurements, and so on). Bold rows already have
  content, with a count in parentheses; grey italic rows (**+ Add
  …**) are sections this record doesn't have yet — click one to add
  it.
- **Right — the form** for whichever section is selected. Each
  existing entry is shown as its own card, with **+ Add** buttons at
  the bottom for adding another. Every card and every section can be
  removed individually (**Remove this …**); removing is always
  undoable.

Fields with a fixed vocabulary (relation type, material type, and
about a dozen others defined by the VRA Core 4 schema) show as a
dropdown instead of free text — the options offered are exactly the
ones the schema allows, so there's no risk of typing an invalid value.
Some sections (People, Dates, Locations, Materials, Rights, ...) also
have their own **Type:** dropdown at the top of the card, for the
same reason.

**Display translations** — most sections can carry a short,
language-tagged summary alongside (or instead of) the itemized detail
underneath. Use **+ Add translations (Display)** to add one.

## Controlled vocabularies and authority search

Fields that reference a named authority (an artist's name, a place,
a subject term, a material) have a **Search authority…** button next
to them. It searches the relevant vocabulary — VIAF, Getty AAT/TGN/
ULAN, GNS, or the Library of Congress vocabularies (LCSH, LCNAF,
LCGFT, LCTGM), depending on the field — and, once you pick a result,
fills in the linked-authority details (record ID and link) for you
automatically. Results are cached locally, so a repeated or related
search doesn't need the network again.

## Syncing with a linked image file

Only relevant to **image** records, and only shown once one is open.
Click **Sync Media** to open it. There's no persisted link remembered
between sessions — the app makes a best guess from the filename each
time, or you're asked to browse to the right file yourself.

It compares seven of the record's own fields — Title, Description,
Rights, People, Subjects, creation Date, and Location — against
whatever the image file's own EXIF/IPTC metadata already says, and
shows each as one of:

- **In sync** — the record and the file already agree; nothing to do.
- **Fill record** — the file has it, the record doesn't; can be
  copied in.
- **Fill file** — the record has it, the file doesn't; can be copied
  out to the file's metadata.
- **Conflict** — the two disagree; pick which one wins.

Pixel dimensions, resolution, and file size are always shown too,
read fresh from the file, purely for information — there's nothing to
choose there. Tick or choose which direction each row should go, then
**Sync** applies your choices — this is the only step here that
writes to the image file itself.

There's also an optional checkbox to copy the image to sit alongside
the record's own XML file (renamed to match the record's ID) as part
of the same sync — useful the first time you link a file that's
sitting somewhere else, so the two stay together going forward.

## Review Notes

A place for a reviewer to leave notes for the editor (or vice versa)
without it being part of the actual cataloguing data — notes are
stored separately from the record's own fields. Toggle the panel with
**Review Notes**; it opens automatically when you load a record that
has unresolved notes on it, so they're hard to miss. Each note can be
marked resolved or removed.

## Undo

**Undo** (or Ctrl+Z) reverts the last change — a field edit, an add,
a remove, anything done inside the sectioned form or the tree editor.
It's a full document snapshot each time, not a per-character history,
so a burst of typing into the same field collapses into a single undo
step; adding or removing something always gets its own step. It does
**not** cover Sync Media's file-writing step (see Tips below).

## Saving, submitting, and reviewing

- **Save** writes the record to the *edit* folder as-is. The record
  doesn't need to be complete or fully valid to save your progress.
- **Submit** moves the record from *edit* into *pending*, for
  review. Unlike Save, this **does** require the record to be
  schema-valid — if it isn't, you'll see an explanation of what's
  wrong rather than the submission going through.
- **Approve** (while reviewing a pending record) moves it into
  *reviewed* — the final archive location.
- **Reject** (while reviewing) sends it into *rejected*, for the
  original editor to revisit. Approve and Reject don't re-validate —
  a reviewer needs to be able to reject something broken without
  having to fix it themselves first. A rejected record shows up right
  alongside your other editable records when you click **Open** (or,
  in the web app, on the Edit folder page) — no separate step is
  needed to bring it back into editing.
- **Cancel** discards any unsaved changes (after confirming, if
  there are any) and returns to the start screen — the same as Home.

After Save, Submit, Approve, or Reject, you'll be asked for a short
commit comment; if you give one, the change is recorded in the
archive's shared version history under your name — see **Audits**
below for browsing and restoring from that history. Leaving the
comment blank just skips that step; the save/submit itself has
already happened either way.

## The Advanced view

Toggle **Advanced View** to switch from the sectioned form to a raw
structure tree (left) and a single-element editor (right). This
exposes every field the schema allows, including ones the Simple
view's section list doesn't surface directly, and is useful for
unusual or highly detailed records. **Show XML** works in either
view, and highlights whichever element is currently selected.

## Audits: browsing and restoring history

Click **Audits** (always available, in the Admin cluster) to see
every past revision recorded via the commit-comment prompt above —
one row per file changed in a commit, most recent first, with who
made it and when. Type in the filter box to narrow it down by
filename.

Select a revision and click **Restore to New File...** (or just
double-click the row) to write that exact past version into a new
file in the *edit* folder, under whatever name you choose — this
never overwrites anything, and the new file is opened for you
afterward, going through the same unsaved-work check as Open or
Create.

## Working offline

For working somewhere with no network at all — a field trip, a site
visit, anywhere without a signal. This only ever involves the *edit*
folder: the records actively being worked on, typically a modest,
everyday-sized amount — not the reviewed/approved archive behind it,
which is never touched and can be far larger.

**Before you go** — open **Settings**, and under **Offline Work**
click **Start Offline Staging...**. Choose a local folder; the app
copies the current *edit* folder into it and points Edit there.
Click **Save** to actually switch over.

**While you're away** — use the app exactly as normal: Open, Create,
Save all work against your local copy. Hold off on **Submit** until
you're back online — *pending* still points at the real, currently
unreachable archive, so a Submit attempt while offline will simply
tell you it can't reach that folder rather than going through.

**When you're back** — open **Settings** again and click **Reconcile
Offline Changes...**. This lists every record that actually needs
attention — new ones you created, ones you edited — and applies the
straightforward ones for you in one go. If a record was *also*
changed on the primary archive while you were away, it's flagged as a
conflict instead of being guessed at: you choose whether to keep your
offline edit, keep what's on primary, or leave it for later. Once
you're done, it offers to point Edit back at the primary folder.

## Installing the web companion

*This is a one-time, occasional-admin task — most users of this app
never need to touch it.*

Settings' **Web Server** tab can set up a browser-based companion to
this app, so people can review, edit, import, and export records from
a web browser, signed in with either an LDAP directory account or a
local account on whichever machine hosts it. Clicking **Install as
Web Server...** opens a dialog to choose the target machine's
operating system, where it installs to, which port it listens on, a
reverse proxy in front of it (or none), and which login method(s) to
allow.

**Generate Install Script...** doesn't install anything itself — it
writes a single script file for you to review and then run yourself,
on whichever machine should actually host it (which doesn't have to
be this one). Read it before running it, same as you would any script
from anywhere — it makes real, system-level changes: installing a
background service and, if you chose one, a reverse-proxy site.

### Running the generated script

**Linux:** copy the `.sh` file to the target machine and run:

    sudo bash install-vra-web.sh

**Windows:** copy the `.ps1` file to the target machine, then open an
**elevated** PowerShell prompt — click **Start**, type "PowerShell",
right-click **Windows PowerShell**, and choose **Run as
administrator**. `cd` to wherever you saved the script, then run it
with this exact command (not just the filename by itself):

    powershell -ExecutionPolicy Bypass -File .\install-vra-web.ps1

If you instead just type the script's name and see *"running scripts
is disabled on this system"* — that's expected, and it's not about
whether you're an administrator. Windows blocks `.ps1` script files
from running at all by default, for anyone, admin or not; "Run as
administrator" is a completely separate permission from whether
PowerShell allows a script to run in the first place. The
`-ExecutionPolicy Bypass` above skips that check for this one run
only — it doesn't change any permanent setting on the machine, so
you'll type the command the same way each time you run a script like
this.

## Settings

Four tabs:

- **Locations** — the *Clutter folder* first, then the folders the
  app reads from and writes to: Edit, Ingest, Pending, Rejected,
  Reviewed, and Released. The first five of those are moved between
  automatically by Import/Submit/Approve/Reject; *Released* has no
  button of its own anywhere in the app — it's wherever you archive a
  reviewed record off to by hand once it's actually ready to publish.
  *Clutter folder* is where the app keeps its own files (the shared
  version history behind Audits, and the vocabulary-search cache)
  separate from the archive itself — leave it blank to use the
  sensible default shown. Pointing it at (or inside) an existing
  archive's own folder automatically fills in whichever of the
  folders above are still blank and found nearby, as siblings or as
  children of it.
- **Offline Work** — see **Working offline** above.
- **User & Options** — your full name (used to label your own Saves/
  Submits/Approvals in Audits), plus a handful of less-common
  preferences, most usefully **media_extensions**: which file
  extensions count as a record's linked media file for Sync Media and
  for Submit/Approve/Reject carrying it along. Leave blank for a
  broad, sensible default (shown as a placeholder in the field
  itself).
- **Web Server** — see **Installing the web companion** above.

Changes take effect the next time a folder is used — for instance,
the next time you click Open.

## Tips and troubleshooting

- **"No 'X' folder is configured"** — open Settings and set that
  folder before trying the action again.
- **"Couldn't reach that folder"** — Save/Submit/Approve/Reject
  couldn't actually write to the configured location (a network
  share that's gone offline is the usual cause). Nothing is lost —
  your edits are still in the open record — but that particular save
  didn't happen. If this is a recurring problem rather than a one-off
  outage, see **Working offline** above.
- **Submit refuses with a validation error** — the message explains
  what the schema requires; the detailed technical error is available
  too if you need it.
- Undo is your safety net for anything done inside the app. It does
  **not** cover Sync Media's actual file-writing step (it modifies
  the linked image's metadata directly, outside the XML record) —
  that's why Sync asks for confirmation before it runs.
