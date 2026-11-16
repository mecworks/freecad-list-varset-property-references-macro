# VarSet Property References Finder

## What this macro does

In FreeCAD, a **VarSet** is a small object that stores named values —
parameters like `Width = 40 mm` or `HoleDia = 8 mm`. Instead of typing a
fixed number into a feature, you can write a formula that reads from the
VarSet (for example, a pad length of `Vars.Width * 2`), so changing the
variable once updates every feature that uses it.

The catch: FreeCAD has no built-in way to show *where* a variable is used.
Before renaming or deleting one — or when a dimension mysteriously stops
updating — you'd have to comb through every formula by hand.

This macro fills that gap. It opens a dialog where you pick a VarSet and one
of its variables (FreeCAD calls them *properties*); the dialog then lists
**every formula in every open document that references that variable** — one
line per usage, with a count. It recognizes both reference styles
(`Vars.Width` and `<<My Vars>>.Width`), so other objects with coincidentally
similar names don't cause false hits. Because FreeCAD lets one file's
formulas reach into another open file, the scan covers all open documents by
default: usages from other files carry a `[DocumentName]` prefix, and
formulas pointing at a document that is **not open** are flagged with `(!)` —
a silently broken link that no longer follows the variable (see
[Cross-file references](#cross-file-references) below).

Works on FreeCAD 1.1 or newer; no third-party packages required.

> **To install:** use ONLY the generated
> [`ListVarSetPropertyReferences.FCMacro`](ListVarSetPropertyReferences.FCMacro)
> at the project root. The files in `src/` are development sources marked
> "DEVELOPMENT COPY -- do not install"; never drop them into your Macro
> folder.

Development background: full analysis of the legacy
`ListVarsetPropertyUsage.FCMacro` this project supersedes, with captured
evidence: see **[REPORT.md](REPORT.md)**.
Macro file-convention research behind the packaging decision:
[`research/MACRO_CONVENTIONS.md`](research/MACRO_CONVENTIONS.md).

## Files

| File | Purpose |
|------|---------|
| `ListVarSetPropertyReferences.FCMacro` | **Single-file distribution build** (generated at the project root). Self-contained: the core is embedded inside it. Copy just this file into your Macro folder. |
| `scripts/build_single_file.py` | Generator: combines the two development sources below into the single-file build. Re-run after any change. |
| `LICENSE` | Full text of the LGPL-2.1-or-later license. |
| `src/ListVarSetPropertyReferences_dev.FCMacro` | The macro (GUI layer), development source. Marked "do not install". |
| `src/varset_usage_core_dev.py` | Headless logic (discovery, matching, formatting). Development companion; must sit next to the dev macro. |
| `tests/test_core_unit.py` | Unit tests, plain Python fakes — no FreeCAD needed. |
| `tests/test_integration_freecad.py` | Integration test on a real document via `freecadcmd`. |
| `tests/test_distro_e2e.py` | End-to-end test of the single-file build (build → standalone exec → full dialog flow). |
| `research/` | API probe scripts + captured results used during development. |

## Install

**Option 1 — single file (recommended):** copy
`ListVarSetPropertyReferences.FCMacro` (project root) into your user Macro
folder (or any subfolder of it). It carries the headless logic embedded,
needs nothing else, and shows up as exactly one entry in the Macros dialog.

**Option 2 — development layout:** copy **both** files from `src/`
(`ListVarSetPropertyReferences_dev.FCMacro` and `varset_usage_core_dev.py`)
into the same folder. The macro loads the companion explicitly from its own
directory via `importlib` (no `sys.path` mutation); if it's missing you get a
clear error dialog instead of a traceback. Note the companion also appears
as an extra entry in the Macros dialog — FreeCAD lists every `.py` under the
Macro folder recursively (see `research/MACRO_CONVENTIONS.md`).

Then restart FreeCAD or open the Macro dialog (Macros ▸ Macros) and run
`ListVarSetPropertyReferences` with an active document that contains at least
one VarSet.

## Usage

1. Choose a **VarSet** (listed by label; internal names are shown as combo
   item data).
2. Choose one of its **properties** (standard properties like `Label` are
   filtered out automatically).
3. Results appear below, one line per usage:
   `Owner.Property = <expression>` — with a count header. Owners whose label
   differs from their internal name are shown as `Label (Name)` to keep lines
   unambiguous.

Notes:

- The expression list of **every open document** is snapshotted once when
  the dialog opens. That is provably safe: while the modal dialog runs
  (`exec()`), the main window is disabled, so expressions cannot change
  underneath it. As a side benefit, each selection change skips a rescan
  (see Performance).
- "Include other open documents" is checked by default: usages found outside
  the VarSet's own document are listed with a `[<document>]` prefix. Untick
  it to restrict the scan to the active document (previous behaviour).
- Matching is anchored to the selected VarSet. An expression counts only if
  it references *this* VarSet's property (by internal name or by `<<label>>`).
  References to other objects whose internal name merely ends with the
  VarSet's name (e.g. `MyDims.Width` when `Dims` is selected) do **not**
  match.
- Whitespace around the dot is tolerated; longer identifiers (`WidthX`) do
  not match `Width`.
- Standard properties are excluded using a baseline probed live from a
  throwaway bare VarSet at startup (falling back to the pinned set in the
  core), so future FreeCAD additions of standard properties won't leak into
  the variable list.
- **Dead cross-document references are flagged.** A usage line whose
  expression names a document that is not currently open (e.g. the source
  file was renamed, or the name was mistyped) gets a `(!)` prefix, and the
  report ends with a legend listing every missing document:

      2 usage(s):

      (!) DP.Len = DeadMaster#Vars.Width * 2
      Pad.Len = Dims.Width * 2

      Missing documents: DeadMaster

  Such bindings still hold their last value silently (see Cross-file
  references below); the flag is the only visible hint that they no longer
  propagate.

## Requirements

- FreeCAD ≥ 1.1 (developed and verified on 1.1.4, Windows).
- No third-party packages.

## License

Copyright (c) 2026 Marc Christensen &lt;mecworks@gmail.com&gt;.

This project is licensed under the GNU Lesser General Public License v2.1
or later (**LGPL-2.1-or-later**); see [LICENSE](LICENSE) for the full text.

## Performance

Each selection change scans every object's bound expressions in the document
(O(objects × expressions)) on the GUI thread. Compiled patterns are memoized
per (VarSet, property) pair and the expression list is snapshotted once per
dialog session, so the per-click cost is just the regex sweep. For typical
documents this is imperceptible; on very large assemblies (thousands of
parts with many driven dimensions) expect a short pause per click. If that
ever matters, the scan could be moved off the GUI thread — intentionally not
done, as it complicates the code for a rare case.

## Cross-file references

FreeCAD allows an expression in one document to reference a property in
another **open** document using `DocName#Object.Property` (wiki:
*Expressions*, "Cross-document linking"), e.g.:

    Master_File#VarSet.RackEarWidth * 2

Mechanism notes (verified on 1.1.4):

- The referenced document's **name** (its file name) is the key: create and
  save the master file first, then build dependents, and avoid renaming the
  master afterwards.
- How FreeCAD finds referenced documents: dependencies are keyed by
  **document name only** (no paths are stored in the files). When you open
  a document, FreeCAD automatically loads any referenced-but-missing
  documents by looking for a file with the matching name **in the same
  folder**, cascading through newly loaded documents.
- Renaming the master file therefore **silently breaks existing
  references**: the old name no longer matches any file, so
  `OldName#Object.Prop` bindings can never resolve again. The breakage is
  very well masked — the dependent file opens normally and driven
  properties keep their last computed value (evaluation is lazy), so the
  model looks fine. It is detectable via object state (`Touched`/
  `Invalid` plus a `Document 'OldName' not found ...` error) and via this
  macro's list (matching is text-based, so dead references still appear).
  Decisive test: change the variable in the master and watch the dependent
  — it will not follow. Fix by rewriting the affected expressions with the
  new document name, or by restoring the old file name.
- The referenced document must be **loaded** for the value to resolve; if
  you close it, the reference keeps its last value until it is reopened.
- Document-name matching is **case-sensitive**, and a dead reference
  **revives automatically** as soon as a document with the exact name opens
  again (verified on 1.1.4). Typing a wrong document name into the
  expression editor is accepted without complaint — the property simply
  sits `Touched`/`Invalid` until the right document appears.
- **Never name a VarSet variable after a unit keyword** (`W`, `V`, `A`,
  `N`, `m`, `mm`, `s`, …). The expression lexer ranks unit literals above
  identifiers, so an expression referencing such a property by name fails
  to parse outright (`Doc#Obj.W * 2` → `ParserError`). Rename the variable
  instead (e.g. `WallThickness`).
- The label form works too: `Master_File#<<Master Vars>>.RackEarWidth`.

Because such usages live in the *referring* document, the dialog scans every
open document by default. Example output mixing local and cross-file usages:

    2 usage(s):

    Pad.Len = Dims.Width * 2
    [Dependent_File] VentPart.Len = Master_File#VarSet.RackEarWidth * 2

## Running the tests

```bat
:: unit tests (any CPython 3)
python "tests\test_core_unit.py"
:: or: pytest tests\test_core_unit.py

:: integration test (needs FreeCAD; put freecadcmd on PATH or adjust the
:: path to your install). freecadcmd swallows script stdout and masks
:: exceptions with exit code 0, so use the capture runner, which writes
:: results + exit code to research\INTEGRATION_RUN.txt:
freecadcmd.exe "tests\run_capture.py"

:: single-file distribution build: generate + self-verify
python "scripts\build_single_file.py"

:: end-to-end test of the single-file build (writes research\DISTRO_E2E.txt)
freecadcmd.exe "tests\test_distro_e2e.py"
```

Both exit non-zero on failure, so they can gate a CI step.

After changing `src/ListVarSetPropertyReferences_dev.FCMacro` or
`src/varset_usage_core_dev.py`, re-run `python scripts\build_single_file.py` to
refresh the distributed file at the project root; the builder refuses to ship
a build whose embedded core is not byte-identical to the source module.
