"""Probe v4: is the old-name cross-doc link in the user's REAL files alive or
merely masked by stale values? IN-MEMORY ONLY -- opens the real files,
mutates values in RAM, recomputes, observes, and NEVER SAVES. Disk files are
byte-for-byte untouched. Self-reports to PROBE_LIVELINK.txt.

Test A (negative): raise Master_File.VarSet.WallThickness 5 -> 6 mm and
      recompute Dependent_File. If the old-name binding
      FanMount_File#VarSet.WallThickness is alive, Pad.Length
      becomes 6 mm. If dead, it stays 5 mm.
Test B (positive control): bind a NEW in-memory property to the CURRENT name
      Master_File#VarSet.WallThickness * 2 and recompute. Expect 12 mm.
"""
import time
import traceback

HERE = __file__.replace("\\", "/")
OUT = HERE.rsplit("/", 1)[0] + "/PROBE_LIVELINK.txt"
lines = []


def log(msg=""):
    lines.append(str(msg))
    print(msg)


def flush():
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


import FreeCAD as App

log("FreeCAD {}".format(App.Version()[0]))
# Point these at two documents of your own (master + dependent) linked by a
# cross-document expression; the internal document names must match.
REAL_DIR = r"<YOUR_PROJECT_DIR>"
RM_DOC = "Master_File"
VT_DOC = "Dependent_File"
rm_path = REAL_DIR + "/" + RM_DOC + ".FCStd"
vt_path = REAL_DIR + "/" + VT_DOC + ".FCStd"

try:
    t0 = time.time()
    App.openDocument(rm_path)
    App.openDocument(vt_path)
    log("opened both real files in {:.1f}s".format(time.time() - t0))
    log("documents: " + repr(sorted(App.listDocuments())))

    rm = App.getDocument(RM_DOC)
    vt = App.getDocument(VT_DOC)
    vs = rm.getObject("VarSet")
    pad = vt.getObject("Pad")
    log("baseline: WallThickness = " + repr(vs.WallThickness))
    log("baseline: Pad.Length = " + repr(pad.Length)
        + "  State = " + repr(pad.State))
    log("baseline: Pad.ExpressionEngine = " + repr(pad.ExpressionEngine))

    # ---- Test A: mutate the master variable, recompute the dependent ------
    log("")
    log("--- TEST A: WallThickness 5 -> 6 (in memory only) ---")
    vs.WallThickness = 6
    t0 = time.time()
    vt.recompute()
    log("recompute took {:.1f}s".format(time.time() - t0))
    log("AFTER: Pad.Length = " + repr(pad.Length)
        + "  State = " + repr(pad.State))
    log("AFTER: WallThickness = " + repr(vs.WallThickness))
    verdict_a = ("ALIVE (followed to 6)"
                 if abs(float(pad.Length.Value) - 6.0) < 1e-6
                 else "DEAD (stayed at " + str(pad.Length) + ")")
    log("TEST A verdict: " + verdict_a)

    # ---- Test B: fresh binding using the CURRENT document name ------------
    log("")
    log("--- TEST B: new in-memory binding to current name ---")
    probe = vt.addObject("App::FeaturePython", "LiveProbe")
    probe.addProperty("App::PropertyDistance", "Len", "Base", "")
    # VT was opened from disk, so it counts as a saved owner document --
    # cross-doc expressions are legal without us writing anything.
    probe.setExpression("Len", RM_DOC + "#VarSet.WallThickness * 2")
    vt.recompute()
    log("B: LiveProbe.Len = " + repr(probe.Len)
        + "  (expected 12 mm if current-name refs propagate)")
    log("B: LiveProbe.ExpressionEngine = " + repr(probe.ExpressionEngine))
    vt.removeObject(probe.Name)

    log("")
    log("NOTE: nothing was saved; closing documents now.")
except Exception:
    log("FATAL:\n" + traceback.format_exc())
finally:
    for nm in list(App.listDocuments()):
        try:
            App.closeDocument(nm)
        except Exception:
            pass
flush()
