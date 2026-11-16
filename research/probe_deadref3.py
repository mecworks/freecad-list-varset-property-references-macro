# -*- coding: utf-8 -*-
"""Follow-up: does a cross-doc reference to a VarSet property parse when the
documents were OPENED FROM DISK (rather than created in memory + saveAs)?

Sequence:
  S1. create master (VarSet W) + consumer (FP Len) in memory, saveAs both
  S2. close both
  S3. reopen both from disk via App.openDocument
  S4. setExpression(consumer -> 'DiskMaster#Vars.W * 2')
  S5. recompute, read value
Also controls:
  C1. same but referencing the FP property of the master doc
  C2. fresh in-memory docs again AFTER the disk-opened ones exist
      (rules out session-order effects)

Run: freecadcmd.exe research/probe_deadref3.py
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


tmpdir = tempfile.mkdtemp(prefix="fc_dr3_")
log("tmpdir:", tmpdir)

# S1 --------------------------------------------------------------------------
m = App.newDocument("DiskMaster")
vs = m.addObject("App::VarSet", "Vars")
vs.addProperty("App::PropertyLength", "W", "Base", "")
vs.W = 4.0
fp_src = m.addObject("App::FeaturePython", "Src")
fp_src.Proxy = Proxy(fp_src)
fp_src.Len = 9.0
m.saveAs(os.path.join(tmpdir, "DiskMaster.FCStd"))

c = App.newDocument("DiskDep")
p = c.addObject("App::FeaturePython", "DP")
p.Proxy = Proxy(p)
c.saveAs(os.path.join(tmpdir, "DiskDep.FCStd"))

App.closeDocument(c.Name)
App.closeDocument(m.Name)

# S3 --------------------------------------------------------------------------
m2 = App.openDocument(os.path.join(tmpdir, "DiskMaster.FCStd"))
c2 = App.openDocument(os.path.join(tmpdir, "DiskDep.FCStd"))
p = c2.getObject("DP")  # fresh handle; the in-memory one died with close
log("S3: reopened names:", repr(sorted(App.listDocuments())))

# S4 --------------------------------------------------------------------------
try:
    p.setExpression("Len", "DiskMaster#Vars.W * 2")
    log("S4: VarSet-target bind ACCEPTED, engine =", p.ExpressionEngine)
except Exception as exc:
    log("S4: VarSet-target bind RAISED {}: {}".format(
        type(exc).__name__, exc))
c2.recompute()
try:
    log("S5: DP.Len =", float(p.Len.Value), "(expect 8.0)")
except Exception as exc:
    log("S5: DP.Len unreadable:", exc)

# C1 --------------------------------------------------------------------------
try:
    p.setExpression("Len", "DiskMaster#Src.Len * 2")
    log("C1: FP-target bind ACCEPTED, engine =", p.ExpressionEngine)
except Exception as exc:
    log("C1: FP-target bind RAISED {}: {}".format(
        type(exc).__name__, exc))
c2.recompute()
try:
    log("C1: DP.Len =", float(p.Len.Value), "(expect 18.0)")
except Exception as exc:
    log("C1: DP.Len unreadable:", exc)

# C2 --------------------------------------------------------------------------
m3 = App.newDocument("FreshMaster")
vs3 = m3.addObject("App::VarSet", "Vars")
vs3.addProperty("App::PropertyLength", "W", "Base", "")
vs3.W = 4.0
m3.saveAs(os.path.join(tmpdir, "FreshMaster.FCStd"))
c3 = App.newDocument("FreshDep")
p3 = c3.addObject("App::FeaturePython", "DP")
p3.Proxy = Proxy(p3)
c3.saveAs(os.path.join(tmpdir, "FreshDep.FCStd"))
try:
    p3.setExpression("Len", "FreshMaster#Vars.W * 2")
    log("C2: in-memory-after-disk VarSet bind ACCEPTED")
except Exception as exc:
    log("C2: in-memory-after-disk VarSet bind RAISED {}: {}".format(
        type(exc).__name__, exc))

for name in list(App.listDocuments()):
    try:
        App.closeDocument(name)
    except Exception:
        pass
shutil.rmtree(tmpdir, ignore_errors=True)

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "PROBE_DEADREF3.txt"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(OUT) + "\n")
