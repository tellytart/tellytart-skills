#!/usr/bin/env python3
"""kwtool: helper for the keyword-mcp skill (Lightroom Classic keywording over MCP).

Lives in the skill's working folder. Every command takes a run folder
(<working folder>/<run name>/) that holds:

  photos.json         written by the MCP tool export_photo_metadata (state BEFORE)
  previews/           JPEGs written by the MCP tool export_photos
  previews/dup/<id>/  previews of photos whose file stem clashes with another
  plan.json           the agreed changes (you write this)
  calls.json          written by `plan`: the exact MCP calls to make
  photos-after.json   export_photo_metadata again after applying
  sheets/, q/         contact sheets and question sheets

Commands:
  prep   <run>                      summarise photos.json, write export chunks
  sheets <run> [--per 8] [--batch 80]   contact sheets + batchNN.json
  qsheet <run> <name> <ref>...      question sheet of the photos matching refs
  plan   <run>                      validate plan.json, write calls.json
  verify <run>                      compare photos-after.json with the plan
  clean  <run>                      after a passing verify: remove the whole run folder

A photo ref is a numeric id, a full file name, a file stem, or a glob on the
file name (e.g. "IMG_18*"). "all" means every photo.

Optional settings go in kwtool.json beside this script:
  { "marker": "Control|Claude Keyworded",   keyword added to every reviewed photo
    "require_nested": false }               true = refuse keywords written without a parent
"""
import fnmatch
import json
import math
import os
import sys

DEFAULT_MARKER = "Claude Keyworded"


def load_config():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kwtool.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError) as e:
        print(f"ERROR: could not read {path}: {e}")
        sys.exit(1)
    if not isinstance(cfg, dict):
        print(f"ERROR: {path} must hold a JSON object")
        sys.exit(1)
    return cfg


CONFIG = load_config()
MARKER = CONFIG.get("marker") or DEFAULT_MARKER
REQUIRE_NESTED = bool(CONFIG.get("require_nested", False))
CHUNK = 100          # photos per export_photos call
MAX_IDS = 1000       # MCP limit per call


def die(msg):
    print("ERROR: " + msg)
    sys.exit(1)


def load_photos(run, name="photos.json"):
    path = os.path.join(run, name)
    if not os.path.exists(path):
        die(f"{path} not found - run export_photo_metadata first")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    photos = data.get("photos") or []
    if isinstance(photos, dict):   # an empty Lua table can arrive as {}
        photos = []
    for p in photos:
        for key in ("keywords", "keywordPaths"):
            if not isinstance(p.get(key), list):
                p[key] = []
        p["stem"] = os.path.splitext(p.get("filename") or "")[0]
    return photos


def is_video(p):
    return (p.get("fileFormat") or "").upper() == "VIDEO"


def clashing_stems(photos):
    seen = {}
    for p in photos:
        seen.setdefault(p["stem"].lower(), []).append(p)
    return {k: v for k, v in seen.items() if len(v) > 1}


def preview_path(run, p, clashes):
    if p["stem"].lower() in clashes:
        return os.path.join(run, "previews", "dup", str(p["id"]), p["stem"] + ".jpg")
    return os.path.join(run, "previews", p["stem"] + ".jpg")


def sort_key(p):
    return (p.get("captureTime") or "9999", p.get("filename") or "", p["id"])


def resolve_refs(photos, refs):
    """Returns photos matching any ref, in capture order. Dies on a ref that matches nothing."""
    if refs == "all" or refs == ["all"]:
        return sorted(photos, key=sort_key)
    if isinstance(refs, (str, int)):
        refs = [refs]
    out = {}
    for ref in refs:
        r = str(ref)
        hits = [p for p in photos if str(p["id"]) == r]
        if not hits:
            hits = [p for p in photos if (p.get("filename") or "").lower() == r.lower()
                    or p["stem"].lower() == r.lower()]
        if not hits:
            hits = [p for p in photos if fnmatch.fnmatch((p.get("filename") or "").lower(), r.lower())]
        if not hits:
            die(f"photo ref matches nothing: {r}")
        for p in hits:
            out[p["id"]] = p
    return sorted(out.values(), key=sort_key)


def short_name(p, common):
    name = p["stem"]
    if common and name.startswith(common) and len(name) > len(common):
        name = name[len(common):]
    return name[-22:]


def common_prefix(photos):
    stems = [p["stem"] for p in photos]
    if len(stems) < 2:
        return ""
    prefix = os.path.commonprefix(stems)
    # cut back to a separator so a label never starts mid-word
    cut = max(prefix.rfind("-"), prefix.rfind("_"), prefix.rfind(" "))
    return prefix[:cut + 1] if cut >= 0 else ""


def build_sheet(run, photos, clashes, out_path, cols, cell, label_time=True, common=""):
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 18)
    except Exception:
        font = ImageFont.load_default()
    label_h = 30
    rows = math.ceil(len(photos) / cols)
    sheet = Image.new("RGB", (cols * cell, rows * (cell + label_h)), (32, 32, 32))
    draw = ImageDraw.Draw(sheet)
    missing = []
    for i, p in enumerate(photos):
        x, y = (i % cols) * cell, (i // cols) * (cell + label_h)
        path = preview_path(run, p, clashes)
        if os.path.exists(path):
            im = Image.open(path).convert("RGB")
            im.thumbnail((cell - 8, cell - 8))
            sheet.paste(im, (x + (cell - im.width) // 2, y + (cell - im.height) // 2))
        else:
            missing.append(p.get("filename"))
            draw.text((x + 10, y + cell // 2), "no preview", fill=(255, 80, 80), font=font)
        label = short_name(p, common)
        if label_time and p.get("captureTime"):
            label += "  " + p["captureTime"][5:16].replace("T", " ")
        draw.text((x + 6, y + cell + 4), label, fill=(235, 235, 235), font=font)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    sheet.save(out_path, quality=82)
    return missing


def cmd_prep(run):
    photos = load_photos(run)
    stills = [p for p in photos if not is_video(p)]
    videos = [p for p in photos if is_video(p)]
    clashes = clashing_stems(stills)
    clash_ids = {p["id"] for group in clashes.values() for p in group}
    normal = [p["id"] for p in sorted(stills, key=sort_key) if p["id"] not in clash_ids]
    chunks = [normal[i:i + CHUNK] for i in range(0, len(normal), CHUNK)]
    export = {
        "destination": os.path.join("previews"),
        "chunks": chunks,
        "clashing": [{"id": p["id"], "filename": p["filename"],
                      "destination": os.path.join("previews", "dup", str(p["id"]))}
                     for group in clashes.values() for p in group],
    }
    with open(os.path.join(run, "export.json"), "w", encoding="utf-8") as f:
        json.dump(export, f, indent=1)
    # export_photos fails with "destination folder is missing" unless these exist
    os.makedirs(os.path.join(run, "previews"), exist_ok=True)
    for item in export["clashing"]:
        os.makedirs(os.path.join(run, item["destination"]), exist_ok=True)
    marked = sum(1 for p in photos if MARKER in p["keywordPaths"])
    no_time = sum(1 for p in stills if not p.get("captureTime"))
    no_gps = sum(1 for p in stills if not p.get("gps"))
    dates = sorted({(p.get("captureTime") or "")[:10] for p in stills if p.get("captureTime")})
    print(f"photos: {len(photos)}  stills: {len(stills)}  videos (skipped): {len(videos)}")
    print(f"already marked '{MARKER}': {marked}")
    print(f"no capture time: {no_time}  no GPS: {no_gps}")
    print(f"capture dates: {len(dates)}" + (f"  ({dates[0]} .. {dates[-1]})" if dates else ""))
    print(f"export chunks: {len(chunks)} x <= {CHUNK} ids  -> export.json")
    print(f"clashing file stems (export one photo per call into its own folder): {len(export['clashing'])}")


def cmd_sheets(run, args):
    per, batch = 8, 80
    if "--per" in args:
        per = int(args[args.index("--per") + 1])
    if "--batch" in args:
        batch = int(args[args.index("--batch") + 1])
    photos = [p for p in sorted(load_photos(run), key=sort_key) if not is_video(p)]
    clashes = clashing_stems(photos)
    common = common_prefix(photos)
    # keep a capture date together where it fits in one batch
    batches, current = [], []
    by_date = {}
    for p in photos:
        by_date.setdefault((p.get("captureTime") or "")[:10], []).append(p)
    for date in sorted(by_date):
        group = by_date[date]
        if current and len(current) + len(group) > batch:
            batches.append(current)
            current = []
        while len(group) > batch:
            batches.append(group[:batch])
            group = group[batch:]
        current += group
    if current:
        batches.append(current)
    cols = 4
    missing = []
    for bi, b in enumerate(batches, 1):
        with open(os.path.join(run, f"batch{bi:02d}.json"), "w", encoding="utf-8") as f:
            json.dump({"ids": [p["id"] for p in b],
                       "files": [p["filename"] for p in b]}, f, indent=1)
        for si in range(0, len(b), per):
            out = os.path.join(run, "sheets", f"b{bi:02d}_s{si // per + 1:02d}.jpg")
            part = b[si:si + per]
            missing += build_sheet(run, part, clashes, out, min(cols, len(part)), 600, common=common)
    print(f"batches: {len(batches)}  sheets: {sum(math.ceil(len(b) / per) for b in batches)}  in sheets/")
    print(f"label prefix dropped: '{common}'")
    if missing:
        print(f"MISSING PREVIEWS ({len(missing)}): " + ", ".join(str(m) for m in missing[:20]))


def cmd_qsheet(run, args):
    if len(args) < 2:
        die("usage: qsheet <run> <name> <ref>...")
    name, refs = args[0], args[1:]
    photos = load_photos(run)
    chosen = resolve_refs(photos, refs)
    clashes = clashing_stems([p for p in photos if not is_video(p)])
    cols = min(len(chosen), 3 if len(chosen) <= 6 else 5)
    out = os.path.join(run, "q", name + ".jpg")
    missing = build_sheet(run, chosen, clashes, out, cols, 460, label_time=False,
                          common=common_prefix(photos))
    print(f"{out}: {len(chosen)} photos" + (f"  MISSING PREVIEWS: {missing}" if missing else ""))


def merged_plan(run, photos):
    path = os.path.join(run, "plan.json")
    if not os.path.exists(path):
        die(f"{path} not found")
    with open(path, encoding="utf-8") as f:
        plan = json.load(f)
    by_id = {p["id"]: p for p in photos}
    per = {}
    problems, skipped = [], []
    for ci, change in enumerate(plan.get("changes", []), 1):
        targets = resolve_refs(photos, change.get("photos", []))
        for p in targets:
            entry = per.setdefault(p["id"], {"add": [], "remove": [], "gps": None})
            for kw in change.get("add", []):
                if kw not in entry["add"]:
                    entry["add"].append(kw)
            for kw in change.get("remove", []):
                if kw not in entry["remove"]:
                    entry["remove"].append(kw)
            if change.get("gps"):
                g = change["gps"]
                if entry["gps"] and entry["gps"] != g:
                    problems.append(f"change {ci}: {p['filename']} gets two different GPS positions")
                entry["gps"] = g
    new_keywords = plan.get("newKeywords", [])
    for kw in new_keywords:
        if REQUIRE_NESTED and "|" not in kw:
            problems.append(f"newKeywords: '{kw}' is not a full path")
    used_new = set()
    for pid, entry in per.items():
        p = by_id[pid]
        have = set(p["keywordPaths"])
        for kw in list(entry["add"]):
            if REQUIRE_NESTED and "|" not in kw:
                problems.append(f"{p['filename']}: add '{kw}' is not a full path")
            if kw == MARKER:
                problems.append(f"{p['filename']}: don't add the marker yourself")
            if kw in entry["remove"]:
                problems.append(f"{p['filename']}: '{kw}' is both added and removed")
            if kw in have:
                entry["add"].remove(kw)
                skipped.append(f"{p['filename']}: already has {kw}")
            if kw in new_keywords:
                used_new.add(kw)
        for kw in list(entry["remove"]):
            if REQUIRE_NESTED and "|" not in kw:
                problems.append(f"{p['filename']}: remove '{kw}' is not a full path")
            if kw not in have:
                entry["remove"].remove(kw)
                skipped.append(f"{p['filename']}: does not have {kw}")
        g = entry["gps"]
        if g is not None:
            try:
                lat, lon = float(g["latitude"]), float(g["longitude"])
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    raise ValueError
            except Exception:
                problems.append(f"{p['filename']}: bad gps {g}")
    for kw in new_keywords:
        if kw not in used_new:
            problems.append(f"newKeywords: '{kw}' is not added to any photo")
    reviewed = plan.get("reviewed", "all")
    reviewed_photos = [p for p in resolve_refs(photos, reviewed) if not is_video(p)]
    return plan, per, problems, skipped, reviewed_photos


def group_calls(pairs):
    """pairs: {keyword: set(ids)} -> [(sorted ids, [keywords])] merging identical id sets."""
    by_ids = {}
    for kw, ids in pairs.items():
        by_ids.setdefault(tuple(sorted(ids)), []).append(kw)
    return [(list(ids), sorted(kws)) for ids, kws in sorted(by_ids.items(), key=lambda x: (-len(x[0]), x[1]))]


def split_ids(ids):
    return [ids[i:i + MAX_IDS] for i in range(0, len(ids), MAX_IDS)]


def cmd_plan(run):
    photos = load_photos(run)
    plan, per, problems, skipped, reviewed = merged_plan(run, photos)
    if problems:
        print("PLAN NOT VALID:")
        for line in problems:
            print("  " + line)
        sys.exit(1)
    new_keywords = set(plan.get("newKeywords", []))
    adds, removes, new_adds, gps = {}, {}, {}, {}
    for pid, entry in per.items():
        for kw in entry["add"]:
            (new_adds if kw in new_keywords else adds).setdefault(kw, set()).add(pid)
        for kw in entry["remove"]:
            removes.setdefault(kw, set()).add(pid)
        if entry["gps"]:
            g = entry["gps"]
            gps.setdefault((float(g["latitude"]), float(g["longitude"])), set()).add(pid)
    calls = []
    # Agreed new keywords first, one call each, the only calls allowed to create.
    for kw, ids in sorted(new_adds.items()):
        for part in split_ids(sorted(ids)):
            calls.append({"tool": "set_keywords", "why": "create agreed new keyword",
                          "args": {"photo_ids": part, "add_keywords": [kw], "create_missing": True}})
    add_groups = {tuple(ids): kws for ids, kws in group_calls(adds)}
    remove_groups = {tuple(ids): kws for ids, kws in group_calls(removes)}
    for ids in sorted(set(add_groups) | set(remove_groups), key=lambda x: (-len(x), x)):
        for part in split_ids(list(ids)):
            args = {"photo_ids": part, "create_missing": False}
            if ids in add_groups:
                args["add_keywords"] = add_groups[ids]
            if ids in remove_groups:
                args["remove_keywords"] = remove_groups[ids]
            calls.append({"tool": "set_keywords", "why": "agreed changes", "args": args})
    for (lat, lon), ids in sorted(gps.items()):
        for part in split_ids(sorted(ids)):
            calls.append({"tool": "set_gps", "why": "agreed position",
                          "args": {"photo_ids": part, "latitude": lat, "longitude": lon}})
    to_mark = sorted(p["id"] for p in reviewed if MARKER not in p["keywordPaths"])
    for part in split_ids(to_mark):
        calls.append({"tool": "set_keywords", "why": "mark as reviewed",
                      "args": {"photo_ids": part, "add_keywords": [MARKER], "create_missing": False}})
    with open(os.path.join(run, "calls.json"), "w", encoding="utf-8") as f:
        json.dump({"calls": calls}, f, indent=1)
    changed = [pid for pid, e in per.items() if e["add"] or e["remove"] or e["gps"]]
    print(f"photos reviewed: {len(reviewed)}  with changes: {len(changed)}")
    print(f"keyword adds: {sum(len(e['add']) for e in per.values())}  "
          f"removes: {sum(len(e['remove']) for e in per.values())}  "
          f"gps: {sum(1 for e in per.values() if e['gps'])}  "
          f"to mark: {len(to_mark)}")
    print(f"new keywords to create: {sorted(new_keywords) or 'none'}")
    print(f"skipped as no-ops: {len(skipped)}" + (" (first 10: " + "; ".join(skipped[:10]) + ")" if skipped else ""))
    print("distinct keywords to add (each must exist in the hierarchy):")
    for kw in sorted(adds):
        print(f"  {kw}  x{len(adds[kw])}")
    print(f"calls: {len(calls)} -> calls.json  (make them in order, one at a time)")


def cmd_verify(run):
    before = load_photos(run)
    after = {p["id"]: p for p in load_photos(run, "photos-after.json")}
    plan, per, problems, _skipped, reviewed = merged_plan(run, before)
    if problems:
        die("plan.json no longer validates: " + "; ".join(problems[:5]))
    reviewed_ids = {p["id"] for p in reviewed}
    bad = []
    for p in before:
        pid = p["id"]
        if pid not in after:
            bad.append(f"{p['filename']}: missing from photos-after.json")
            continue
        entry = per.get(pid, {"add": [], "remove": [], "gps": None})
        expected = (set(p["keywordPaths"]) | set(entry["add"])) - set(entry["remove"])
        if pid in reviewed_ids:
            expected.add(MARKER)
        got = set(after[pid]["keywordPaths"])
        for kw in sorted(expected - got):
            bad.append(f"{p['filename']}: should have {kw}")
        for kw in sorted(got - expected):
            bad.append(f"{p['filename']}: should not have {kw}")
        if entry["gps"]:
            g, a = entry["gps"], after[pid].get("gps") or {}
            if (abs(float(g["latitude"]) - float(a.get("latitude", 999))) > 1e-5
                    or abs(float(g["longitude"]) - float(a.get("longitude", 999))) > 1e-5):
                bad.append(f"{p['filename']}: gps is {a}, expected {g}")
        elif (p.get("gps") or {}) != (after[pid].get("gps") or {}):
            bad.append(f"{p['filename']}: gps changed unexpectedly")
    if bad:
        print(f"VERIFY FAILED: {len(bad)} mismatches")
        for line in bad[:60]:
            print("  " + line)
        sys.exit(1)
    print(f"VERIFY OK: {len(before)} photos match the plan exactly")


def cmd_clean(run):
    """Remove the whole run folder once the run has been applied and verified.

    Only runs when photos-after.json matches the plan. Deleting needs the user's
    permission for the connected folder; without it, the folder is moved to
    <working folder>/_to_delete/ instead.
    """
    import shutil
    before = load_photos(run)
    after = {p["id"]: p for p in load_photos(run, "photos-after.json")}
    _plan, per, problems, _skipped, reviewed = merged_plan(run, before)
    if problems:
        die("plan.json does not validate; not cleaning")
    reviewed_ids = {p["id"] for p in reviewed}
    for p in before:
        entry = per.get(p["id"], {"add": [], "remove": []})
        expected = (set(p["keywordPaths"]) | set(entry["add"])) - set(entry["remove"])
        if p["id"] in reviewed_ids:
            expected.add(MARKER)
        if p["id"] not in after or set(after[p["id"]]["keywordPaths"]) != expected:
            die("photos-after.json does not match the plan; run verify first. Nothing removed.")
    run = os.path.abspath(run)
    name = os.path.basename(run)
    try:
        shutil.rmtree(run)
        print(f"removed run folder: {name}")
        return
    except OSError as e:
        reason = e
    if not os.path.isdir(run):
        print(f"removed run folder: {name}")
        return
    parent = os.path.join(os.path.dirname(run), "_to_delete")
    os.makedirs(parent, exist_ok=True)
    target = os.path.join(parent, name)
    n = 1
    while os.path.exists(target):
        n += 1
        target = os.path.join(parent, f"{name} {n}")
    try:
        os.rename(run, target)
        print(f"NOT DELETED ({reason}): moved the run folder to {target}")
    except OSError as e:
        print(f"could not remove or move {run}: {e}")
        sys.exit(1)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    cmd, run, rest = sys.argv[1], sys.argv[2], sys.argv[3:]
    if not os.path.isdir(run):
        die(f"run folder not found: {run}")
    if cmd == "prep":
        cmd_prep(run)
    elif cmd == "sheets":
        cmd_sheets(run, rest)
    elif cmd == "qsheet":
        cmd_qsheet(run, rest)
    elif cmd == "plan":
        cmd_plan(run)
    elif cmd == "verify":
        cmd_verify(run)
    elif cmd == "clean":
        cmd_clean(run)
    else:
        die(f"unknown command: {cmd}")


if __name__ == "__main__":
    main()
