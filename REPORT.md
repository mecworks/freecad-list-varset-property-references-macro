# Analysis Report — `ListVarsetPropertyUsage.FCMacro`

**Date:** 2026-11-15 · **Target platform:** FreeCAD 1.1.4+ (Qt6 / PySide6), Windows
**Method:** Static review of the macro, then empirical verification against the
installed FreeCAD 1.1.4 (`freecadcmd.exe`, headless probes — see
`research/PROBE_RESULTS.txt`), cross-checked against upstream FreeCAD source
(`main` branch) and the official wiki. Every API claim below was verified on
the target version; several commonly assumed APIs turned out to be wrong or
missing (section 4).

---

## 1. What the macro does

Opens a dialog listing all VarSets in the active document. Selecting a VarSet
fills a second combo with its user properties; selecting a property scans every
object's expression engine and lists expressions that reference it.

Overall assessment: the core idea is sound and the expression-collection loop
is actually correct for FreeCAD 1.x (see §4.2 — an early suspicion that it was
broken was disproven by probing). However, the error path is guaranteed to
crash, the matching logic produces false positives, and the UI code carries
dead Qt4-era boilerplate. Details below.

## 2. Bugs found (things that misbehave today)

| # | Sev. | Location | Problem | Evidence |
|---|------|----------|---------|----------|
| B1 | High | `errorDialog()` | References `os.path.basename(__file__)` but **`os` is never imported** → `NameError` the moment any error path fires ("no active document", "no VarSets"). | Code inspection; both paths are common (running with no document open). |
| B2 | High | `errorDialog()` | `from PySide import QtGui` + `QtGui.QMessageBox`: **`QMessageBox` no longer exists in `PySide6.QtGui`** → `ImportError`. So even if B1 were fixed, the error dialog crashes before showing anything. | Probe: `cannot import name 'QMessageBox' from 'PySide6.QtGui'`; it lives in `QtWidgets` (Qt ≥ 5 layout). |
| B3 | Med | `propertyChanged()` | Matching uses `\bProp\b` anywhere in the expression, so it reports usages of **any object's** same-named property, not just the selected VarSet's. E.g. querying `Dims.Width` also matches `Other.Width`. Defeats the tool's stated purpose. | Logic review; Expressions wiki confirms references carry the owner (`Name.Prop` / `<<Label>>.Prop`). |
| B4 | Med | `varsetChanged()` | Slot parameter is named `comboBox`, but `currentIndexChanged` delivers the **new index (int)**, not the widget. It only works because `itemText(int)` happens to accept an index. Any refactor expecting a widget breaks silently. | Probe: connected slot received `(0,)` / `(1,)` — ints. |
| B5 | Low | `varsetChanged()` | VarSet lookup via `getObjectsByLabel(label)` + `obj.Name.startswith('VarSet')`: (a) picks arbitrarily when two VarSets share a label, (b) relies on an internal-name prefix convention users can break (internal names are freely editable). | Probe: a VarSet created as `"Other"` is perfectly legal; duplicate labels accepted. |
| B6 | Low | module scope | `foundExpressions` is snapshotted once at startup; edits made while the dialog is open are not reflected. | Logic review. |
| B7 | Low | `errorDialog()` | `__file__` is only defined when the macro runs *from a file* (FreeCAD injects it in `Base::InterpreterSingleton::runFile`); pasted into the Python console it is undefined — a second latent `NameError` source. | Upstream `src/Base/Interpreter.cpp` (`runFile` sets `__file__` if absent). |

Dead code (cleanup): unused globals `reportMsg`, `singleUseMsg`; unused
`label_3`; `QtCore.QMetaObject.connectSlotsByName(Dialog)` and the whole
`retranslateUi`/`_translate` machinery (uic-template leftovers that do nothing
for a programmatic single-language UI); `exec_()` (deprecated alias — use
`exec()`); `if not len(varsets)` → `if not varsets`.

## 3. Improvements made and why

### Correctness

1. **Anchored usage matching** (fixes B3). The pattern now requires the
   reference to belong to the selected VarSet:
   `(?:<Name>|<<Label>>)\s*\.\s*<Prop>\b` — covering both reference styles
   documented on the Expressions wiki (internal `DataName` or `<<DataLabel>>`),
   tolerating whitespace around the dot, escaping regex metacharacters in
   names/labels, and rejecting longer identifiers (`WidthX`) via the trailing
   word boundary. Verified against real documents in
   `tests/test_integration_freecad.py` (decoy VarSet with the same property
   name is correctly excluded).
   *Trade-off:* results are now narrower than before by design — this tool is
   "where is *this* VarSet's property used". If you ever want the old
   "any object with this property name" behaviour, it is a one-line change to
   `usage_pattern()`.
2. **Type-based VarSet discovery** (fixes B5). `isDerivedFrom("App::VarSet")`
   instead of a name-prefix heuristic. `App::VarSet` is the authoritative
   TypeId (`src/App/VarSet.h`, added Feb 2024, PR #12135, shipped in 1.0).
   Note: `Document.getObjectsByType` **does not exist in 1.1.4** (§4.1), so the
   filter iterates `doc.Objects` — equally fast and portable.
3. **Direct object mapping in the dialog.** Combo row *i* maps to
   `self._varsets[i]`; no label round-trip, immune to duplicate labels.
4. **Fresh results.** The scan re-runs on every selection (cheap: linear over
   objects × bound expressions), removing the stale-snapshot problem (B6).
5. **Working error dialogs** (fixes B1/B2): `QtWidgets.QMessageBox.critical`
   static call, no `os`/`__file__` dependence, plus a top-level exception
   handler that prints the traceback to the console and shows a message box.

### Python quality

6. **Separated headless core from GUI** (`src/varset_usage_core_dev.py`): pure
   functions taking doc/object arguments, no Qt imports. Consequences:
   unit-testable with plain-Python fakes (no FreeCAD needed), reusable, and
   the macro shrinks to a thin dialog layer. The macro bootstraps
   `sys.path` from `__file__` (defined by FreeCAD's `runFile`, verified in
   `src/Base/Interpreter.cpp`) so the companion module resolves from any
   install location.
7. **Tuple unpacking** `for prop, expr in obj.ExpressionEngine:` instead of
   opaque `expression[0]/expression[1]` indexing — expresses intent
   (`ExpressionEngine` is a list of 2-tuples, §4.2).
8. **Explicit compiled regex per selection** (`re.compile` once, reused per
   expression) instead of implicit per-expression compilation.
9. **Result text built with a list + `"\n".join`**, not repeated string
   concatenation; friendly "(no usages found)" placeholder and a usage count.
10. **Signals:** `activated[int]` instead of `currentIndexChanged` — fires
    only on user interaction, so populating/clearing the combos no longer
    triggers spurious handler calls; slot parameters honestly typed as
    `index: int` (fixes B4).
11. PEP 8 naming (`snake_case` functions/variables), type hints, docstrings,
    dead code removed, `exec()` instead of deprecated `exec_()`.

### UI / FreeCAD practice

12. **Real layouts instead of absolute geometry.** The original mixes
    `setGeometry(...)` rectangles with a `gridLayoutWidget` wrapper (a uic
    artifact) — the dialog cannot resize sanely. Now: `QVBoxLayout` +
    `QHBoxLayout`, stretch factors, sensible default size; monospace font for
    the results pane.
13. **Standard-property exclusion promoted to a documented constant.**
    `STANDARD_PROPERTIES = {"ExpressionEngine","Label","Label2","Visibility"}`
    — verified on 1.1.4 to be *exactly* the `PropertiesList` of a bare
    `App::VarSet`, so everything else on a VarSet is a user variable.
14. Disambiguated result paths: `Label.Property`, or `Label (InternalName).Property`
    when they differ, so duplicate labels can't confuse the output.

## 4. API pitfalls discovered during verification (FreeCAD 1.1.4)

These matter for anyone improving this or similar macros; each was confirmed
empirically (probe outputs in `research/PROBE_RESULTS.txt`):

1. **`Document.getObjectsByType` does not exist.** Many older docs/examples
   show it, but 1.1.4 raises `AttributeError`. Available object lookups:
   `getObject`, `getObjectsByLabel`, `findObjects(Type=..., Name=..., Label=...)`
   (keyword form — passing the type positionally fails with
   `ValueError: Empty module name`), plus manual filtering.
2. **`obj.ExpressionEngine` is a `list` of `(property, expression)` tuples**,
   not a dict: `.items()` raises `AttributeError`. Iterating yields tuples, so
   the original macro's `expression[0]/[1]` indexing was coincidentally
   correct for 1.x (it would have produced garbage on versions where it was a
   dict). An empty engine is falsy, so `if engine:` safely skips idle objects.
3. **`obj.Properties` (dict) does not exist** on `DocumentObject` in 1.1.4 —
   only `PropertiesList` (reported in alphabetical order, not creation order).
4. **`from PySide import ...` still works** (FreeCAD registers a `PySide` →
   `PySide6` alias), but `PySide2` is *not* aliased. New code should import
   `PySide6` explicitly.
5. **`QtGui.QMessageBox` is gone** (`ImportError`); use `QtWidgets.QMessageBox`.
   Both `QDialog.exec()` and the deprecated `exec_()` exist in this build —
   prefer `exec()`.
6. **`currentIndexChanged` passes the int index**, not the sender widget.
7. **`App.evalExpression` does not exist**; evaluation is
   `App.DocumentObject.evalExpression(expr)` (classmethod).
8. `__file__` is injected by `runFile` for file-run macros but not for
   console-pasted code.

## 5. Behavioural changes vs. the original

- Results are anchored to the selected VarSet (fewer, accurate hits; see §3.1).
- Dialog is resizable; slightly different proportions; monospace results.
- Error cases now show a real message box instead of crashing.
- A VarSet with no custom properties shows a hint instead of an empty combo.
- Two files required for the development layout: the dev macro +
  `src/varset_usage_core_dev.py` in the same folder (or just the single
  generated distribution file — see README).
- Report lines whose expression references a document that is **not open**
  are prefixed with `(!)` and summarised in a `Missing documents:` legend line
  (§10). Omitting the new optional parameter reproduces the old output
  byte-for-byte.

## 6. Testing

| Suite | Runner | Coverage | Status |
|-------|--------|----------|--------|
| `tests/test_core_unit.py` | any CPython (`python tests/test_core_unit.py` or pytest) | 43 tests on fakes: discovery, property filtering (incl. custom standard set), both reference styles, whitespace, identifier boundaries (both sides), superset-name rejection, cross-document reference matching, decoy exclusion, label escaping, display paths, formatting, malformed-engine tolerance, snapshot parameter, multi-document scan + prefixed reporting, **dead-reference detection** (token extraction incl. hyphenated basenames, tight operators/parens, unary minus, numeric-prefix operator reading, suffix-match rescue prevention, formatter flag + legend, legacy-call compatibility) | 43/43 pass |
| `tests/test_integration_freecad.py` | `freecadcmd.exe tests/run_capture.py` (runner captures output to `research/INTEGRATION_RUN.txt`; freecadcmd swallows script stdout and masks exceptions with exit code 0) | 27 checks on real 1.1.4 documents: real VarSets (incl. duplicate label + bare drift-check VarSet), real expressions in `Name` and `<<Label>>` forms, decoy/unrelated/superset-name exclusions, `STANDARD_PROPERTIES` drift assertion, end-to-end cross-document `DocName#Object.Property` scenario (value resolves, home-only scan misses, multi-doc scan finds with prefix), **dead-reference scenarios**: direct ghost binding (accepted by `setExpression`, flagged in report) and rename round-trip (binding survives save→rename→close→reopen verbatim, flagged; fresh current-name binding unflagged alongside), macro-file parse check | 27/27 pass |
| `tests/test_distro_e2e.py` | `freecadcmd.exe tests/test_distro_e2e.py` (self-reports to `research/DISTRO_E2E.txt`) | 27 checks on the **single-file distribution build** (§11): builder self-verification, generated-file parse, byte-exact embedded-core round-trip via AST extraction, metadata header presence, standalone execution from an empty folder (proves self-containment by module name), `__main__` guard firing `main()` (QMessageBox stubbed headless), full dialog flow through the distro namespace (local / cross-doc prefixed / dead-flagged lines, decoy exclusion, scan-all toggle), re-execution safety, development-layout regression (sibling load path, `sys.path` untouched) | 27/27 pass |

The integration suite caught one genuine surprise during development:
`PropertiesList` ordering is alphabetical, not creation order (§4.3).

## 7. Sources

- Empirical probes on installed FreeCAD 1.1.4 (`research/probe_api.py`,
  `research/probe2.py`, `research/PROBE_RESULTS.txt`).
- FreeCAD upstream (`main`): `src/App/VarSet.h` (+ history: PR #12135,
  2024-02-21), `src/App/DocumentObject.h` (`PropertyExpressionEngine
  ExpressionEngine` member), `src/App/DocumentObject.pyi` /
  `src/App/Document.pyi` stubs, `src/Base/Interpreter.cpp` (`runFile`).
- FreeCAD wiki: *Expressions* (referencing objects by `DataName` or
  `<<DataLabel>>`), *Macros*.
- PySide6 (bundled with FreeCAD 1.1.4): module/class locations verified by
  direct import attempts.


## 8. Code-review fixes applied (2026-11-15)

An external code review arrived as `CODE_REVIEW.md`. Every finding was
re-verified against the actual code and the installed FreeCAD 1.1.4 before
being applied; all were confirmed and are now implemented. Evidence:
`research/probe_review.py` / `PROBE_REVIEW.txt`,
`research/probe_review2.py` / `PROBE_REVIEW2.txt`,
`research/smoke_macro.py` / `SMOKE_RESULTS.txt`.

| ID | Finding | Disposition |
|----|---------|-------------|
| R1 | Missing left word-boundary in `usage_pattern()` → false positives when another object's internal name ends with the selected VarSet's name (`MyDims.Width` matching `Dims`) | **Confirmed** (reproduced standalone). Fixed with leading `(?<!\w)`; regression tests added (unit + live integration decoy `SuperDims`). |
| R2 | `raise SystemExit(1)` at module level in the macro | **Confirmed.** Removed: import failure now degrades gracefully (`core = None`, one error dialog, guarded `main()`); `except ImportError` widened to `except Exception` so a companion that fails mid-import is also reported cleanly. Verified headless: no `SystemExit`, exactly one dialog, `main()` no-op. |
| S1 | Global `sys.path.insert(0, …)` pollutes the session | **Confirmed.** Companion now loaded via `importlib.util.spec_from_file_location` from the macro's own directory; plain-`import` fallback kept for console-paste. Verified: `sys.path` byte-identical after macro load. |
| S2 | Combo `userData` stored but index-based lookup used | **Confirmed.** Selections now keyed by stored internal `Name` (`currentData()` → `{name: obj}` dict), decoupled from row order. |
| S3 | Hardcoded, version-pinned `STANDARD_PROPERTIES` | **Confirmed.** Macro now probes the baseline live from a throwaway bare VarSet at startup (fallback: pinned set); core gained a `standard=` override parameter; integration suite asserts the pinned set still equals a live bare VarSet's `PropertiesList` and fails loudly on drift. Docstring notes the inverse edge case (a user property literally named `Label2` is filtered out). |
| S4 | Whole-document rescan per selection change | **Confirmed.** Compiled patterns memoized per (Name, Label, prop) — provably safe since the pattern is a pure function of those strings; expression list snapshotted once per dialog session (modal ⇒ provably fresh). README gained a Performance section. |
| S5 | Empty `Label` renders a blank combo entry | **Confirmed.** `varset.Label or varset.Name` fallback. |
| N1 | Style nits | Applied: `re.Pattern` instead of deprecated `typing.Pattern`; `currentIndex`/`currentData` guard; redundant `results.clear()` dropped; `_dialog_ref` comment clarified (GC protection, not required); SPDX headers added to both files; `iter_expressions` skips malformed engine entries defensively. **One correction:** see below. |

### Correction found while verifying N1

The review suggested replacing `font.setFixed(True)` with
`font.setFamily(QtGui.QFont.Fixed)`. Probing the actual bundled PySide6
6.8.3 showed **both** forms are wrong:

- `QFont.setFixed` does not exist in this build — the pre-existing line was
  a **latent runtime crash** (the dialog would die on construction), which
  the original test suite never exercised because it only parses the macro
  file.
- `QFont.Fixed` / `QFont.StyleHint.Fixed` do not exist either (this
  PySide6 exposes a reduced `StyleHint` enum without `Fixed`), so the
  review's proposed replacement would have crashed identically.

Applied instead: `font.setStyleHint(QtGui.QFont.StyleHint.Monospace)` —
verified working, and asserted in the headless GUI smoke test.

### Post-fix verification matrix

| Suite | Before | After | Result |
|-------|--------|-------|--------|
| Unit (`tests/test_core_unit.py`, CPython) | 15 pass | 19 tests (superset-name regression, snapshot param, custom standard set, malformed-engine tolerance) | 19/19 pass |
| Integration (`freecadcmd`, real 1.1.4 doc) | 10 pass | 12 checks (+ `STANDARD_PROPERTIES` drift assertion, + superset-named decoy exclusion) | 12/12 pass |
| Headless macro smoke (`research/smoke_macro.py`) | — | A: importlib load w/o `sys.path` mutation · B: graceful degradation path · C: full offscreen-QT dialog flow incl. font hint and decoy exclusion | all green |


## 9. Cross-document behaviour (probed 2026-11-15, corrected same day)

Question: what happens when a VarSet property is referenced from a
*different* file (e.g. a derived part built against a base object whose
variables live in the base file)?

**Correction:** the first probe round concluded that no cross-document
reference syntax exists. That conclusion was wrong: the probes tested
`Base.Dims.Width` (dot form) and function-call forms, but never the actual
syntax `DocName#Object.Property`, which was reported by the user and then
confirmed empirically. It is also documented in the FreeCAD wiki (*Expressions*,
"Cross-document linking": `master#modelConstants.Length`; the referenced
document must be loaded for its values to resolve).

Evidence: `research/probe_xref.py` / `PROBE_XREF.txt` (plus the superseded
first-round files `probe_crossdoc*.py` / `PROBE_CROSSDOC*.txt`).

| Scenario | FreeCAD 1.1.4 behaviour | Macro result (after fix) |
|----------|------------------------|--------------------------|
| Expression in doc B references VarSet in doc A: `Master_File#VarSet.RackEarWidth * 2` | Accepted, stored verbatim in `ExpressionEngine`, **resolves correctly** (probe: 5 mm × 2 → 10 mm). Label form `Master_File#<<Master Vars>>.RackEarWidth` works too. | Found when scanning doc B — the anchored pattern matches the reference text (`#` is a non-word char, so the left-boundary guard passes). Listed with a `[<source document>]` prefix. |
| Referenced document closed | Stored expression text persists; driven value goes stale (probe kept its last value); resolves again once the referenced document is reopened and the document recomputes. | Still listed (matching is text-based), so broken/stale cross-references remain visible. |
| Usage hidden behind an `App::Link` | `link.ExpressionEngine == []` — binding text belongs to the source object in the base file. | Visible only when the base file itself is scanned (run the macro there). |

Implementation (this round):

- The macro now scans **all open documents** by default (checkbox
  "Include other open documents", on by default). Result lines whose usage
  lives outside the VarSet's own document are prefixed with
  `[<document label>]`; local lines keep their plain form, so single-file
  output is unchanged.
- Expressions of every open document are snapshotted once when the dialog
  opens (application-modal ⇒ none can change while it runs).
- Core additions: `find_usages_all(docs, varset, prop, snapshots=None)`
  returning `(doc, path, expr)` triples, and `format_report_multi(matches,
  home_doc)` for the prefixed rendering.
- Idiomatic workflow per the wiki: create and *save* the master document
  first (its file name becomes the reference key), then build dependent
  documents; avoid renaming the master.
- Tests: unit coverage for cross-reference matching, multi-document scan
  and prefixed reporting; the integration suite reproduces the two-file
  scenario end-to-end (value resolves, home-only scan misses, multi-doc
  scan finds with prefix); the headless GUI smoke test drives the checkbox
  both ways.

### Rename behaviour (probed same day)

`research/probe_rename.py` / `PROBE_RENAME.txt` (controlled temp-dir
experiment) and `research/probe_livelink.py` / `PROBE_LIVELINK.txt`
(in-memory-only measurement of the author's own files; nothing was saved).

- Dependencies are keyed by **document name only**; neither file stores a
  path or identifier for the other. On open, FreeCAD 1.1 auto-loads
  referenced-but-missing documents by **same-folder filename match**,
  transitively: opening just `Master_File.FCStd` +
  `Dependent_File.FCStd` pulled in three more documents
  (`Chassis_File`, `Assembly_File`, `Fan_File`), all resolved
  from the same folder; no recent-files registry is involved (checked
  `user.cfg`). A synthetic control confirmed the loader does *not* guess:
  when the only referenced file had been renamed away, nothing extra
  loaded.
- A renamed master therefore cannot satisfy old-name requests. The
  breakage is masked: the dependent file opens cleanly, driven properties
  retain their last saved value (expression evaluation is lazy — nothing
  re-evaluates unless the object is touched), so geometry looks correct.
- Verified on the real files (in memory only): raising
  `Master_File.VarSet.WallThickness` from 5 to 6 mm left
  `Dependent_File.Pad.Length` frozen at 5.0 mm with state
  `['Touched', 'Invalid']` (the binding still reads
  `FanMount_File#VarSet.WallThickness`), while a fresh
  in-memory binding `Master_File#VarSet.WallThickness * 2` resolved to
  12.0 mm in the same session. Old-name link: dead. Current-name link:
  live.
- Consequence: after a rename, cross-file edits stop propagating even
  though nothing visibly fails. Detection: object state, the saved
  `Invalid="1"` error attribute, or this macro (text-based matching lists
  dead references too). Repair: rewrite the affected expressions with the
  new document name, or restore the old file name.

## 10. Dead-reference detection (added 2026-11-15)

Feature: flag report lines whose expression references a document that is not
currently open — i.e. broken/stale cross-document bindings (the rename
scenario of §9, plus typos in the expression editor).

### Design

- Detection lives in the headless core (`src/varset_usage_core_dev.py`); the macro
  only supplies the set of open document names captured at dialog start
  (`set(App.listDocuments())`). Formatters take an optional
  `open_doc_names=None` parameter — omitting it preserves prior output
  byte-for-byte (backward compatible, asserted by unit tests).
- Affected lines get a `(!)` prefix; a trailing `Missing documents: <names>`
  legend lists every offending document once. Marker constant:
  `core.DEAD_REF_MARKER = "(!)"`.
- Token extraction scans backward from each `#` using a stop-character set
  (operators, parens, quotes, whitespace), so tightly adjacent syntax such
  as `(A#B.C)` or `2*A#B.C` extracts cleanly. Hyphens are admitted inside
  doc-name tokens (legal in Windows filenames); a secondary "operator
  reading" is offered only when the segment before the last hyphen is purely
  numeric, so `2-X#Y.Z` reads as subtraction while `Renamed-Away#V.W`
  correctly flags `Renamed-Away`. Matching is case-sensitive, mirroring the
  parser (§10.2 P2).

### Behavioural facts established this session

Probes: `research/probe_deadref5.py` / `PROBE_DEADREF5.txt` (clean),
`probe_realvarset.py` / `PROBE_REALVARSET.txt` (read-only inspection of the
user's real `VarSet` object — confirmed a genuine `App::VarSet`), plus the
superseded `probe_deadref*.py` rounds 1–4 (their ParserError findings were
artefacts of the lexer trap below).

| # | Fact | Evidence |
|---|------|----------|
| P1 | `setExpression` **accepts** a document name that exists nowhere. Parsing does not require the referenced document to exist: the grammar builds the path and `ObjectIdentifier::resolveAmbiguity()` returns early for forced identifiers (`src/App/ObjectIdentifier.cpp`); resolution is deferred to evaluation. The bound property sits `['Touched', 'Invalid']` until then. | PROBE_DEADREF5 P1 |
| P2 | Document-name matching is **case-sensitive**: `GHOSTDOC2#Vars.Width` did not resolve against an open document named `ghostdoc2`. | PROBE_DEADREF5 P2 |
| P3 | A dead reference **revives automatically** once a document with the exact name opens (and contains the referenced object/property): state returned to `Up-to-date` and the value recomputed (99 mm × 2 → 198 mm). No repair action needed if the renamed file is reopened under its *original* name (possible via `Document.load()` into a renamed document, cf. PROBE_RENAME S4). | PROBE_DEADREF5 P3 |
| L1 | **Lexer trap:** the expression scanner ranks unit literals above `IDENTIFIER` (`src/App/Expression.l`: unit rules precede the identifier rule; identifiers are letters/digits/`_`/`@` only). A property named after a unit keyword — e.g. `W` (watt), also `V`, `A`, `N`, `m`, `mm`, `s`, … — makes any expression referencing it by name unparseable: `Doc#Obj.W * 2` lexes the trailing `W` as the watt-unit token → grammar mismatch → `ParserError: Failed to parse expression`. This bit four consecutive probe rounds (rounds 1–4 all used a synthetic property named `W`) and masqueraded as "cross-document refs to VarSet properties fail" — they do not; `WallThickness`/`Width` work fine, including on the user's real files. Practical consequence: **never name a VarSet variable after a unit keyword**; such a property is effectively unreferenceable in expressions. | Source: `Expression.l`/`Expression.y` (main branch, commit 157bfcb); empirically: rounds 1–4 vs. round 5 with `Width` |
| F1 | Fixture-building constraints under `freecadcmd`: `setExpression` raises `RuntimeError: Owner document not saved` if the owner document has never been saved (but NOT for pure ghost references — P1's owner was unsaved); and `closeDocument` silently discards unsaved modifications, so a binding made after `saveAs` must be persisted with a second `save()` before closing. Both cost one failed test run each. | Integration suite history |

### Verification

- Unit: 18 new tests (extraction edge cases, dedup, local expressions,
  hyphen handling, formatter flag/legend, legacy-call compatibility,
  multi-doc cross-flagging).
- Integration: two live scenarios — (a) direct ghost binding created and
  flagged without any disk I/O; (b) full rename round-trip proving the dead
  binding persists through save→rename→close→reopen and is flagged in the
  multi-doc report while a fresh current-name binding in the same report is
  not.
- Smoke: unchanged dialog flow verified with the new `open_doc_names`
  plumbing (`SMOKE_RESULTS.txt`).

## 11. Single-file distribution build (added 2026-11-15)

Decision context: `research/MACRO_CONVENTIONS.md`. FreeCAD's Macros dialog
lists every `*.FCMacro` **and** `*.py` under the Macro folder recursively
(`DlgMacroExecuteImp::filterFiles`), so the development companion module
shows up as an extra executable entry. The community's dominant convention
for shared macros is a single file (Macro Animator's consolidation,
chennes' embedded-text pattern, official repo metadata headers). Chosen:
**option (b)** — a generated self-contained `.FCMacro`.

### Mechanism

- `scripts/build_single_file.py` combines the two development sources in `src/`
  into `ListVarSetPropertyReferences.FCMacro` at the project root:
  - the full core source is embedded as a raw string literal
    `_EMBEDDED_CORE_SOURCE = r'''...'''` between the EMBEDDED CORE markers;
    no padding newlines, so the literal's value is the core source
    **byte-for-byte** (safe because the core contains no `'''` and does not
    end with a backslash — both asserted by the builder);
  - an official metadata header (`__Name__`, `__Version__`, `__License__`,
    `__Requires__`, … as used by github.com/FreeCAD/FreeCAD-macros) is
    inserted after the module docstring, so Addon Manager installs pick it
    up.
- The macro's loader (`_load_core()`) now has three sources in priority
  order: embedded copy → sibling file (development layout) → plain import
  (console paste). Executing the embedded source into a fresh
  `types.ModuleType` registers nothing in `sys.modules` and mutates nothing
  global.
- The development layout stays the source of truth; the distro file is
  generated, never hand-edited. The builder self-verifies (parse, metadata,
  byte-exact embed) and exits non-zero on failure.

### Verification

`tests/test_distro_e2e.py` (27/27, `research/DISTRO_E2E.txt`):

- D0–D2: build + independent structural checks (AST-extracted embedded
  source compared byte-for-byte against `src/varset_usage_core_dev.py`).
- D3: the distro file copied **alone into an empty folder** executes cleanly
  and loads its embedded copy (module name `varset_usage_core_embedded`
  proves the embedded branch was taken — no sibling existed); the
  `if __name__ == "__main__"` guard fires `main()`, which reports
  "No active document found." (QMessageBox stubbed so the headless run
  cannot block on a modal).
- D4: full dialog flow through the distro-built namespace under offscreen
  Qt: local usage plain, cross-doc usage `[DistVent]`-prefixed, dead
  reference `(!) [DistGhost] GP.Len = PhantomDoc#Dims.Width * 2` flagged
  with `Missing documents: PhantomDoc` legend, superset-named decoy
  excluded, scan-all toggle drops foreign lines.
- D5: second exec in a fresh namespace reloads cleanly.
- D6: development-layout regression — the dev macro still loads the sibling
  file (`varset_usage_core_dev`) with `sys.path` untouched.

All pre-existing suites re-run green after the change: unit 43/43,
integration 27/27, smoke A/B/C.

### Naming and layout update (2026-11-15)

The legacy macro's basename (`ListVarsetPropertyUsage.FCMacro`) collided
with both the development source and the generated artifact, so the project
was renamed and re-laid-out:

- Distribution artifact: **`ListVarSetPropertyReferences.FCMacro`**
  (project root; `__Name__` = "List VarSet Property References",
  `__Version__` bumped to 1.2.0 to distinguish it from the earlier
  same-basename build).
- Development sources moved to `src/` with `_dev` suffixes and
  "DEVELOPMENT COPY -- do not install" banners:
  `src/ListVarSetPropertyReferences_dev.FCMacro`,
  `src/varset_usage_core_dev.py`. The loader's companion filename constant
  and error messages follow suit.
- The builder now writes the deliverable to the project root (top level =
  what you ship; `src/` = sources; `scripts/` = build tooling only).
- All four suites re-run green after the change (unit 43/43, integration
  27/27, smoke A/B/C, distro e2e 27/27), plus a rebuild idempotence check
  (two consecutive builds byte-identical).
