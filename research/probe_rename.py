"""Probe v3: how does FreeCAD 1.1.4 resolve DocName#Obj.Property references
after the referenced file has been RENAMED on disk? Controlled experiment in
a temp dir PLUS an optional read-only measurement of your own real files.
Self-reports to PROBE_RENAME.txt (freecadcmd swallows stdout).

Scenario matrix:
  S1: build Master (Vars.X=7) + Dep (P.Len = Master#Vars.X * 3);
      expression set BEFORE saving; verify 21 mm; close all.
  S2: rename Master.FCStd -> Renamed.FCStd on disk, open ONLY Dep.
      Value + validity: does a dead ref keep its last value or zero out?
  S3: open the renamed master normally (doc name 'Renamed'), recompute Dep.
      Do old-name refs resolve against a doc whose name no longer matches?
  S4: diagnostic: enumerate open/read-like APIs; attempt to load the
      renamed file under the OLD document name (simulated GUI locate).
  S5: control: restore original name, open Dep + Master normally.
  S6: READ-ONLY on your own real files (skipped when absent): open the
      master + dependent pair, inspect the Pad driven by the old-name reference.
      NOTHING IS EVER SAVED.
"""
import os
import tempfile
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "PROBE_RENAME.txt")
lines = []


def log(msg=""):
    lines.append(str(msg))
    print(msg)


def flush():
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def sec(title):
    log("")
    log("=== {} ===".format(title))
    flush()


import FreeCAD as App

log("FreeCAD {}".format(App.Version()[0]))


class P:
    def __init__(self, obj):
        obj.addProperty("App::PropertyDistance", "Len", "Base", "")


tmp = tempfile.mkdtemp(prefix="fc_rename_")
mpath = os.path.join(tmp, "Master.FCStd")
rpath = os.path.join(tmp, "Renamed.FCStd")
dpath = os.path.join(tmp, "Dep.FCStd")


def describe(tag):
    docs = sorted(App.listDocuments())
    log(tag + ": open documents = " + repr(docs))
    for nm in docs:
        dd = App.getDocument(nm)
        vv = dd.getObject("Vars")
        if vv is not None:
            log(tag + ": doc " + repr(nm) + ": Vars.X = " + repr(vv.X))
    dd = App.getDocument("Dep")
    po = dd.getObject("P")
    log(tag + ": Dep.P.Len = " + repr(po.Len))
    log(tag + ": Dep.P.State = " + repr(po.State))
    try:
        ee = po.ExpressionEngine
    except Exception as exc:
        ee = "<access failed: {!r}>".format(exc)
    log(tag + ": Dep.P.ExpressionEngine = " + repr(ee))


def close_all():
    for nm in list(App.listDocuments()):
        try:
            App.closeDocument(nm)
        except Exception:
            pass


def main():
    # ------------------------------------------------------------------ S1
    sec("S1: build + save + verify baseline (expression set BEFORE save)")
    m = App.newDocument("Master")
    vs = m.addObject("App::VarSet", "Vars")
    vs.addProperty("App::PropertyLength", "X", "Base", "")
    vs.X = 7
    m.recompute()
    m.saveAs(mpath)
    d = App.newDocument("Dep")
    p = d.addObject("App::FeaturePython", "P")
    p.Proxy = P(p)
    d.saveAs(dpath)                      # owner doc must be saved first
    p.setExpression("Len", "Master#Vars.X * 3")
    d.recompute()
    d.save()                             # <-- NOW the binding is persisted
    describe("S1")
    log("S1: expecting P.Len == 21 mm")
    close_all()
    flush()

    # ------------------------------------------------------------------ S2
    sec("S2: rename master on disk, then open ONLY Dep")
    os.rename(mpath, rpath)
    log("S2: renamed Master.FCStd -> Renamed.FCStd")
    try:
        App.openDocument(dpath)
    except Exception as exc:
        log("S2: openDocument raised: {!r}".format(exc))
    describe("S2")
    try:
        App.getDocument("Dep").recompute()
        describe("S2-post-recompute")
    except Exception as exc:
        log("S2: recompute raised: {!r}".format(exc))
    flush()

    # ------------------------------------------------------------------ S3
    sec("S3: open renamed master normally (doc name 'Renamed'), recompute Dep")
    try:
        App.openDocument(rpath)
    except Exception as exc:
        log("S3: openDocument raised: {!r}".format(exc))
    describe("S3-pre")
    try:
        App.getDocument("Dep").recompute()
        describe("S3-post-recompute")
    except Exception as exc:
        log("S3: recompute raised: {!r}".format(exc))
    flush()

    # ------------------------------------------------------------------ S4
    sec("S4: try to load renamed file UNDER THE OLD NAME")
    close_all()
    try:
        App.openDocument(dpath)
    except Exception as exc:
        log("S4: openDocument(Dep) raised: {!r}".format(exc))
    app_attrs = [a for a in dir(App)
                 if any(k in a.lower() for k in ("open", "read", "load"))]
    log("S4: App attrs (open/read/load): " + repr(app_attrs))
    dummy = App.getDocument("Dep")
    doc_attrs = [a for a in dir(dummy)
                 if any(k in a.lower() for k in ("read", "open", "load"))]
    log("S4: Document attrs (read/open/load): " + repr(doc_attrs))
    loaded_old_name = False
    for cand in ("read", "readFile", "open", "load"):
        fn = getattr(App.getDocument("Dep"), cand, None)
        if callable(fn):
            g = App.newDocument("Master")
            try:
                fn = getattr(g, cand)
                fn(rpath)
                log("S4: Document.{}() succeeded".format(cand))
                loaded_old_name = True
                break
            except Exception as exc:
                log("S4: Document.{} raised {!r}".format(cand, exc))
                try:
                    App.closeDocument("Master")
                except Exception:
                    pass
    if loaded_old_name:
        describe("S4-pre")
        try:
            App.getDocument("Dep").recompute()
            describe("S4-post-recompute")
        except Exception as exc:
            log("S4: recompute raised: {!r}".format(exc))
    else:
        log("S4: no API found to load a file under a chosen document name")
    flush()

    # ------------------------------------------------------------------ S5
    sec("S5: control -- restore original name, open Dep + Master normally")
    close_all()
    os.rename(rpath, mpath)
    log("S5: restored Master.FCStd")
    try:
        App.openDocument(dpath)
        App.openDocument(mpath)
    except Exception as exc:
        log("S5: open raised: {!r}".format(exc))
    describe("S5-pre")
    try:
        App.getDocument("Dep").recompute()
        describe("S5-post-recompute")
    except Exception as exc:
        log("S5: recompute raised: {!r}".format(exc))
    flush()

    # ------------------------------------------------------------------ S6
    sec("S6: READ-ONLY on your own real files (nothing is saved)")
    # Point these at two documents of your own (master + dependent) linked
    # by a cross-document expression; S6 is skipped when they are absent.
    real_dir = r"<YOUR_PROJECT_DIR>"
    rm_doc = "Master_File"
    vt_doc = "Dependent_File"
    rm_path = os.path.join(real_dir, rm_doc + ".FCStd")
    vt_path = os.path.join(real_dir, vt_doc + ".FCStd")
    if not (os.path.isfile(rm_path) and os.path.isfile(vt_path)):
        log("S6: SKIPPED -- set real_dir to your own project folder first")
        sec("DONE")
        flush()
        return
    close_all()
    t0 = time.time()
    try:
        App.openDocument(rm_path)
        log("S6: opened master in {:.1f}s".format(time.time() - t0))
        App.openDocument(vt_path)
        log("S6: opened dependent in {:.1f}s total".format(time.time() - t0))
    except Exception as exc:
        log("S6: open raised: {!r}".format(exc))
    log("S6: open documents = " + repr(sorted(App.listDocuments())))
    vt = App.getDocument(vt_doc)
    pad = vt.getObject("Pad")
    if pad is not None:
        log("S6: Pad.Length = " + repr(pad.Length))
        log("S6: Pad.State = " + repr(pad.State))
        try:
            log("S6: Pad.ExpressionEngine = " + repr(pad.ExpressionEngine))
        except Exception as exc:
            log("S6: ExpressionEngine access raised {!r}".format(exc))
    rm = App.getDocument(rm_doc)
    vsr = rm.getObject("VarSet")
    if vsr is not None:
        log("S6: {} VarSet.RackEarWidth = ".format(rm_doc)
            + repr(vsr.RackEarWidth))
        log("S6: {} VarSet.WallThickness = ".format(rm_doc)
            + repr(vsr.WallThickness))
    t0 = time.time()
    try:
        vt.recompute()
        log("S6: recompute took {:.1f}s".format(time.time() - t0))
    except Exception as exc:
        log("S6: recompute raised: {!r}".format(exc))
    if pad is not None:
        log("S6: POST-recompute Pad.Length = " + repr(pad.Length))
        log("S6: POST-recompute Pad.State = " + repr(pad.State))
    # Count how many objects in the dependent doc carry errors right now.
    bad = []
    for o in vt.Objects:
        st = getattr(o, "State", [])
        if isinstance(st, list) and any(
                s in ("Invalid", "Error") for s in st):
            bad.append(o.Name)
    log("S6: objects flagged Invalid/Error after recompute: " + repr(bad))
    flush()

    sec("DONE")
    flush()


try:
    main()
except Exception:
    log("FATAL:\n" + traceback.format_exc())
    flush()
