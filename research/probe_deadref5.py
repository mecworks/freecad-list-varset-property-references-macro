# -*- coding: utf-8 -*-
"""Probe 5: TRUE missing-document behavior, free of the 'W'-is-Watts lexer
collision discovered in Expression.l (unit literals outrank IDENTIFIER).

Property names here avoid ALL unit keywords (mm, m, W, V, A, N, s, ...).

P1: setExpression to a doc name that exists NOWHERE -> accepted?
P2: case sensitivity of cross-doc doc-name matching
P3: does a dead ref REVIVE if a doc with that exact name later opens?

Run: freecadcmd.exe research/probe_deadref5.py
"""
import os
import tempfile
import traceback

OUT = []


def log(*args):
    line = " ".join(str(a) for a in args)
    OUT.append(line)
    print(line)


class Proxy(object):
    def __init__(self, obj):
        obj.addProperty("App::PropertyLength", "Len", "Base", "")


try:
    import FreeCAD as App

    tmp = tempfile.mkdtemp(prefix="fc_deadref5_")
    log("tmpdir:", tmp)

    # ---------------- P1: direct ghost binding ----------------
    cons = App.newDocument("ConsA")
    ctl = cons.addObject("App::FeaturePython", "Ctl")
    ctl.Proxy = Proxy(ctl)
    try:
        ctl.setExpression("Len", "GhostDoc#Vars.Width * 2")
        log("P1: setExpression ACCEPTED (no exception)")
    except Exception as exc:
        log("P1: setExpression RAISED %r" % exc)
    log("P1: ExpressionEngine:", repr(list(ctl.ExpressionEngine)))
    cons.recompute()
    log("P1: state:", list(ctl.State), " Len =", ctl.Len.Value)

    # ---------------- P3: revives when GhostDoc opens? -------------
    gm = App.newDocument("GhostDoc")
    gv = gm.addObject("App::VarSet", "Vars")
    gv.addProperty("App::PropertyLength", "Width", "Base", "")
    gv.Width = 99.0
    gm.recompute()
    cons.recompute(None, True, True)
    log("P3: after opening GhostDoc: state:", list(ctl.State),
        " Len =", ctl.Len.Value, "(expect 198.0 if revived)")

    for nm in list(App.listDocuments()):
        App.closeDocument(nm)

    # ---------------- P2: case sensitivity ------------------------
    low = App.newDocument("ghostdoc2")
    lv = low.addObject("App::VarSet", "Vars")
    lv.addProperty("App::PropertyLength", "Width", "Base", "")
    lv.Width = 55.0
    low.recompute()

    cons2 = App.newDocument("ConsB")
    ctl2 = cons2.addObject("App::FeaturePython", "Ctl2")
    ctl2.Proxy = Proxy(ctl2)
    try:
        ctl2.setExpression("Len", "GHOSTDOC2#Vars.Width")
        log("P2: uppercase-name setExpression ACCEPTED")
    except Exception as exc:
        log("P2: uppercase-name setExpression RAISED %r" % exc)
    cons2.recompute(None, True, True)
    log("P2: with 'ghostdoc2' open, expr 'GHOSTDOC2#...': state:",
        list(ctl2.State), " Len =", ctl2.Len.Value,
        "(expect 55.0 if case-insensitive)")

    for nm in list(App.listDocuments()):
        App.closeDocument(nm)

except Exception:
    log("FATAL:\n" + traceback.format_exc())
finally:
    for nm in list(App.listDocuments()):
        try:
            App.closeDocument(nm)
        except Exception:
            pass
    try:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    except Exception:
        pass

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "PROBE_DEADREF5.txt"),
          "w", encoding="utf-8") as fh:
    fh.write("\n".join(OUT) + "\n")
