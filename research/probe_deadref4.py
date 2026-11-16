# -*- coding: utf-8 -*-
"""Pin down WHY cross-doc refs to a VarSet property fail to parse.

Setup mirrors probe_deadref3 (disk round-trip), then:
  E1. dump PropertiesList of the reopened VarSet and FP source
      (did the custom property survive the save?)
  E2. bind WITHOUT any proxy on the consumer (livelink shape)
  E3. bind using the <<Label>> form: DiskMaster#<<Vars>>.W
  E4. local (same-doc) ref to the VarSet prop -- control
  E5. cross-doc ref to the VarSet prop AFTER touching/recomputing master

Run: freecadcmd.exe research/probe_deadref4.py
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


tmpdir = tempfile.mkdtemp(prefix="fc_dr4_")
log("tmpdir:", tmpdir)

m = App.newDocument("DiskMaster")
vs = m.addObject("App::VarSet", "Vars")
vs.addProperty("App::PropertyLength", "W", "Base", "")
vs.W = 4.0
fp_src = m.addObject("App::FeaturePython", "Src")
fp_src.Proxy = Proxy(fp_src)
fp_src.Len = 9.0
m.recompute()
m.saveAs(os.path.join(tmpdir, "DiskMaster.FCStd"))

c = App.newDocument("DiskDep")
p = c.addObject("App::FeaturePython", "DP")
p.Proxy = Proxy(p)
c.recompute()
c.saveAs(os.path.join(tmpdir, "DiskDep.FCStd"))

App.closeDocument(c.Name)
App.closeDocument(m.Name)

m2 = App.openDocument(os.path.join(tmpdir, "DiskMaster.FCStd"))
c2 = App.openDocument(os.path.join(tmpdir, "DiskDep.FCStd"))
vs2 = m2.getObject("Vars")
src2 = m2.getObject("Src")
dp = c2.getObject("DP")

log("E1: reopened Vars.PropertiesList =", repr(vs2.PropertiesList))
log("E1: reopened Src.PropertiesList   =", repr(src2.PropertiesList))
try:
    log("E1: Vars.W =", float(vs2.W.Value))
except Exception as exc:
    log("E1: Vars.W unreadable:", exc)

# E2: consumer WITHOUT proxy ---------------------------------------------
np_ = c2.addObject("App::FeaturePython", "NoProxy")
np_.addProperty("App::PropertyDistance", "Len", "Base", "")
try:
    np_.setExpression("Len", "DiskMaster#Vars.W * 2")
    log("E2: no-proxy consumer ACCEPTED, engine =", np_.ExpressionEngine)
except Exception as exc:
    log("E2: no-proxy consumer RAISED {}: {}".format(
        type(exc).__name__, exc))

# E3: label form -----------------------------------------------------------
try:
    dp.setExpression("Len", "DiskMaster#<<Vars>>.W * 2")
    log("E3: <<Label>> form ACCEPTED, engine =", dp.ExpressionEngine)
except Exception as exc:
    log("E3: <<Label>> form RAISED {}: {}".format(type(exc).__name__, exc))

# E4: local same-doc control ------------------------------------------------
lp = c2.addObject("App::FeaturePython", "LocalCtl")
lp.Proxy = Proxy(lp)
lv = c2.addObject("App::VarSet", "LocalVars")
lv.addProperty("App::PropertyLength", "W", "Base", "")
lv.W = 3.0
try:
    lp.setExpression("Len", "LocalVars.W * 2")
    log("E4: local VarSet ref ACCEPTED, engine =", lp.ExpressionEngine)
except Exception as exc:
    log("E4: local VarSet ref RAISED {}: {}".format(
        type(exc).__name__, exc))
c2.recompute()
try:
    log("E4: LocalCtl.Len =", float(lp.Len.Value), "(expect 6.0)")
except Exception as exc:
    log("E4: LocalCtl.Len unreadable:", exc)

# E5: touch + recompute master, retry cross-doc ------------------------------
vs2.touch()
m2.recompute()
try:
    dp.setExpression("Len", "DiskMaster#Vars.W * 2")
    log("E5: post-touch cross-doc ACCEPTED, engine =", dp.ExpressionEngine)
except Exception as exc:
    log("E5: post-touch cross-doc RAISED {}: {}".format(
        type(exc).__name__, exc))

for name in list(App.listDocuments()):
    try:
        App.closeDocument(name)
    except Exception:
        pass
shutil.rmtree(tmpdir, ignore_errors=True)

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "PROBE_DEADREF4.txt"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(OUT) + "\n")
