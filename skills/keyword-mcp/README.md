# keyword-mcp

Keywords the photos you have selected in Adobe Lightroom Classic, working directly through
a Lightroom MCP server. Claude reads the selection, looks at small previews, proposes
keyword changes using **only the keywords that already exist in your catalog**, asks you
about anything unclear (showing you the photos), gets one confirmation, writes the changes
to the catalog, and then checks that the catalog matches what was agreed.

It can also set GPS positions, create a new keyword when you explicitly agree to one, and
mark every photo it reviewed with a control keyword so a smart collection can find photos
not yet done.

- [`SKILL.md`](SKILL.md): the instructions Claude follows.
- [`scripts/kwtool.py`](scripts/kwtool.py): helper script for contact sheets, plan
  validation, working out the calls to make, verification and clean-up.

## Status

This is a generalised version of a skill I use on my own catalog. My own copy has my
keyword hierarchy written into it and has been used on real photos; this version asks you
for your conventions instead (see "First run" below), and **that first-run path has not
been tested end to end**. The helper script is the same one I use.

## Prerequisites

### 1. Lightroom Classic and a keyword hierarchy

Adobe Lightroom Classic, with a catalog whose keywords you want Claude to choose from. The
skill was developed and used on macOS. Back up the catalog before the first run.

### 2. A patched Lightroom MCP server

The skill talks to Lightroom through
[Automaat/lightroom-mcp](https://github.com/Automaat/lightroom-mcp), an MCP server with a
Lua plug-in that runs inside Lightroom Classic.

**The stock server is not enough, and must not be used with this skill.** Its
`set_keywords` tool creates every keyword at the top level, so in a catalog with a keyword
hierarchy it would create duplicates beside your nested keywords. The skill checks for this
and stops.

The skill needs three additions to that server. They are being proposed upstream from the
fork [tellytart/lightroom-mcp](https://github.com/tellytart/lightroom-mcp):

| Addition | Branch on the fork | Status |
|---|---|---|
| `set_keywords` accepts `Parent|Child` paths and `create_missing: false`; `get_photo_metadata` returns `keywordPaths`; new `list_keywords` tool | `hierarchical-keywords` | Pull request open upstream |
| New `set_gps` tool | `set-gps` | Pull request open upstream |
| New `export_photo_metadata` tool | not published yet | Waiting for the first pull request to be merged |

**Until the third addition is published, the skill cannot be installed from public
sources.** This README will be updated when it is. Once all three are merged and released
upstream, the stock server will do.

To install the patched build:

1. Install [Node.js](https://nodejs.org) 18 or later.
2. Get a copy of the server source that has all three additions, then build the bundle
   from its root:
   ```
   node scripts/build-mcpb.mjs
   ```
   This writes `build/lightroom-mcp.mcpb`.
3. Install the server: open the `.mcpb` file with the Claude desktop app and choose
   Install. If you already have the stock Lightroom Classic extension, remove it first.
4. Install the plug-in. With Lightroom closed, copy `plugin/LightroomMCP.lrplugin` into
   Lightroom's Modules folder, replacing any copy already there (the server only installs
   the plug-in when none is present, so it will not replace a stock one for you):
   - macOS: `~/Library/Application Support/Adobe/Lightroom/Modules/`
   - Windows: `%APPDATA%\Adobe\Lightroom\Modules\`
5. Open Lightroom, go to File > Plug-in Manager > Lightroom MCP and press **Start Server**.
   Tick **Auto-start server on Lightroom launch** to skip this step in future.

If Claude reports "Lightroom plugin not connected" while the plug-in says it is running,
press **Stop Server** and then **Start Server**. The plug-in's log is at
`~/Documents/LrClassicLogs/LightroomMCP.log`.

### 3. Claude with access to your computer

The skill needs a Claude session that can:

- call the Lightroom MCP server's tools;
- run shell commands on your computer and read and write a folder there (the skill's
  working folder, `~/Claude/lightroom-keywording` by default, which must be connected to
  the session);
- show you images and ask you multiple-choice questions.

It was written for the Claude desktop app with the session linked to the Mac running
Lightroom. In an unattended run, where questions cannot be asked, the skill sends its
questions and stops without changing the catalog.

### 4. Python 3 and Pillow

`kwtool.py` needs Python 3.8 or later and the [Pillow](https://python-pillow.org) imaging
library, in whichever shell Claude uses to run it. Everything else it uses is in the
standard library.

```
python3 -c "import PIL; print(PIL.__version__)"    # check
python3 -m pip install Pillow                      # install if missing
```

### 5. The helper script and its settings

Copy `scripts/kwtool.py` into the working folder:

```
mkdir -p ~/Claude/lightroom-keywording
cp scripts/kwtool.py ~/Claude/lightroom-keywording/
```

Create the **marker keyword** in Lightroom: the keyword the skill adds to every photo it
has reviewed, so that a smart collection with "Keywords doesn't contain" can find the
photos still to do. Then tell the script its full path by creating
`~/Claude/lightroom-keywording/kwtool.json`:

```json
{ "marker": "Control|Claude Keyworded", "require_nested": false }
```

- `marker` is the keyword's full path, parent first, with `|` between levels. Without this
  file the script uses a top-level keyword called `Claude Keyworded`.
- `require_nested`, when `true`, makes the script refuse any keyword written without a
  parent. Turn it on if every keyword in your catalog sits inside a group.

### 6. The skill installed in Claude

Add `SKILL.md` to Claude as a skill named `keyword-mcp`.

## First run

The skill keeps a file called `conventions.md` in the working folder describing how your
keyword hierarchy is organised: which branches hold subjects, attributes, photographic
terms, places and people, which branches it must not add from without asking, which
keywords are only containers, and where you are for working out seasons.

On the first run that file does not exist, so the skill reads your keyword tree, shows you
what it found, asks you those questions and writes the file. You can also write or edit
`conventions.md` yourself; it is plain text for Claude to read.

## Using it

1. In Lightroom, select the photos to keyword. With nothing selected, the whole filmstrip
   is used; with one photo selected, only that photo is.
2. In Claude, run `/keyword-mcp` followed by a name for the run, for example
   `/keyword-mcp Lisbon trip`.
3. Answer the questions. Nothing is written to the catalog until you confirm the summary.

## What it does to your catalog and your disk

- It changes the catalog only through the MCP tools: keywords added and removed, GPS
  positions set where agreed, new keywords created only when you agreed to each one.
- Every write except creating an agreed new keyword uses `create_missing: false`, so an
  unknown or ambiguous keyword makes the call fail before anything is written.
- Each call is one step in Lightroom's Edit > Undo history.
- Working files (previews, contact sheets, the plan) go in a folder per run inside the
  working folder. After a run is applied and verified, that folder is deleted. Claude asks
  for permission to delete; if you decline, the folder is moved to `_to_delete/` in the
  working folder instead. A run that fails or is not applied keeps its folder so it can
  be resumed.
- Because the run folder is deleted, there is no saved copy of the photos' previous
  keywords. Undoing a run relies on Lightroom's undo history, or on a catalog backup.

## Limits

- The MCP cannot list the contents of a collection, so the skill works on the current
  selection or filmstrip.
- Previews are named after the original file, so two selected photos with the same file
  name stem are exported separately.
- Not yet exercised: selections of more than 1,000 photos, and the parallel route for
  very large runs described at the end of `SKILL.md`.

## `kwtool.py` commands

Run from the working folder; `<run>` is the run folder's name.

| Command | What it does |
|---|---|
| `prep <run>` | Summarises `photos.json`, writes `export.json` with ID chunks for the preview export, and creates the preview folders. |
| `sheets <run>` | Builds contact sheets in `sheets/` and `batchNN.json` files of about 80 photos each. |
| `qsheet <run> <name> <ref>...` | Builds a question sheet of the photos matching the refs. |
| `plan <run>` | Validates `plan.json` and writes `calls.json`, the exact MCP calls to make. |
| `verify <run>` | Checks `photos-after.json` against `photos.json` plus the plan. |
| `clean <run>` | After a passing verify, deletes the run folder. |

A photo ref is a numeric ID, a file name, a file stem, or a glob on the file name; `all`
means every photo.
