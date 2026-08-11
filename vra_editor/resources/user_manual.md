# VRA Core 4 XML Editor — User Manual

This guide covers day-to-day use of the editor: opening and creating
records, filling them in, linking media files, and moving records
through review. It describes the app as it actually behaves — if
something here doesn't match what you see on screen, that's worth
reporting.

## Contents

- Getting started
- The toolbar
- Editing a record (Simple view)
- Controlled vocabularies and authority search
- Linking a media file
- Review Notes
- Undo
- Saving, submitting, and reviewing
- The Advanced view
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

**Home** returns you to this starting screen from anywhere.

## The toolbar

The buttons across the top are grouped into four clusters, separated
by thin vertical dividers:

1. **Navigation** — Home, Open, Create, Review, Import. Always
   available.
2. **Record actions** — Save, Undo, Submit/Approve, Reject, Cancel.
   Only shown once a record is open; act on that record specifically.
3. **View toggles** — Show XML, Review Notes, Advanced View. Switch
   how the current record is displayed; don't change its content.
4. **Admin** — Settings, Help, About. Rarely-needed, styled smaller
   and muted so they don't compete for attention.

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
automatically.

## Linking a media file

Only relevant to **image** records. Open the **Related Works**
(Relations) section — a **+ Link Media File** button appears there.

Clicking it:

1. Opens a standard file picker, starting in the *ingest* folder if
   one's configured, but not restricted to it — you can pick any
   image file anywhere on disk.
2. Asks for a filename to save it under in the *media* folder
   (pre-filled with the original name — change it if you want to
   rename the file as it comes in). If that name's already taken,
   you'll be asked to pick a different one rather than silently
   overwriting anything.
3. **Copies** the file into *media* (your original is left exactly
   where it was) and automatically fills in:
   - **Measurements** — pixel width/height and resolution (DPI),
     always.
   - **Location** and **Date** — only if the file's own EXIF data
     actually has a GPS position and/or a capture timestamp.
   - A **Related Works** entry recording which file this record is
     linked to.

All of this lands as a single Undo step — one Ctrl+Z reverts the
whole thing.

Once a file is linked, a preview band appears at the top of the form,
with three buttons:

- **Inject** — writes this record's Title, Description, People,
  Rights, Subjects, creation Date, and record ID into the file's own
  IPTC metadata, so the file stays useful outside this app too (for
  instance if it's later handled separately from the XML record).
  This modifies the actual file on disk, so you'll be asked to
  confirm first.
- **Extract** — re-reads the linked file's dimensions/GPS/date and
  refreshes Measurements/Location/Date from it. Useful if the linked
  file was swapped out after it was first linked.
- **Thumbnail** — collapses the preview to a small floating thumbnail
  in the corner, if you want the vertical space back. Click the
  thumbnail to bring the full preview back.

## Review Notes

A place for a reviewer to leave notes for the editor (or vice versa)
without it being part of the actual cataloguing data — notes are
stored separately from the record's own fields. Toggle the panel with
**Review Notes**; it opens automatically when you load a record that
has unresolved notes on it, so they're hard to miss. Each note can be
marked resolved or removed.

## Undo

**Undo** (or Ctrl+Z) reverts the last change — a field edit, an add,
a remove, a media link, anything. It's a full document snapshot each
time, not a per-character history, so a burst of typing into the same
field collapses into a single undo step; adding or removing something
always gets its own step.

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
  having to fix it themselves first.
- **Cancel** discards any unsaved changes (after confirming, if
  there are any) and returns to the start screen — the same as Home.

After Save, Submit, Approve, or Reject, you'll be asked for a short
commit comment; if you give one, the change is recorded in the
archive's shared version history under your name. Leaving it blank
just skips that step — the save/submit itself has already happened
either way.

## The Advanced view

Toggle **Advanced View** to switch from the sectioned form to a raw
structure tree (left) and a single-element editor (right). This
exposes every field the schema allows, including ones the Simple
view's section list doesn't surface directly, and is useful for
unusual or highly detailed records. **Show XML** works in either
view, and highlights whichever element is currently selected.

## Settings

Configures the folders the app reads from and writes to (edit,
ingest, media, pending, rejected, reviewed), plus where the app
stores its own local data (vocabulary cache, etc.) and your display
name. Changes take effect the next time a folder is used — for
instance, the next time you click Open.

## Tips and troubleshooting

- **"No 'X' folder is configured"** — open Settings and set that
  folder before trying the action again.
- **Submit refuses with a validation error** — the message explains
  what the schema requires; the detailed technical error is available
  too if you need it.
- **A TIFF won't preview** — some TIFF compression variants can't be
  decoded by every image library; if a linked file's preview fails,
  the record and the link are still fine, only the on-screen preview
  is affected.
- Undo is your safety net for anything done inside the app. It does
  **not** cover Inject (which writes to the linked file itself,
  outside the XML record) — that action asks for confirmation
  precisely because it isn't undoable from within the app.
