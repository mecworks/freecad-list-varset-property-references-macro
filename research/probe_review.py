"""Probe FreeCAD 1.1.4 for the APIs the review proposes to change.

Writes findings to PROBE_REVIEW.txt next to this file (freecadcmd swallows
script stdout, so self-reporting to a file is the reliable channel).
"""
import importlib.util
import os
import traceback

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "PROBE_REVIEW.txt")
lines = []


def log(msg=""):
    lines.append(str(msg))
    print(msg)


log("=== probe_review ===")

# --- 1. QFont replacement for deprecated setFixed(True) ---------------------
try:
    from PySide6 import QtGui
    f1 = QtGui.QFont()
    f1.setStyleHint(QtGui.QFont.StyleHint.Fixed)
    log("QFont.setStyleHint(StyleHint.Fixed): OK, styleHint={}".format(f1.styleHint()))
except Exception as exc:
    log("QFont.setStyleHint FAILED: {!r}".format(exc))

try:
    from PySide6 import QtGui
    f2 = QtGui.QFont()
    f2.setFamily(QtGui.QFont.Fixed)
    log("QFont.setFamily(QFont.Fixed): OK, family={!r}".format(f2.family()))
except Exception as exc:
    log("QFont.setFamily(QFont.Fixed) FAILED: {!r}".format(exc))

try:
    from PySide6 import QtGui
    f3 = QtGui.QFont()
    f3.setFixed(True)
    log("QFont.setFixed(True) still present: OK (deprecated-style)")
except Exception as exc:
    log("QFont.setFixed absent: {!r}".format(exc))

# --- 2. importlib.util.spec_from_file_location under FreeCAD python ---------
CORE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "..", "src", "varset_usage_core_dev.py"))
try:
    spec = importlib.util.spec_from_file_location("varset_usage_core_probe", CORE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    log("importlib load of varset_usage_core_dev: OK, has usage_pattern={} "
        "STANDARD_PROPERTIES={}".format(hasattr(mod, "usage_pattern"),
                                        sorted(mod.STANDARD_PROPERTIES)))
except Exception as exc:
    log("importlib load FAILED: {!r}".format(exc))
    log(traceback.format_exc())

# --- 3. Live baseline: bare App::VarSet PropertiesList ----------------------
import FreeCAD as App
doc = App.newDocument("ProbeReviewDoc")
try:
    bare = doc.addObject("App::VarSet", "BareProbe")
    plist = list(bare.PropertiesList)
    log("bare VarSet PropertiesList: {}".format(plist))
    try:
        spec2 = importlib.util.spec_from_file_location("core_cmp", CORE)
        cmp_mod = importlib.util.module_from_spec(spec2)
        spec2.loader.exec_module(cmp_mod)
        pinned = set(cmp_mod.STANDARD_PROPERTIES)
        log("matches pinned STANDARD_PROPERTIES: {}".format(set(plist) == pinned))
    except Exception as exc:
        log("compare failed: {!r}".format(exc))
finally:
    App.closeDocument(doc.Name)

with open(OUT, "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
