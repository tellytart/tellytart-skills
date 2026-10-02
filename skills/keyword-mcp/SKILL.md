---
name: "keyword-mcp"
description: "Keyword the photos selected in Lightroom Classic directly through the Lightroom MCP: read them, review previews, agree changes with the user, then apply keywords and GPS using only the catalog's existing keyword hierarchy. Use for /keyword-mcp."
---

# Keyword Lightroom photos through the Lightroom MCP

`/keyword-mcp <run name>` keywords whatever the user has selected in Lightroom Classic. You
read the photos through the Lightroom Classic MCP tools, look at previews, decide keyword
changes, resolve every open question with the user (showing them the photos), get one
confirmation, then write the changes to the catalog yourself with `set_keywords` and
`set_gps`, and verify them.

The order is always: **check tools → read → review → draft → ask (with pictures) until
nothing is open → confirm → apply → verify → clean up → report**. Nothing is written to the
catalog while any question is open or before the user confirms.

Only ever change the catalog through the MCP tools. Never touch the `.lrcat` file.

## 1. Check the tools

The tools are the Lightroom Classic MCP tools (their names end in `get_selected_photos`,
`export_photo_metadata`, `export_photos`, `list_keywords`, `set_keywords`, `set_gps`). This
skill needs a build of the server that has all of them; the skill's README says where to
get one.

- Call `get_selected_photos` with `limit: 1`. If it says "Lightroom plugin not connected",
  ask the user to open File › Plug-in Manager › Lightroom MCP and press **Stop Server** then
  **Start Server** (Start alone is ignored when the plug-in wrongly thinks it is running).
  The plug-in's log is `~/Documents/LrClassicLogs/LightroomMCP.log`.
- If `list_keywords`, `export_photo_metadata` or `set_gps` is missing, or `set_keywords` has
  no `create_missing` parameter, the stock build is installed. **Stop.** Stock `set_keywords`
  creates every keyword at the top level and would scatter duplicates through a keyword
  hierarchy.

## 2. What gets keyworded

The MCP cannot list a collection's contents; it reads the **current selection, or the whole
filmstrip when nothing is selected**. So the user selects the photos, or clicks the
collection and chooses Edit › Select None, before running the skill.

- The `count` from step 1 is what will be read. If it is 1, or far from what the run name
  suggests, ask before going on: one selected photo means that one photo, not its
  collection.
- The argument is only a label for the run. With no argument, use the collection or shoot
  name the user mentions, or a dated name.

## 3. Working folder, helper and conventions

The **working folder** is a folder on the user's computer that is connected to this
session. The default is `~/Claude/lightroom-keywording/`; use another if the user says so.
Request access to it once if it isn't connected.

Everything you create goes in `<working folder>/<run name>/` (characters
`/ \ : * ? " < > |` become `_`). If the run folder already exists with a `plan.json` or
part files but no `photos-after.json`, read them and carry on rather than starting over. A
folder that has `photos-after.json` is a finished run that was never cleaned up: leave it
alone, tell the user it is there, and use a new name (add ` 2`, ` 3`…).

**`kwtool.py`** in the working folder does the mechanical work. Run it in the shell on the
user's computer, from the working folder; its docstring lists the commands:

- `prep <run>`: summarises `photos.json`, writes `export.json` (ID chunks for previews)
  and creates the preview folders (`export_photos` fails if its destination is missing).
- `sheets <run>`: contact sheets in `sheets/` and `batchNN.json` (about 80 photos a batch).
- `qsheet <run> <name> <ref>...`: a question sheet in `q/<name>.jpg`.
- `plan <run>`: validates `plan.json` and writes `calls.json`, the exact MCP calls to make.
- `verify <run>`: checks `photos-after.json` against `photos.json` plus the plan.
- `clean <run>`: after a passing verify, removes the whole run folder.

A photo ref is an ID, a file name, a file stem, or a glob on the file name; `all` is every
photo. If `kwtool.py` is missing, tell the user and stop: the README says how to install it.

**`conventions.md`** in the working folder records how this user's keyword hierarchy is
organised and how they want it used. Read it at the start of every run. It answers:

- which branches hold which kind of keyword (subjects and objects, attributes such as
  action, number and season, photographic terms such as framing and orientation, places,
  people);
- which branches you must never add from without being told (for example people, clients,
  jobs, publication or workflow keywords);
- which keywords are containers that should not be applied themselves;
- the marker keyword that records a photo as reviewed (also set as `marker` in
  `kwtool.json`, see the README);
- the user's location, for seasons, and any standing choices they have made (which term
  to use where two fit, how to treat edited copies, and so on).

If `conventions.md` does not exist, this is the first run. Before reviewing any photo:
read the whole keyword tree once with `list_keywords` and `paths_only: true` (page with
`limit: 1000`), summarise its structure back to the user, ask them the points above with
AskUserQuestion, and write `conventions.md` from their answers. When a later run settles a
new standing choice, add it to the file.

## 4. Read the inputs

1. **Metadata.** `export_photo_metadata` with `destination` =
   `<run folder>/photos.json` and no `photo_ids` (it then follows the selection). Each photo
   has `id`, `filename`, `fileFormat`, `captureTime` (ISO, local time, may be missing for
   scans), `dimensions`, `croppedDimensions`, `gps`, `location`, `title`, `caption` and
   `keywordPaths` (full paths). This file is the **before** state: never overwrite it once
   you have started applying. Never read metadata with `get_photo_metadata` photo by photo.
2. **`kwtool.py prep <run>`**, then read `export.json`.
3. **Previews.** For each chunk in `export.json`, call `export_photos` with those
   `photo_ids`, `destination` = `<run folder>/previews`, `format: jpeg`, `width: 1200`,
   `height: 1200`, `quality: 65`, `on_existing: overwrite`. Previews are named after the
   original file stem. Each photo under `clashing` shares a stem with another, so export it
   in its own call to the `destination` given for it. Videos are skipped.
4. **Vocabulary.** A hierarchy can hold thousands of keywords; never list it as full
   objects. Use `list_keywords` with `paths_only: true` and `limit: 1000`:
   - read the branches `conventions.md` names for attributes and photographic terms in
     full;
   - read the subject branch in full (page with `offset` while `has_more`), or just the
     parts of it the shoot needs;
   - for places and anything else, look up single terms with `query` (it matches names
     and synonyms and returns full objects), or list one branch with `parent`.
   Copy paths exactly as listed, including keywords that have no parent. This is the ONLY
   vocabulary you may use.
5. **Contact sheets.** `kwtool.py sheets <run>`, then view the sheets (stage at most 50
   files at a time). View an individual preview at full size wherever a detail matters:
   what someone is wearing or holding, framing, angle.

## 5. Decide the changes

For each photo compare what is visibly in the frame with its current `keywordPaths`.

**Add** keywords from the hierarchy that clearly apply, as far as the hierarchy has them:
- subjects, objects, clothing and other things in the frame;
- attributes: action, number of people or animals, age, colour, time of day, season (from
  `captureTime` and the user's location);
- photographic terms: framing, orientation (from `croppedDimensions`), angle of view,
  setting (interior, exterior, studio), type of photography, effect, treatment (colour or
  black and white);
- places: only from GPS or location metadata, or an unmistakable landmark. Use the deepest
  existing place keyword. If the GPS or an existing place keyword contradicts an
  unmistakable landmark, trust the landmark and flag it to the user (see GPS below).

**Remove** keywords that are clearly wrong for that photo: wrong framing, orientation or
angle, or objects not in the frame. When unsure, leave it and ask.

**Edited copies:** a selection often holds an original and an edited copy (a different
file type, a suffix such as "-Edit" or "-2", or a virtual copy) with the same capture time.
Keep content keywords consistent across a pair: a keyword that describes the subject on
one copy may be copied to the other. Keywords that track workflow or publication can
differ between copies on purpose; leave them.

**GPS positions.** `set_gps` always replaces whatever position the photo has. So:
1. Propose GPS only when the photo has no position, or when its position clearly
   contradicts an unmistakable landmark in the frame.
2. Take the position from the landmark itself, or from the other copy of the same shot,
   never from a guess about the general area.
3. List every proposed position as old → new with the reason, and ask before including any
   that are uncertain.
4. Never propose GPS just to make an existing, roughly-right position more precise.

**Don't:**
- Identify people from their faces. Keywords naming a person come only from existing
  keywords (including the other copy of the same shot), the title, caption or file name, or
  what the user tells you. Keep existing ones.
- Add from any branch `conventions.md` reserves, unless the user says so; do ask when the
  context suggests one (the run name, a folder name, a title).
- Put the marker keyword in the plan. `kwtool.py plan` adds the call that marks every
  reviewed photo.
- Add container keywords that only group others; add the keywords beneath them.
- Use a keyword whose meaning doesn't fit just because the word matches.
- Invent keywords. If something clearly needs a keyword that doesn't exist, propose it as a
  question with a suggested full path; it goes in `newKeywords` ONLY after the user agrees.
- Add something you can't make out clearly at preview size; ask instead.

Always write a keyword as its full path, exactly as `list_keywords` shows it. Leaf names
repeat: `portrait` can be both an orientation and a type of photograph.

Keyword whatever is in the library plainly and neutrally, with the user's existing terms.

While deciding, keep two things apart:
- **Draft changes** you're sure of: these go in `plan.json` (section 7 has the format).
- **Open questions**: anything unclear: a new keyword, a person's name, a reserved-branch
  keyword, uncertain GPS or dates, details you can't be sure of at preview size, a
  convention choice (e.g. night vs evening), a suspected duplicate or reject. Record each
  one with the photos it concerns and the options you'd offer.

## 6. Ask with pictures until nothing is open

Every open question is put to the user with **AskUserQuestion**, and they see the photos
it's about before they answer. Don't bury questions in prose or leave them in a file.

For each round:
1. Build a question sheet per question (or closely related group) with
   `kwtool.py qsheet <run> <name> <refs>` (e.g. name `q03a_hat`). For a long run of
   near-identical frames, show a representative sample plus the edge cases and say so.
2. Send the sheets to the user in one go, rendered so they can see them, with a caption
   that names each sheet by letter and what to look at, e.g. "(a) 043/044 the hat,
   (b) 019–022 the sign". Label the matching questions with the same letters.
3. Call **AskUserQuestion** with up to 4 questions. Each names the photos (filenames or
   range) and the sheet letter; options are concrete keyword outcomes, with the full path in
   the option description when it matters. Use `multiSelect` when several independent
   yes/no items share one topic. Put a new keyword's proposed full path in the option so
   agreeing to it is explicit.
4. Read each answer literally. A skipped question means no change for that item. A typed
   answer can introduce facts (a place name, a correction); act on it, and if it implies a
   new keyword the user hasn't explicitly agreed, confirm that in the next round.
5. Record every decision straight away by updating `plan.json`, and keep a short
   `decisions.md` in the run folder (question, answer, what changed) so a dropped session
   can resume and declined items stay declined.

Keep going round by round until **no question is left open**. If an answer raises a new
question, ask it in the next round with its own sheet.

If AskUserQuestion isn't available (an unattended or scheduled run), still build and send
the question sheets, list the numbered questions in the reply, and stop there. Apply
nothing. If the user answers numbered questions in a message, make sure you know exactly
which list the numbers refer to; if you can't map them with certainty, ask.

## 7. Plan, confirm, apply

**plan.json** in the run folder:

```json
{ "reviewed": "all",
  "newKeywords": ["Places|Europe|France|Strasbourg"],
  "changes": [
    { "photos": "all",
      "add": ["Photography|Setting|exterior"] },
    { "photos": ["IMG_18*.dng", 12345],
      "add": ["Photography|Framing|full body"],
      "remove": ["Photography|Framing|headshot"],
      "gps": { "latitude": 48.5818, "longitude": 7.7509 } } ] }
```

`reviewed` is the photos you actually looked at (`"all"`, or a list of refs); they get the
marker keyword whether or not they changed. `newKeywords` holds only full paths the user
agreed to, each used on at least one photo.

**Build the calls.** Run `kwtool.py plan <run>`. It refuses a plan with a keyword both
added and removed, a bad position or an unused new keyword; it drops no-op adds and
removes; and it writes `calls.json`. Fix anything it rejects.

**Pre-flight, read-only.**
- Every path under "distinct keywords to add" must be one you saw in a `list_keywords`
  result this run. For any you didn't, call `list_keywords` with `parent: <path>` and
  `limit: 0`: it errors with "Keyword not found" when the keyword doesn't exist.
- For each new keyword, check its **parent** path the same way, so a typo can't grow a
  stray branch. New keywords are created with include-on-export on and no synonyms; say so.
- Check the marker keyword exists, using `query` with its name. If it doesn't, ask the
  user to create it in Lightroom. Don't create it yourself.

**Confirm once.** Show the summary (photos reviewed, photos changing, adds, removes, GPS
changes old → new, new keywords to be created) and ask with AskUserQuestion whether to
apply. Without a clear yes, apply nothing.

**Apply.** Make the calls in `calls.json` in order, one at a time, with the arguments
exactly as written. Never retype ID lists from memory; read them from the file.
- Calls marked "create agreed new keyword" are the only ones with `create_missing: true`.
  Every other `set_keywords` call has `create_missing: false`, so an unknown or ambiguous
  keyword fails that call before it writes anything.
- If a call fails, stop, read the error, and fix the cause (usually a path that doesn't
  exist). Earlier calls stay applied; re-running a call is harmless.
- If Lightroom stops answering mid-way, don't guess: go to verification to see what landed.

## 8. Verify before saying it's done

1. `export_photo_metadata` again, to `<run folder>/photos-after.json`, passing the
   `photo_ids` from `photos.json` (not the selection, which the user may have changed; at
   most 1000 IDs per call, so for more, export in parts and merge them in the shell).
2. `kwtool.py verify <run>`. It checks every photo's keyword paths equal the before state
   plus the agreed adds, minus the agreed removes, plus the marker, that agreed positions
   are set, and that no other position changed.
3. Only when it prints `VERIFY OK` say the keywords are applied. If it fails, report
   exactly which photos differ and why, and fix or ask.

If the user later changes their mind or adds something, treat it as a new run under a new
name, read from the current state: export, plan, confirm, apply and verify again.

## 9. Clean up the run folder

Do this only after `VERIFY OK`, and before the report. A run that failed, was not applied,
or still has open questions keeps all its files so it can be resumed.

1. Take what the report needs from the run folder first (the per-photo changes from
   `plan.json`, any GPS old → new values, the decisions), because the folder is about to go.
2. If deleting files in the working folder needs the user's permission, ask for it once
   per session, giving the reason (removing this run's temporary files).
3. Run `kwtool.py clean <run>`. It re-checks that `photos-after.json` matches the plan and
   refuses otherwise. It then deletes the whole run folder: previews, contact and question
   sheets, and the plan, decisions, before and after files.
4. If permission was declined or deleting isn't possible, still run `clean`: it moves the
   whole run folder to `<working folder>/_to_delete/` instead, and says so. Tell the user
   it is there for them to bin. Don't ask for permission again in the same session.
5. Never delete anything outside this run's folder, and never another run's folder: one
   that is not yours may be in use by another session. Never delete `conventions.md`,
   `kwtool.py` or `kwtool.json`.

## 10. Report back

Only after verification has passed:
- One line of collection-wide changes (e.g. "exterior added to all 16").
- A table: photo (short filename; pair edited and original copies on one row) | add |
  remove/fix, leaf names only, with the parent when ambiguous. For large runs give totals
  and a per-shoot summary instead.
- GPS changes as old → new with the reason.
- New keywords that were created.
- Anything the user has to do by hand in Lightroom (rejects, moving files or keywords,
  synonyms or export settings on new keywords).
- How to undo: each call is one "Set Keywords" or "Set GPS" step in Edit › Undo. The run
  folder is deleted, so there is no saved before state beyond Lightroom's undo history.
- What clean-up did: the run folder was deleted, or moved to `_to_delete/` if deleting
  wasn't allowed.

## Large selections (more than ~50 photos)

The same rules apply; only the mechanics change.

- `kwtool.py sheets` already splits the photos into batches of about 80, keeping a capture
  date together where it fits, and writes `batchNN.json` with each batch's IDs. Keep an
  original and its edited copy in the same batch when you can.
- Work batch by batch and save as you go: for each batch write `plan.partNN.json` (same
  format as `plan.json`, refs limited to that batch) and `questions.partNN.md`, straight
  into the run folder. On resume, skip batches that already have a part file.
- For very large runs (roughly 400+ photos), hand batches to parallel subagents, three or
  four at a time: give each one section 5's rules, `conventions.md`, the vocabulary paths
  you listed, its batch's entries from `photos.json` and its sheets, and have it return the
  part file and its questions. Subagents never call `set_keywords` or `set_gps`, and never
  put questions to the user; you do both.
- When every batch is done, merge the part files' `changes` into one `plan.json`, give the
  user a short overview (totals and a one-line per-shoot summary), then go through the
  questions part by part with section 6 until none is open.
- Then section 7 onwards as normal. `calls.json` groups photos that share a change, so the
  number of calls follows the number of distinct changes, not the number of photos.
