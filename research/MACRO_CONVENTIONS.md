# Research: FreeCAD macro file conventions (single `.FCMacro` vs. multi-file)

**Date:** 2026-11-15 · **Scope:** whether `ListVarsetPropertyUsage.FCMacro` +
`varset_usage_core.py` should stay two files, collapse into one, or move the
core elsewhere. All source claims verified against FreeCAD `main` at commit
`157bfcb7462a733b03a7d041aeaa79fee7aff7a3` (same revision used for the
expression-parser research) and against installed FreeCAD 1.1.4 behaviour.

---

## 1. How FreeCAD discovers and presents macros

### 1.1 The Macros dialog lists BOTH `.FCMacro` AND `.py`, recursively

`src/Gui/Dialogs/DlgMacroExecuteImp.cpp`, `DlgMacroExecuteImp::filterFiles()`:

```cpp
QDir dir(folder, QLatin1String("*.FCMacro *.py"));
QStringList unfiltered;  // all .fcmacro and .py files
QDirIterator it(
    dir.path(),
    QStringList() << "*.FCMacro" << "*.py",
    QDir::Files,
    QDirIterator::Subdirectories          // <-- recursive
);
```

Facts that follow:

- Every `.py` file anywhere under the user Macro folder (top level **or any
  subfolder**) appears as an executable entry in the Macros dialog. There is
  no content-based exclusion, no notion of "helper module".
- The only filtering is the user's own find-by-name / find-in-content boxes.
- Listing sources: user Macro dir, system macro dir
  (`<FreeCAD home>/Macro`), and every entry in the `AdditionalMacroPaths`
  config parameter.
- Executing either extension goes through the same code path
  (`Base::InterpreterSingleton::runFile`, `src/Base/Interpreter.cpp`): the
  file is exec'd in `__main__` with `__file__` injected. A helper module that
  only defines functions runs harmlessly (no output, no effect) — but the
  dialog's *Edit* button opens it in the macro editor, where an accidental
  edit+save would corrupt it.

**Conclusion: a companion module next to a macro DOES pollute the macro
selector.** Placing it in a subfolder does not help (recursive listing).

### 1.2 Extension choice is convention, not enforcement

Wiki (*Macros*): "While Python scripts normally have the `.py` extension,
FreeCAD macros **should** have the `.FCMacro` extension." Soft wording.
`EditorView.cpp` offers both filters when saving; `DlgMacroExecuteImp`
appends `.FCMacro` to names without a recognised suffix. Practically:
`.py` macros are first-class citizens (the official macro repo contains
bare-`.py` macros such as `GenevaWheelGUI.py`, `apothemBasedPrism.py`).

### 1.3 The Macro folder IS on `sys.path` at startup

`src/App/FreeCADInit.py`, `register_macro_sources()` (RFE #0000504):

```python
std_macro = self.std_home / "Macro"
user_macro_default = Path(App.getUserMacroDir(False)).resolve()
user_macro = Path(App.getUserMacroDir(True)).resolve()

# add MacroDir to path (RFE #0000504)
self.search_paths.add(user_macro_default, ..., sys_path=PathPriority.FallbackLast)
self.search_paths.add(user_macro,        ..., sys_path=PathPriority.FallbackLast)
self.search_paths.add(std_macro,         ..., sys_path=PathPriority.FallbackLast)
```

Consequences:

- Any `.py` placed **directly** in the user Macro folder is importable with a
  plain `import <name>` from any macro, workbench, or the Python console —
  no `importlib` bootstrapping required.
- Priority is `FallbackLast` (appended after existing entries): a same-named
  module earlier on `sys.path` (stdlib, site-packages, another addon) wins.
  Our `importlib.util.spec_from_file_location` load sidesteps that shadowing
  risk entirely — strictly more robust than a plain import.
- Only the three macro dirs themselves are added, **not their subfolders**.
  A subfolder directly under the Macro dir is nevertheless importable as a
  PEP 420 namespace package (`from treeHelper import ui_treewindow`), which
  is exactly how the official repo's multi-file macros do it (§2.1).
- Applies to GUI and `freecadcmd` alike (shared init sequence).

## 2. What the ecosystem actually does

### 2.1 Official peer-reviewed repo: multi-file macros are sanctioned

`github.com/FreeCAD/FreeCAD-macros` (installed via Addon Manager) contains
multi-file macros packaged as `<name>.FCMacro` + a companion folder named
after the macro, with the extras declared in a metadata header. Canonical
example — `Utility/treeHelper.FCMacro`:

```python
__Name__ = "Tree Helper"
__Comment__ = "..."
__Author__ = "Daniel Pose"
__Version__ = "0.0.4"
__Date__ = "2022-09-04"
__License__ = "MIT"
__Web__ = "https://github.com/iinjdpa/TreeHelper"
__Icon__ = "treeHelper/treeHelper.svg"
__Files__ = "/treeHelper/ui_treewindow.py,/treeHelper/treeHelper.svg"
...
from treeHelper import ui_treewindow     # plain import, works via §1.3
```

So the endorsed multi-file recipe is: metadata header declaring `__Files__`,
companion files in a same-named subfolder, plain imports. The Addon Manager
installs the declared files alongside the macro.

### 2.2 Strong single-file bias for distribution

- **Macro Animator** (TheMarkster, widely-used animation macro): shipped as
  `Animator.FCMacro` + `Animator.py`; v0.2026.09.06 changelog: *"Remove file
  creation and just put everything into a single Animator.py file (no more
  Animator.FCMacro + Animator.py)"*; the wiki install was switched to the
  single `.py`.
- **3D Plywood Slicer** (sedat_kuran, 2026): *"The macro is a single
  `.FCMacro` file. Just save it in your FreeCAD [Macro folder]"* — marketed
  as a feature.
- **TheMarkster** (PySideUic.loadUi thread, 2026): embeds the whole UI
  definition *as a string inside the macro* specifically *"to be able to
  distribute the macro on the wiki in a single macro file"*.
- **chennes** (AddOn-repository thread, 2023): *"Some of my macros create a
  .py file from text embedded behind comments in the .FCMacro file"* —
  runtime extraction of embedded companion code is an established pattern.
- **TheMarkster** (Aug 2024, "Macro invoking a Macro"): *"If these are .py
  files they can be imported easily, but not if they are .FCMacro files. In
  retrospect, .FCMacro should never have been a thing."*

Pattern: authors develop however they like, but **collapse to one file for
distribution** because recipients copy a single file into the Macro folder.

### 2.3 Nothing forbids our current layout

Two files in the same folder is functionally fine (proven: smoke test
scenario A loads the companion via `importlib` from the macro's own
directory). The only real costs are (a) the extra entry in the macro list
and (b) two files to copy on install.

## 3. Options assessed

| Option | Selector pollution | Install friction | Testability | Distribution | Verdict |
|--------|--------------------|------------------|-------------|--------------|---------|
| **(a) Keep two files** (status quo) | One extra entry (`varset_usage_core.py`), listed recursively wherever it sits | Copy 2 files | Best: core is a real importable module, unit-tested directly | Fine for personal use; awkward for sharing | Zero-risk; acceptable if the extra entry bothers you not at all |
| **(b) Single `.FCMacro`, core embedded** (chennes/TheMarkster pattern) | None — one entry | Copy 1 file | Core tested by extracting the embedded block (small harness) or by keeping the dev copy in the repo | Matches dominant community practice; wiki-friendly | Best UX; modest build/extract machinery |
| **(c) Core as a proper package** (site-packages / `Mod` folder) | None | Extra install step; version-drift risk between macro and core | Best | Overkill for a personal utility | Reject |
| **(d) Two-file dev + generated single-file distro** | None (distro file) | Copy 1 file | Best (real module in repo) | Best of both worlds | Most moving parts; justified only if you plan to publish |

## 4. Recommendation

For a **personal** tool installed by copying files into the Macro folder:

1. **Short term: keep (a).** Everything works; the sole defect is one extra
   grey entry in the macro list. If that entry annoys you, the cheapest
   mitigation is renaming the companion so its purpose is obvious at a glance
   (e.g. `zzz_varset_usage_core_helper.py` sorts last; it is inert when run).
2. **If you ever share it (wiki/GitHub): switch to (b)** — embed the core in
   the `.FCMacro` behind a marker comment, extract-and-load at startup
   (falling back to a sibling file for development/testing), and adopt the
   official metadata header (`__Name__`, `__Version__`, `__License__`, …) so
   it also installs cleanly through the Addon Manager. The dev repo keeps the
   standalone `varset_usage_core.py` so the 43 unit tests stay untouched.

No structural change is made until the user picks.

## 5. Sources

- FreeCAD `main` @ `157bfcb`: `src/Gui/Dialogs/DlgMacroExecuteImp.cpp`
  (`filterFiles`, `fillUpList`), `src/Base/Interpreter.cpp` (`runFile`),
  `src/App/FreeCADInit.py` (`register_macro_sources`),
  `src/Gui/EditorView.cpp` (save filters).
- FreeCAD wiki: *Macros* (extension convention), *How to install macros*.
- `github.com/FreeCAD/FreeCAD-macros`: root listing (mixed `.FCMacro`/`.py`),
  `Utility/treeHelper.FCMacro` + `Utility/treeHelper/` (official multi-file
  pattern with `__Files__`).
- forum.freecad.org: *Macro Animator v.0.2023.09.30c* (single-file
  consolidation), *Macro invoking a Macro* (.py importability opinion),
  *How to publish a macro in the AddOn repository* (embedded-text pattern),
  *Passing optional QWidget parameter to PySideUic.loadUi* (UI-as-string),
  *3D Plywood Slicer* announcement (single-file marketing).
