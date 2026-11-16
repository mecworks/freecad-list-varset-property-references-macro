"""Probe v3: App::Link case with the base file SAVED to disk (the realistic
workflow -- a link to an unsaved in-memory document is rejected by FreeCAD
itself, which is itself a finding worth recording).

Self-reports to PROBE_CROSSDOC_LINK.txt after every section.
"""
import os
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
OUT = os.path.join(HERE, "PROBE_CROSSDOC_LINK.txt")
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


# --- Base file, saved ----------------------------------------------------------
tmpdir = tempfile.mkdtemp(prefix="fc_xdoc_")
base_path = os.path.join(tmpdir, "Base.FCStd")

docA = App.newDocument("BaseFile")
dims = docA.addObject("App::VarSet", "Dims")
dims.addProperty("App::PropertyLength", "Width", "Base", "")
dims.Width = 10

holder = docA.addObject("App::FeaturePython", "Holder")
holder.Proxy = P(holder)
holder.setExpression("Len", "Dims.Width * 2")
docA.recompute()
docA.saveAs(base_path)
log("A: base file saved to {}".format(base_path))
log("A: Holder.Len = {}".format(holder.Len))

# --- Derived file ----------------------------------------------------------------
docB = App.newDocument("DerivedFile")
derived_path = os.path.join(tmpdir, "Derived.FCStd")
docB.saveAs(derived_path)
log("A2: derived file saved to {}".format(derived_path))

section("B4: App::Link to saved base-file object")
try:
    lnk = docB.addObject("App::Link", "LinkToHolder")
    lnk.LinkedObject = holder
    docB.recompute()
    try:
        log("B4: link.Len = {!r}".format(lnk.Len))
    except Exception as exc:
        log("B4: reading link.Len raised: {!r}".format(exc))
    try:
        log("B4: link.ExpressionEngine = {!r}".format(lnk.ExpressionEngine))
    except Exception as exc:
        log("B4: link.ExpressionEngine raised: {!r}".format(exc))
    log("B4: Link appears in docB.Objects: {}".format(
        any(o.Name == "LinkToHolder" for o in docB.Objects)))
    log("B4: Link TypeId = {}".format(getattr(lnk, "TypeId", "?")))
except Exception as exc:
    log("B4: link setup failed: {!r}".format(exc))
    log(traceback.format_exc())

section("C: what the macro reports")
log("C1: find_usages(docA, Dims, Width) = {}".format(
    core.find_usages(docA, dims, "Width")))
log("C2: find_usages(docB, Dims, Width) = {}".format(
    core.find_usages(docB, dims, "Width")))
log("C3: does the link's expression text appear anywhere in docB scan? "
    "{}".format(any("Holder" in p for p, _ in core.find_usages(docB, dims, "Width"))))

section("DONE")
flush()
