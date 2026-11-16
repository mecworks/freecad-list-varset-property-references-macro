"""Probe: cross-document references via DocName#Object.Property (user-reported
syntax). Reproduces the exact scenario: working in Dependent_File,
referencing a VarSet property that lives in Master_File.

Self-reports to PROBE_XREF.txt after every section (freecadcmd swallows
stdout and may die mid-script).
"""
import os
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
OUT = os.path.join(HERE, "PROBE_XREF.txt")
lines = []


def log(msg=""):
    lines.append(str(msg))
    print(msg)


def flush():
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def section(title):
    log("")
    log("=== {} ===".format(title))
    flush()


import FreeCAD as App
import varset_usage_core_dev as core

log("FreeCAD {}".format(App.Version()[0]))


class P:
    def __init__(self, obj):
        obj.addProperty("App::PropertyDistance", "Len", "Base", "")


tmpdir = tempfile.mkdtemp(prefix="fc_xref_")

# --- Base file: Master_File ---------------------------------------------------
docA = App.newDocument("Master_File")
vs = docA.addObject("App::VarSet", "VarSet")
vs.addProperty("App::PropertyLength", "RackEarWidth", "Base", "")
vs.RackEarWidth = 5
docA.recompute()
docA.saveAs(os.path.join(tmpdir, "Master_File.FCStd"))
log("A: docA.Name={!r} docA.Label={!r}".format(docA.Name, docA.Label))
log("A: VarSet.Name={!r} VarSet.Label={!r}".format(vs.Name, vs.Label))

# --- Derived file: Dependent_File ----------------------------------------------
docB = App.newDocument("Dependent_File")
part = docB.addObject("App::FeaturePython", "Part")
part.Proxy = P(part)
docB.saveAs(os.path.join(tmpdir, "Dependent_File.FCStd"))

section("X1: user's exact syntax  Master_File#VarSet.RackEarWidth * 2")
try:
    part.setExpression("Len", "Master_File#VarSet.RackEarWidth * 2")
    log("X1: setExpression accepted: True")
    log("X1: Part.ExpressionEngine = {}".format(part.ExpressionEngine))
    docB.recompute()
    try:
        log("X1: Part.Len = {!r}  (expected 10 mm if resolved)".format(part.Len))
    except Exception as exc:
        log("X1: reading Part.Len raised: {!r}".format(exc))
except Exception as exc:
    log("X1: setExpression raised: {!r}".format(exc))

section("X2: label form  Master_File#<<Master Vars>>.RackEarWidth")
vs.Label = "Master Vars"
docA.recompute()
try:
    part.setExpression("Len", "Master_File#<<Master Vars>>.RackEarWidth * 3")
    log("X2: setExpression accepted: True")
    log("X2: Part.ExpressionEngine = {}".format(part.ExpressionEngine))
    docB.recompute()
    try:
        log("X2: Part.Len = {!r}  (expected 15 mm if resolved)".format(part.Len))
    except Exception as exc:
        log("X2: reading Part.Len raised: {!r}".format(exc))
except Exception as exc:
    log("X2: setExpression raised: {!r}".format(exc))

section("X3: macro impact -- pattern + per-document scans")
pat = core.usage_pattern(vs, "RackEarWidth")
xref_text = "Master_File#VarSet.RackEarWidth * 2"
log("X3: pattern.search(cross-ref text) = {}".format(bool(pat.search(xref_text))))
log("X3: find_usages(docA/home, ...) = {}".format(
    core.find_usages(docA, vs, "RackEarWidth")))
log("X3: find_usages(docB/foreign, ...) = {}".format(
    core.find_usages(docB, vs, "RackEarWidth")))

section("X4: close the base file, recompute derived")
try:
    App.closeDocument(docA.Name)
    docB.recompute()
    try:
        log("X4: Part.Len with base CLOSED = {!r}".format(part.Len))
    except Exception as exc:
        log("X4: reading Part.Len raised: {!r}".format(exc))
    log("X4: Part.ExpressionEngine still = {}".format(part.ExpressionEngine))
except Exception as exc:
    log("X4: raised: {!r}".format(exc))
    log(traceback.format_exc())

section("X5: reopen the base file, recompute derived")
try:
    docA = App.openDocument(os.path.join(tmpdir, "Master_File.FCStd"))
    docB.recompute()
    try:
        log("X5: Part.Len with base REOPENED = {!r}".format(part.Len))
    except Exception as exc:
        log("X5: reading Part.Len raised: {!r}".format(exc))
except Exception as exc:
    log("X5: raised: {!r}".format(exc))
    log(traceback.format_exc())

section("DONE")
flush()
