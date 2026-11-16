# -*- coding: utf-8 -*-
"""Minimal repro: cross-doc setExpression failing with ParserError although
the referenced document IS open. Isolates which factor breaks parsing.

Variants:
  V1. two fresh docs, both saveAs'd, then bind consumer->master (test shape)
  V2. same, but consumer NOT saved before binding
  V3. master doc name printed before/after saveAs (did saveAs rename it?)
  V4. bind BEFORE any saveAs (both in memory)
  V5. reference a FeaturePython prop instead of a VarSet prop

Run: freecadcmd.exe research/probe_deadref2.py
"""
import os
import shutil
import tempfile

import FreeCAD as App

OUT = []


def log(*args):
    line = " ".join(str(a) for a in args)
    OUT.append(line)
    print(line)


class Proxy:
    def __init__(self, obj):
        obj.addProperty("App::PropertyDistance", "Len", "Base", "")


tmpdir = tempfile.mkdtemp(prefix="fc_dr2_")
log("tmpdir:", tmpdir)


def try_bind(obj, prop, expr, tag):
    try:
        obj.setExpression(prop, expr)
        log(tag, ": ACCEPTED, engine =", obj.ExpressionEngine)
    except Exception as exc:
        log(tag, ": RAISED {}: {}".format(type(exc).__name__, exc))


# ---- V3/V1: the exact test shape ------------------------------------------
m1 = App.newDocument("DeadMaster")
vs1 = m1.addObject("App::VarSet", "Vars")
vs1.addProperty("App::PropertyLength", "W", "Base", "")
vs1.W = 4.0
log("V3: master doc name before saveAs:", repr(m1.Name))
m1.saveAs(os.path.join(tmpdir, "DeadMaster.FCStd"))
log("V3: master doc name after saveAs :", repr(m1.Name))

c1 = App.newDocument("DeadDep")
p1 = c1.addObject("App::FeaturePython", "DP")
p1.Proxy = Proxy(p1)
c1.saveAs(os.path.join(tmpdir, "DeadDep.FCStd"))
log("V3: consumer doc name after saveAs:", repr(c1.Name))
try_bind(p1, "Len", "DeadMaster#Vars.W * 2", "V1 (both saved)")

# ---- V4: bind before any save ---------------------------------------------
m2 = App.newDocument("MemMaster")
vs2 = m2.addObject("App::VarSet", "Vars")
vs2.addProperty("App::PropertyLength", "W", "Base", "")
vs2.W = 4.0
c2 = App.newDocument("MemDep")
p2 = c2.addObject("App::FeaturePython", "DP")
p2.Proxy = Proxy(p2)
try_bind(p2, "Len", "MemMaster#Vars.W * 2", "V4 (nothing saved)")

# ---- V2: consumer unsaved ---------------------------------------------------
m3 = App.newDocument("HalfMaster")
vs3 = m3.addObject("App::VarSet", "Vars")
vs3.addProperty("App::PropertyLength", "W", "Base", "")
vs3.W = 4.0
m3.saveAs(os.path.join(tmpdir, "HalfMaster.FCStd"))
c3 = App.newDocument("HalfDep")
p3 = c3.addObject("App::FeaturePython", "DP")
p3.Proxy = Proxy(p3)
try_bind(p3, "Len", "HalfMaster#Vars.W * 2", "V2 (consumer unsaved)")

# ---- V5: FeaturePython target property --------------------------------------
m4 = App.newDocument("FPMaster")
fp = m4.addObject("App::FeaturePython", "Src")
fp.Proxy = Proxy(fp)
fp.Len = 4.0
m4.saveAs(os.path.join(tmpdir, "FPMaster.FCStd"))
c4 = App.newDocument("FPDep")
p4 = c4.addObject("App::FeaturePython", "DP")
p4.Proxy = Proxy(p4)
c4.saveAs(os.path.join(tmpdir, "FPDep.FCStd"))
try_bind(p4, "Len", "FPMaster#Src.Len * 2", "V5 (FP->FP)")

for name in list(App.listDocuments()):
    try:
        App.closeDocument(name)
    except Exception:
        pass
shutil.rmtree(tmpdir, ignore_errors=True)

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "PROBE_DEADREF2.txt"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(OUT) + "\n")
