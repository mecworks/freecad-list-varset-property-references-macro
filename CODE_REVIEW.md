# Code Review — VarSet Property Usage Macro

**Reviewed:** 2026-11-15
**Files reviewed (unmodified):**
- `ListVarsetPropertyUsage.FCMacro` (GUI wrapper, 161 lines)
- `varset_usage_core.py` (headless core, 131 lines)
- Supporting context checked: `tests/test_core_unit.py`, `research/PROBE_RESULTS.txt`

---

## Summary

Overall this is **well-above-average macro code**. The architecture is sound: a Qt-free headless core with GUI isolation, evidence-based API documentation (the probe results in `research/` back up every cited FreeCAD 1.1.4 fact), defensive `getattr` usage, proper regex escaping, correct modal-dialog lifetime handling, and a genuinely useful unit-test suite that runs under plain CPython.

However, there is **one real correctness bug** (false-positive matches when another object's internal name ends with the selected VarSet's name), **one risky control-flow construct** (`raise SystemExit(1)` at module level inside a macro), and several design/hygiene issues worth fixing. Severity legend below:

- **[REQUIRED]** Bug or risk; fix before shipping.
- **[SHOULD]** Design/API improvement; clear benefit, low effort.
- **[NICE]** Polish / minor.

---

## Findings

### R1 [REQUIRED] — False positives: missing left word-boundary in `usage_pattern()`

**File:** `varset_usage_core.py`, `usage_pattern()` (~line 96)

The compiled pattern is:

```python
rf"(?:{anchors})\s*\.\s*{re.escape(prop)}\b"
```

It guards the *right* side of the property name (`\b` rejects `WidthX`) but has **no guard on the left side of the anchor**. Because `re.search` finds substrings, an expression belonging to a *different* object whose internal `Name` merely *ends with* the selected VarSet's name will match:

```python
import re
pat = re.compile(r'(?:Dims)\s*\.\s*Width\b')          # VarSet Name="Dims", prop="Width"
bool(pat.search('MyDims.Width * 2'))                   # -> True  (FALSE POSITIVE)
```

Concrete scenario: document contains VarSet `Dims` and pad feature `MyDims`; the user selects `Dims.Width`; the report lists `MyDims.Length = MyDims.Width * 2` as a usage of `Dims.Width`. This defeats the stated purpose of anchoring ("avoids false positives from other objects").

**Verified:** reproduced standalone (CPython 3.11); the existing test `test_pattern_rejects_other_objects_with_same_property` uses `"Other"`, which does not overlap `"Dims"`, so the suite does not catch this.

**Fix (verified against all existing test cases):** add a negative lookbehind asserting the character before the reference is not a word character:

```python
return re.compile(rf"(?<!\w)(?:{anchors})\s*\.\s*{re.escape(prop)}\b")
```

`(?<!\w)` is safe for both alternatives: internal names are identifiers (a preceding letter/digit means a longer identifier), and `<<Label>>` references in valid expressions always begin after whitespace, an operator, or start-of-string. Verified: rejects `MyDims.Width * 2`, still matches `Dims.Width * 2` and `<<My Dims>>.Width + 1mm`.

**Required accompanying change:** add a regression test, e.g.:

```python
def test_pattern_rejects_superset_names():
    pat = core.usage_pattern(_vs(), "Width")   # _vs() Name="Dims"
    assert not pat.search("MyDims.Width * 2")
    assert not pat.search("xDims . Width")
```

and extend `test_find_usages_end_to_end` with a decoy object named e.g. `SuperDims` holding an expression referencing itself.

---

### R2 [REQUIRED] — `raise SystemExit(1)` at module level in a macro context

**File:** `ListVarsetPropertyUsage.FCMacro`, import-guard block (~lines 52–58)

```python
except ImportError:
    _fatal(...)
    raise SystemExit(1)
```

`SystemExit` derives from `BaseException`, not `Exception`. FreeCAD's macro runner catches Python exceptions raised by `runFile` and reports them; behavior for `SystemExit` crossing the embedded-interpreter boundary is not part of any contract and depends on how the C++ layer converts the error — worst case it aborts the process instead of printing a traceback. Even if benign today, terminating a long-running CAD session because a companion file is missing is disproportionate.

**Fix:** avoid abnormal control flow entirely. Show the dialog, then degrade gracefully:

```python
try:
    import varset_usage_core as core
except Exception as exc:                      # broader than ImportError: also
    _fatal(failed_import_message(str(exc)))    # catches broken deps inside core
    core = None
```

then guard `main()` with `if core is None: return`. Two benefits at once: no `SystemExit`, and the wider net also catches the case where `varset_usage_core.py` exists but fails mid-import (currently the user gets only a raw traceback in the console).

---

### S1 [SHOULD] — Global `sys.path.insert(0, ...)` pollutes the whole FreeCAD session

**File:** `ListVarsetPropertyUsage.FCMacro`, ~lines 37–40

Inserting the macro directory at position 0 of `sys.path`:

1. Persists for the entire FreeCAD session and affects *every* later `import` by *any* macro. If another macro folder contains a same-named module, resolution order changes globally (position 0 wins over everything else).
2. Survives moving/renaming the macro folder (stale path entry remains).
3. Is unnecessary: you know the exact file location.

**Fix:** load the companion explicitly with `importlib`, touching no global state:

```python
import importlib.util

_CORE_PATH = os.path.join(_MACRO_DIR, "varset_usage_core.py") if _MACRO_DIR else None
if _CORE_PATH and os.path.isfile(_CORE_PATH):
    spec = importlib.util.spec_from_file_location("varset_usage_core", _CORE_PATH)
    core = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(core)
else:
    core = None
```

Keep the plain-`import` fallback for the paste-into-console case (where `__file__` is absent), wrapped in the same graceful-degradation pattern from R2.

---

### S2 [SHOULD] — Combo-box `userData` is stored but never used (dead data / inconsistent lookup)

**File:** `ListVarsetPropertyUsage.FCMacro`, `_populate_varsets()` / `_on_varset_changed()`

```python
self.varset_combo.addItem(varset.Label, varset.Name)      # stores Name as userData
...
varset = self._varsets[index]                              # ...but looks up by index
```

Either commit to one strategy or the other. Index-coupling works today only because items are added in list order and never reordered/filtered; the moment anyone adds sorting or search, rows silently desynchronize from `self._varsets`. Preferred: use the stored `Name` as the key (Names are unique per document):

```python
name = self.varset_combo.currentData()
varset = next(v for v in self._varsets if v.Name == name)
```

(or keep a `{name: obj}` dict built alongside the combo). Same applies symmetrically to `property_combo` (property names are unique per object, so `itemText` is fine there — but be consistent).

---

### S3 [SHOULD] — `STANDARD_PROPERTIES` is a hardcoded, version-pinned exclusion set

**File:** `varset_usage_core.py`, `STANDARD_PROPERTIES`

Correctness of `user_properties()` hinges on a bare `App::VarSet` having *exactly* those four properties forever. If a future FreeCAD release adds a standard property to `DocumentObject`/`VarSet` (e.g. status flags, metadata), it will silently appear as a selectable "user variable," and worse, could produce confusing zero-result scans.

Options, increasing robustness:

1. Minimum: pin the claim loudly — docstring already says "verified on 1.1.4"; add a runtime sanity check in tests/integration that asserts `set(bare_varset.PropertiesList) == STANDARD_PROPERTIES` and fails loudly on drift.
2. Better: derive the baseline dynamically at startup by creating a throwaway `App::VarSet` in a temporary hidden document, reading its `PropertiesList`, deleting it, and using that set. Costs a few ms once; immune to upstream additions.

Also note the inverse edge case: a *user* who deliberately creates a property literally named `Label2` would have it filtered out. Acceptable trade-off, but worth a docstring sentence.

---

### S4 [SHOULD] — Whole-document rescan on every selection change (UI-thread latency)

**File:** `varset_usage_core.py`, `find_usages()`; called from `_on_property_changed()`

Each property-selection event walks **all** objects × **all** bound expressions and recompiles the regex. Fine for typical documents; on a large assembly (thousands of parts, many driven dimensions) each click pays O(objects × expressions) on the GUI thread, causing visible freezes.

Low-cost mitigations:

- Compile the pattern once per `(varset, prop)` pair (memoize in a small dict keyed by `(varset.Name, prop)`; Names are immutable, so no staleness).
- Precompute the per-object expression list once per dialog session (expressions can't change while the modal dialog is open — `exec()` blocks the main window — so a snapshot taken in `__init__` is provably fresh; drop the "always reflects current state" framing in the docstring accordingly).
- If truly huge docs matter, move the scan to a `QTimer.singleShot(0, ...)` hop or a worker thread with a busy cursor. Probably overkill; mention in README performance notes instead.

---

### S5 [SHOULD] — Empty `Label` renders a blank combo entry

**File:** `ListVarsetPropertyUsage.FCMacro`, `_populate_varsets()`

`addItem(varset.Label, ...)` shows nothing for a VarSet whose Label was cleared. Fall back like `display_path()` does:

```python
self.varset_combo.addItem(varset.Label or varset.Name, varset.Name)
```

---

### N1 [NICE] — Minor API/style nits

| Location | Item | Note |
|---|---|---|
| FCMacro `_build_ui` | `font.setFixed(True)` | Deprecated-style API; prefer `font.setFamily(QtGui.QFont.Fixed)`. Harmless on Qt6. |
| FCMacro `_on_property_changed` | `self.varset_combo.currentIndex()` | Can theoretically be `-1`; guard with `if index < 0: return` for robustness. |
| FCMacro `_on_varset_changed` | `self.results.clear()` before `setPlainText(...)` | Redundant; `setPlainText` replaces content. |
| FCMacro | `_dialog_ref` global | Strictly unnecessary — the local reference inside `main()` keeps the dialog alive throughout `exec()`. Keep for clarity, but the comment should say why (GC protection during `exec()`), not imply it's required. |
| core | `from typing import Pattern` | Deprecated alias; use `re.Pattern` (fine on the Py 3.11 FreeCAD 1.1 ships). |
| core `iter_expressions` | `for prop, expr in engine` | Assumes exactly-2-tuples. Documented as verified; consider `zip(engine_keys, engine_vals)`-style defensiveness or a `try/except ValueError` skip if you want crash-proofing against format drift. Low priority. |
| Both files | No license header | Add SPDX line (e.g. `# SPDX-License-Identifier: LGPL-2.0-or-later`) to match FreeCAD ecosystem norms. |
| FCMacro | Hardcoded English strings | FreeCAD macros rarely i18n; acceptable, but centralizing strings would make it trivial later. |

---

## Security Assessment

**Verdict: clean, with one hygiene issue.**

- ✅ No network access, no subprocess/shell, no `eval`/`exec`, no filesystem writes, no credential handling.
- ✅ All dynamic regex inputs (object `Name`, `Label`, property name) pass through `re.escape` — no injection into the pattern; the pattern is linear (two literal alternatives + bounded quantifiers), so no ReDoS exposure.
- ✅ `QMessageBox` text is plain text (no rich-text/HTML rendering), so `doc.Label` cannot inject markup.
- ⚠️ `sys.path.insert(0, ...)` (see S1) is the only security-relevant item: it widens import-resolution surface for the rest of the session and lets a malicious/coincidental same-named `.py` in the macro directory shadow modules imported by *other* macros. Fixing S1 removes this.
- ℹ️ Inherent caveat: FreeCAD macros execute arbitrary trusted-code by design; nothing here escalates beyond that model.

## API-Usage Assessment

**Verdict: accurate and unusually well-evidenced.** Cross-checked against `research/PROBE_RESULTS.txt` (FreeCAD 1.1.4, PySide6):

- `ExpressionEngine` handled as a list of `(prop, expr)` tuples — matches probe (`ee.items()` fails; iteration yields pairs). ✔
- `isDerivedFrom("App::VarSet")` for type detection — matches probe; correctly avoids the nonexistent `getObjectsByType`. ✔
- `QtWidgets.QMessageBox` (not `QtGui`) — matches probe. ✔
- `QComboBox.activated` chosen over `currentIndexChanged` with the correct rationale (programmatic population must not trigger slots) — matches probe2. ✔
- `app.ActiveDocument`, `PySide6` imports, `exec()` — all correct for FC 1.1+/Qt6. ✔

Remaining API risks are forward-compatibility ones (S3) rather than current-version errors.

## Correctness Verdict

- Logic, discovery, formatting, and GUI wiring are correct for the documented scope.
- **One demonstrable matching bug (R1)** producing false positives — the single most important fix.
- **One unsafe termination path (R2)**.
- Test suite quality is good (fake-based, pytest-compatible, covers label/name duality, escaping, dedup-by-type); gaps: the R1 regression case, empty-label behavior, and a live assertion that `STANDARD_PROPERTIES` still matches reality (S3 option 1).

---

## Consolidated Change List

### Required (fix before distribution)

1. **core `usage_pattern()`:** prepend `(?<!\w)` to the pattern → eliminates superset-name false positives. *(R1)*
2. **core tests:** add `test_pattern_rejects_superset_names` + end-to-end decoy with overlapping name. *(R1)*
3. **FCMacro import guard:** replace `raise SystemExit(1)` with graceful degradation (`core = None` + guarded `main()`); broaden `except ImportError` to `except Exception`. *(R2)*

### Should (strongly recommended)

4. **FCMacro:** load `varset_usage_core` via `importlib.util.spec_from_file_location`; stop mutating `sys.path`. *(S1)*
5. **FCMacro:** key combo selections off stored `Name` (`currentData()`), not row index. *(S2)*
6. **core:** either runtime-verify or dynamically derive `STANDARD_PROPERTIES`; add integration assertion against drift. *(S3)*
7. **core/macro:** memoize compiled patterns; snapshot expressions once per dialog session (modal ⇒ safe). *(S4)*
8. **FCMacro:** `varset.Label or varset.Name` fallback in the combo. *(S5)*

### Nice (polish)

9. `QFont.setFamily(QFont.Fixed)`; `currentIndex() >= 0` guard; drop redundant `results.clear()`; `re.Pattern` instead of `typing.Pattern`; clarify `_dialog_ref` comment; SPDX headers. *(N1)*

### Original code untouched

Per instruction, neither source file was modified; all fixes above are proposals only.
