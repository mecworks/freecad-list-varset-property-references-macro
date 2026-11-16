"""Probe: cross-document VarSet references on FreeCAD 1.1.4 (v2, hardened).

Scenario: a VarSet lives in document A ("base file"); document B
("derived file") tries to use its variables. Answers:
  1. Can an expression in B reference a VarSet in A at all?
  2. Where does the expression TEXT live (which document's objects)?
  3. What does the macro's find_usages report for each document?

Self-reports to PROBE_CROSSDOC.txt after EVERY section (freecadcmd swallows
script stdout and may kill the process mid-script, so partial progress must
survive).
"""
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
OUT = os.path.join(HERE, "PROBE_CROSSDOC.txt")
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


# --- Base file ---------------------------------------------------------------
docA = App.newDocument("BaseFile")
dims = docA.addObject("App::VarSet", "Dims")
dims.addProperty("App::PropertyLength", "Width", "Base", "")
dims.Width = 10

holder = docA.addObject("App::FeaturePython", "Holder")
holder.Proxy = P(holder)
holder.setExpression("Len", "Dims.Width * 2")
docA.recompute()
log("A: Holder.Len (intra-doc control) = {}".format(holder.Len))

# --- Derived file --------------------------------------------------------------
docB = App.newDocument("DerivedFile")
part = docB.addObject("App::FeaturePython", "Part")
part.Proxy = P(part)

section("B1: cross-doc reference by internal name")
try:
    part.setExpression("Len", "Dims.Width * 2")
    log("B1: setExpression accepted: True")
    log("B1: Part.ExpressionEngine = {}".format(part.ExpressionEngine))
    docB.recompute()
    try:
        log("B1: Part.Len = {!r}".format(part.Len))
    except Exception as exc:
        log("B1: reading Part.Len raised: {!r}".format(exc))
except Exception as exc:
    log("B1: setExpression raised: {!r}".format(exc))

section("B2: cross-doc reference by label")
try:
    part.setExpression("Len", "<<Dims>>.Width * 3")
    log("B2: setExpression accepted: True")
    docB.recompute()
    try:
        log("B2: Part.Len = {!r}".format(part.Len))
    except Exception as exc:
        log("B2: reading Part.Len raised: {!r}".format(exc))
except Exception as exc:
    log("B2: setExpression raised: {!r}".format(exc))

section("B3: qualified attempts")
for cand in ("BaseFile.Dims.Width", "App.getDocument('BaseFile').Dims.Width"):
    try:
        part.setExpression("Len", cand)
        log("B3[{}]: accepted: True".format(cand))
    except Exception as exc:
        log("B3[{}]: raised: {!r}".format(cand, exc))
part.setExpression("Len", "1mm")

section("B4: App::Link to base-file object")
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
except Exception as exc:
    log("B4: link setup failed: {!r}".format(exc))
    log(traceback.format_exc())

section("C: what the macro reports")
log("C1: find_usages(docA, Dims, Width) = {}".format(
    core.find_usages(docA, dims, "Width")))
log("C2: find_usages(docB, Dims, Width) = {}".format(
    core.find_usages(docB, dims, "Width")))

dangler = docB.addObject("App::FeaturePython", "Dangler")
dangler.Proxy = P(dangler)
dangler.setExpression("Len", "Dims.Width * 5")
log("C3: dangler.ExpressionEngine = {}".format(dangler.ExpressionEngine))
log("C3: find_usages(docB, Dims, Width) after dangler = {}".format(
    core.find_usages(docB, dims, "Width")))

section("DONE")
flush()
