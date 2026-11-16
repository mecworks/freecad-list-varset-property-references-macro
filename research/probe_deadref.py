# -*- coding: utf-8 -*-
"""Probe: what happens when an expression references a document that is not
open (e.g. after its master file was renamed)?

Questions answered here:
  Q1. Does setExpression() accept a DocName#Obj.Prop expression whose
      DocName matches no open document? (raises / stores verbatim?)
  Q2. What does ExpressionEngine store for such a binding?
  Q3. What object state / value results (Touched/Invalid? stale number?)
  Q4. If we later OPEN a document with that exact name, does the binding
      come alive (i.e. is resolution purely by current open-doc name)?
  Q5. Case sensitivity: does 'othercase#...' resolve when the open doc's
      name differs only in case?

Run:  freecadcmd.exe research/probe_deadref.py > research/PROBE_DEADREF.txt
(stdout is swallowed by freecadcmd; redirect at the shell level)
"""
import os
import shutil
import tempfile

OUT = []


def log(*args):
    line = " ".join(str(a) for a in args)
    OUT.append(line)
    print(line)


tmpdir = tempfile.mkdtemp(prefix="fc_deadref_")
log("tmpdir:", tmpdir)

# --- Setup: a saved master doc with a VarSet -------------------------------
import FreeCAD as App

master = App.newDocument("MasterDoc")
vs = master.addObject("App::VarSet", "Vars")
vs.addProperty("App::PropertyLength", "W", "Base", "")
vs.W = 7.0
master.saveAs(os.path.join(tmpdir, "MasterDoc.FCStd"))

class Proxy:
    def __init__(self, obj):
        obj.addProperty("App::PropertyDistance", "Len", "Base", "")


# --- Consumer doc with a binding to a NON-EXISTENT doc name ---------------
cons = App.newDocument("ConsumerDoc")
part = cons.addObject("App::FeaturePython", "Part")
part.Proxy = Proxy(part)
cons.saveAs(os.path.join(tmpdir, "ConsumerDoc.FCStd"))

log("\n=== Q1/Q2: setExpression with missing doc name ===")
try:
    part.setExpression("Len", "GhostDoc#Vars.W * 2")
    log("setExpression: ACCEPTED (no exception)")
except Exception as exc:
    log("setExpression RAISED {}: {}".format(type(exc).__name__, exc))

log("ExpressionEngine:", part.ExpressionEngine)
cons.recompute()
try:
    val = float(part.Len.Value)
except Exception as exc:
    val = "<unreadable: {}>".format(exc)
log("state:", part.State, " Len =", val)

# --- Q4: open a doc named GhostDoc and see if the binding revives ---------
log("\n=== Q4: open a document named exactly 'GhostDoc' ===")
ghost = App.newDocument("GhostDoc")
gvs = ghost.addObject("App::VarSet", "Vars")
gvs.addProperty("App::PropertyLength", "W", "Base", "")
gvs.W = 99.0
ghost.saveAs(os.path.join(tmpdir, "GhostDoc.FCStd"))
cons.recompute()
try:
    val = float(part.Len.Value)
except Exception as exc:
    val = "<unreadable: {}>".format(exc)
log("after opening GhostDoc: state:", part.State, " Len =", val, "(expect 198.0 if revived)")

# --- Q5: case sensitivity --------------------------------------------------
log("\n=== Q5: case-insensitive doc name match ===")
upper = App.newDocument("GHOSTDOC2")
uvs = upper.addObject("App::VarSet", "Vars")
uvs.addProperty("App::PropertyLength", "W", "Base", "")
uvs.W = 55.0
upper.saveAs(os.path.join(tmpdir, "GHOSTDOC2.FCStd"))
part2 = cons.addObject("App::FeaturePython", "Part2")
part2.Proxy = Proxy(part2)
try:
    part2.setExpression("Len", "ghostdoc2#Vars.W")
    log("lowercase-name setExpression: ACCEPTED")
except Exception as exc:
    log("lowercase-name setExpression RAISED {}: {}".format(type(exc).__name__, exc))
cons.recompute()
try:
    val2 = float(part2.Len.Value)
except Exception as exc:
    val2 = "<unreadable: {}>".format(exc)
log("with GHOSTDOC2 open, expr 'ghostdoc2#Vars.W': state:", part2.State,
    " Len =", val2, "(expect 55.0 if case-insensitive)")

# --- cleanup ----------------------------------------------------------------
for d in ("ConsumerDoc", "GhostDoc", "GHOSTDOC2", "MasterDoc"):
    try:
        App.closeDocument(d)
    except Exception:
        pass
shutil.rmtree(tmpdir, ignore_errors=True)

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "PROBE_DEADREF.txt"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(OUT) + "\n")
