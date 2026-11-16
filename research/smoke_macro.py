"""Headless smoke test of the development copy
(ListVarSetPropertyReferences_dev.FCMacro).

Scenarios (self-reported to SMOKE_RESULTS.txt; freecadcmd swallows stdout):
  A. Normal load: companion present next to the macro.
     - core loads via importlib, NO sys.path mutation, no SystemExit.
  B. Companion missing: graceful degradation (core=None, one error dialog,
     main() is a safe no-op) -- no SystemExit, no traceback.
  C. Full dialog flow under offscreen Qt: populate combos, fire slots,
     verify the report excludes the superset-named decoy AND includes a
     cross-document usage (DocName#Object.Property) with a [doc] prefix,
     and that unchecking "Include other open documents" drops it.
"""
import os
import sys
import tempfile
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     ".."))
MACRO = os.path.join(ROOT, "src", "ListVarSetPropertyReferences_dev.FCMacro")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "SMOKE_RESULTS.txt")
lines = []


def log(msg=""):
    lines.append(str(msg))
    print(msg)


def flush():
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


SRC = open(MACRO, encoding="utf-8").read()
PATH_BEFORE = list(sys.path)

# --------------------------------------------------------------------------
# A. Normal load
# --------------------------------------------------------------------------
ns = {"__file__": MACRO, "__name__": "smoke_a"}
try:
    exec(compile(SRC, MACRO, "exec"), ns)
    log("A: module-level exec clean (no SystemExit): True")
except BaseException as exc:
    log("A: module-level exec RAISED: {!r}".format(exc))
    flush()
    raise SystemExit(1)

log("A: core loaded: {}".format(ns.get("core") is not None))
log("A: sys.path unchanged: {}".format(list(sys.path) == PATH_BEFORE))
log("A: core.usage_pattern callable: {}".format(
    callable(getattr(ns.get("core"), "usage_pattern", None))))

# --------------------------------------------------------------------------
# B. Companion missing -> graceful degradation
# --------------------------------------------------------------------------
tmpdir = tempfile.mkdtemp(prefix="fc_smoke_")
fake_macro = os.path.join(tmpdir, "FakeMacro.FCMacro")
with open(fake_macro, "w", encoding="utf-8") as fh:
    fh.write(SRC)

import PySide6
calls = []


class _StubMsgBox:
    @staticmethod
    def critical(*args, **kwargs):
        calls.append(args)
        return 0


_stub = types.ModuleType("PySide6.QtWidgets_stub")
_stub.QMessageBox = _StubMsgBox
# Minimal stand-in so the macro's module-level class definition can run;
# the real PySide6 always provides it.
_stub.QDialog = type("QDialog", (), {})
_saved = getattr(PySide6, "QtWidgets", None)
try:
    PySide6.QtWidgets = _stub
    ns2 = {"__file__": fake_macro, "__name__": "smoke_b"}
    try:
        exec(compile(SRC, fake_macro, "exec"), ns2)
        log("B: module-level exec clean (no SystemExit): True")
    except BaseException as exc:
        log("B: module-level exec RAISED: {!r}".format(exc))
    log("B: core is None: {}".format(ns2.get("core") is None))
    log("B: exactly one error dialog shown: {}".format(len(calls) == 1))
    if calls:
        msg = str(calls[0][-1])
        log("B: message names the companion: {}".format(
            "varset_usage_core" in msg))
    try:
        ns2["main"]()
        log("B: main() safe no-op: True")
    except Exception as exc:
        log("B: main() RAISED: {!r}".format(exc))
finally:
    PySide6.QtWidgets = _saved

# --------------------------------------------------------------------------
# C. Full dialog flow (offscreen Qt), incl. cross-document scan
# --------------------------------------------------------------------------
from PySide6 import QtGui
from PySide6 import QtWidgets as QTW
qapp = QTW.QApplication.instance() or QTW.QApplication(["smoke"])

import FreeCAD as App
c_tmp = tempfile.mkdtemp(prefix="fc_smoke_c_")
doc = App.newDocument("SmokeDoc")
vs = doc.addObject("App::VarSet", "Dims")
vs.addProperty("App::PropertyLength", "Width", "Base", "")
vs.Width = 10


class _P:
    def __init__(self, obj):
        obj.addProperty("App::PropertyDistance", "Len", "Base", "")


pad = doc.addObject("App::FeaturePython", "Pad")
pad.Proxy = _P(pad)
pad.setExpression("Len", "Dims.Width * 2")

super_pad = doc.addObject("App::FeaturePython", "SuperDims")
super_pad.Proxy = _P(super_pad)
super_pad.addProperty("App::PropertyLength", "Width", "Base", "")
super_pad.setExpression("Len", "SuperDims.Width * 3")

doc.saveAs(os.path.join(c_tmp, "SmokeDoc.FCStd"))

# Second open document referencing the home VarSet across files.
doc2 = App.newDocument("SmokeVent")
vpart = doc2.addObject("App::FeaturePython", "VP")
vpart.Proxy = _P(vpart)
doc2.saveAs(os.path.join(c_tmp, "SmokeVent.FCStd"))
vpart.setExpression("Len", "SmokeDoc#Dims.Width * 3")
doc2.recompute()
log("C: cross-doc value = {!r} (expected 30 mm)".format(vpart.Len))

try:
    dlg = ns["UsageDialog"](doc)
    log("C: dialog constructed: True")
    log("C: varset entries: {} / userData={}".format(
        [dlg.varset_combo.itemText(i)
         for i in range(dlg.varset_combo.count())],
        dlg.varset_combo.currentData()))
    log("C: scan-all checkbox present & checked: {}".format(
        hasattr(dlg, "scan_all_cb") and dlg.scan_all_cb.isChecked()))
    dlg._on_varset_changed(0)
    props = [dlg.property_combo.itemText(i)
             for i in range(dlg.property_combo.count())]
    log("C: property items: {}".format(props))
    dlg._on_property_changed(0)
    text = dlg.results.toPlainText()
    log("C: results text (all docs): {!r}".format(text))
    log("C: local usage unprefixed: {}".format("Pad.Len =" in text))
    log("C: foreign usage prefixed: {}".format("[SmokeVent] VP.Len" in text))
    log("C: superset decoy excluded: {}".format("SuperDims" not in text))
    dlg.scan_all_cb.setChecked(False)
    dlg._on_property_changed(0)
    text = dlg.results.toPlainText()
    log("C: unchecked -> local only: {}".format(
        "SmokeVent" not in text and "Pad.Len" in text))
    log("C: monospace style hint applied: {}".format(
        dlg.results.font().styleHint() == QtGui.QFont.StyleHint.Monospace))
    dlg.close()
except Exception as exc:
    import traceback
    log("C: dialog flow RAISED: {!r}\n{}".format(exc, traceback.format_exc()))
finally:
    App.closeDocument(doc2.Name)
    App.closeDocument(doc.Name)

flush()
