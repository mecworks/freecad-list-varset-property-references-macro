"""Integration test against a real FreeCAD document (no GUI needed).

Run with freecadcmd from anywhere:

    freecadcmd.exe tests/test_integration_freecad.py

(any freecadcmd on PATH, or adjust the path to your install). Exits
non-zero on failure, so it can gate CI.
"""

import ast
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import FreeCAD as App  # noqa: E402
import varset_usage_core_dev as core  # noqa: E402

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    suffix = "  [{}]".format(detail) if detail and not cond else ""
    print("{} {}{}".format("PASS" if cond else "FAIL", name, suffix))


class Proxy:
    def __init__(self, obj):
        obj.addProperty("App::PropertyDistance", "Len", "Base", "")


def main():
    doc = App.newDocument("VarSetUsageTest")

    dims = doc.addObject("App::VarSet", "Dims")
    dims.addProperty("App::PropertyLength", "Width", "Base", "")
    dims.addProperty("App::PropertyLength", "Height", "Base", "")
    dims.Width = 10
    dims.Height = 20

    decoy = doc.addObject("App::VarSet", "Decoy")
    decoy.Label = "Dims"  # duplicate label on purpose
    decoy.addProperty("App::PropertyLength", "Width", "Base", "")

    t1 = doc.addObject("App::FeaturePython", "UsesName")
    t1.Proxy = Proxy(t1)
    t1.setExpression("Len", "Dims.Width * 2")

    t2 = doc.addObject("App::FeaturePython", "UsesLabel")
    t2.Proxy = Proxy(t2)
    t2.setExpression("Len", "<<Dims>>.Width + 1mm")

    t3 = doc.addObject("App::FeaturePython", "UsesDecoy")
    t3.Proxy = Proxy(t3)
    t3.setExpression("Len", "Decoy.Width")

    t4 = doc.addObject("App::FeaturePython", "Unrelated")
    t4.Proxy = Proxy(t4)
    t4.setExpression("Len", "1mm + 2mm")

    # Superset-name trap: internal name ends with the selected VarSet's
    # name and references its own same-named property.
    t5 = doc.addObject("App::FeaturePython", "SuperDims")
    t5.Proxy = Proxy(t5)
    t5.addProperty("App::PropertyLength", "Width", "Base", "")
    t5.setExpression("Len", "SuperDims.Width * 3")

    # Bare VarSet used by the STANDARD_PROPERTIES drift check below.
    bare = doc.addObject("App::VarSet", "BareCheck")

    # -- discovery ------------------------------------------------------------
    found = core.find_varsets(doc)
    check("find_varsets finds all three VarSets",
          sorted(o.Name for o in found) == ["BareCheck", "Decoy", "Dims"],
          repr(sorted(o.Name for o in found)))

    # NOTE: FreeCAD reports PropertiesList in alphabetical order, not
    # creation order -- compare accordingly.
    check("user_properties lists only custom props",
          sorted(core.user_properties(dims)) == ["Height", "Width"],
          repr(core.user_properties(dims)))

    # Drift check (S3): the pinned STANDARD_PROPERTIES must still equal a
    # bare VarSet's live PropertiesList; fail loudly if upstream adds one.
    check("STANDARD_PROPERTIES matches bare VarSet (drift check)",
          set(bare.PropertiesList) == set(core.STANDARD_PROPERTIES),
          repr(sorted(bare.PropertiesList)))

    # -- matching -------------------------------------------------------------
    hits = core.find_usages(doc, dims, "Width")
    paths = sorted(p for p, _ in hits)
    check("anchored match count == 2", len(hits) == 2, repr(hits))
    check("internal-name reference matched", "UsesName.Len" in paths, repr(paths))
    check("<<label>> reference matched", "UsesLabel.Len" in paths, repr(paths))
    check("decoy VarSet excluded",
          not any("Decoy" in p or "(Decoy)" in p for p, _ in hits), repr(hits))
    check("superset-named object excluded",
          not any("SuperDims" in p for p, _ in hits), repr(hits))
    check("unrelated expression excluded",
          not any("Unrelated" in p for p, _ in hits), repr(hits))

    exprs = dict(hits)
    check("expression text preserved",
          exprs.get("UsesName.Len") == "Dims.Width * 2", repr(exprs))

    # report formatting
    report = core.format_report(hits)
    check("report has one line per usage", report.count("\n") == len(hits) - 1,
          repr(report))

    # -- cross-document reference (DocName#Object.Property) -------------------
    # Replicates the real workflow: a second file referencing this document's
    # VarSet via 'VarSetUsageTest#Dims.Width'. The referenced document must
    # be saved for the reference to resolve.
    tmpdir = tempfile.mkdtemp(prefix="fc_xref_it_")
    doc.saveAs(os.path.join(tmpdir, "VarSetUsageTest.FCStd"))
    vent = App.newDocument("VentFile")
    vp = vent.addObject("App::FeaturePython", "VentPart")
    vp.Proxy = Proxy(vp)
    vent.saveAs(os.path.join(tmpdir, "VentFile.FCStd"))
    vp.setExpression("Len", "VarSetUsageTest#Dims.Width * 2")
    vent.recompute()
    try:
        val = float(vp.Len.Value)
    except Exception:
        val = None
    check("cross-doc reference resolves (10mm * 2)",
          val is not None and abs(val - 20.0) < 1e-6, repr(val))

    home_hits = core.find_usages(doc, dims, "Width")
    check("home-only scan misses cross-doc usage",
          not any("VentPart" in p for p, _ in home_hits), repr(home_hits))

    all_hits = core.find_usages_all([doc, vent], dims, "Width")
    check("multi-doc scan finds cross-doc usage",
          any(d.Name == "VentFile" and p == "VentPart.Len"
              for d, p, _ in all_hits), repr(all_hits))

    multi_report = core.format_report_multi(all_hits, doc)
    check("multi-doc report prefixes foreign doc only",
          "[VentFile] VentPart.Len" in multi_report
          and "UsesName.Len =" in multi_report, repr(multi_report))

    App.closeDocument(vent.Name)

    # -- dead cross-document reference ------------------------------------
    # Two ways dead bindings arise in practice:
    #
    # (a) Direct: the expression names a document that is not open
    #     (typo in the expression editor, or the source file was closed).
    #     setExpression ACCEPTS such names -- parsing does not require the
    #     referenced document to exist (ObjectIdentifier::resolveAmbiguity
    #     skips forced identifiers); the property simply sits Touched/
    #     Invalid until a document with that EXACT name (case-sensitive)
    #     opens, at which point the reference revives automatically
    #     (research/PROBE_DEADREF5.txt).
    #
    # (b) Rename round-trip: the binding is valid when created, then the
    #     referenced file is renamed on disk. FreeCAD keeps the old name
    #     verbatim in ExpressionEngine and freezes the value silently
    #     (research/PROBE_RENAME.txt).
    #
    # NOTE: synthetic fixture property names must avoid unit keywords
    # (mm, m, W, V, A, N, s, ...): the expression lexer ranks unit
    # literals above IDENTIFIER, so a property named 'W' makes
    # 'Doc#Obj.W * 2' unparseable (ParserError) -- a trap that burned
    # early probes (see research/probe_deadref5.py header).

    # (a) direct ghost binding -------------------------------------------
    gh = App.newDocument("GhostHost")
    gp = gh.addObject("App::FeaturePython", "GP")
    gp.Proxy = Proxy(gp)
    try:
        gp.setExpression("Len", "PhantomDoc#Vars.Width * 2")
        ghost_accepted = True
    except Exception:
        ghost_accepted = False
    check("ghost-doc setExpression accepted", ghost_accepted,
          repr(list(gp.ExpressionEngine)))
    gh_open = set(App.listDocuments())
    check("PhantomDoc absent from open documents",
          "PhantomDoc" not in gh_open, repr(sorted(gh_open)))
    check("unresolved_doc_names flags the ghost reference",
          core.unresolved_doc_names("PhantomDoc#Vars.Width * 2",
                                    gh_open) == ["PhantomDoc"])
    gh_hits = [(gh, "GP.Len", "PhantomDoc#Vars.Width * 2")]
    gh_report = core.format_report_multi(gh_hits, gh,
                                         open_doc_names=gh_open)
    check("ghost report carries marker and legend",
          "(!) GP.Len = PhantomDoc#Vars.Width * 2" in gh_report
          and "Missing documents: PhantomDoc" in gh_report,
          repr(gh_report))
    App.closeDocument(gh.Name)

    # (b) rename round-trip ----------------------------------------------
    tmpdir2 = tempfile.mkdtemp(prefix="fc_deadref_it_")
    dm = App.newDocument("DeadMaster")
    dmv = dm.addObject("App::VarSet", "Vars")
    dmv.addProperty("App::PropertyLength", "Width", "Base", "")
    dmv.Width = 4.0
    dm.saveAs(os.path.join(tmpdir2, "DeadMaster.FCStd"))
    dd = App.newDocument("DeadDep")
    dp = dd.addObject("App::FeaturePython", "DP")
    dp.Proxy = Proxy(dp)
    # setExpression requires the OWNER document to be saved first...
    dd.saveAs(os.path.join(tmpdir2, "DeadDep.FCStd"))
    dp.setExpression("Len", "DeadMaster#Vars.Width * 2")
    dd.recompute()
    try:
        pre_val = float(dp.Len.Value)
    except Exception:
        pre_val = None
    check("pre-rename binding live (4mm * 2)",
          pre_val is not None and abs(pre_val - 8.0) < 1e-6, repr(pre_val))
    # ...but the binding must be persisted too: closeDocument under
    # freecadcmd discards unsaved modifications, so save once more.
    dd.save()
    App.closeDocument(dd.Name)
    App.closeDocument(dm.Name)
    os.rename(os.path.join(tmpdir2, "DeadMaster.FCStd"),
              os.path.join(tmpdir2, "RenamedMaster.FCStd"))

    dep2 = App.openDocument(os.path.join(tmpdir2, "DeadDep.FCStd"))
    # Re-acquire the object: the pre-close Python handle is dead once the
    # document was closed.
    dp = dep2.getObject("DP")
    # The auto-loader tries to pull 'DeadMaster' in by same-folder filename
    # match and fails silently; the binding survives verbatim.
    check("binding survives reopen verbatim",
          dp.ExpressionEngine == [("Len", "DeadMaster#Vars.Width * 2")],
          repr(dp.ExpressionEngine))
    open_names = set(App.listDocuments())
    check("old doc name absent from open documents",
          "DeadMaster" not in open_names, repr(sorted(open_names)))
    offenders = core.unresolved_doc_names("DeadMaster#Vars.Width * 2",
                                          open_names)
    check("unresolved_doc_names flags the dead reference",
          offenders == ["DeadMaster"], repr(offenders))

    master3 = App.openDocument(os.path.join(tmpdir2, "RenamedMaster.FCStd"))
    vs2 = master3.getObject("Vars")
    hits = core.find_usages_all([dep2, master3], vs2, "Width")
    report = core.format_report_multi(hits, dep2,
                                      open_doc_names=set(App.listDocuments()))
    check("multi-doc report flags the dead line only",
          "(!) DP.Len = DeadMaster#Vars.Width * 2" in report
          and "Missing documents: DeadMaster" in report
          and report.count(core.DEAD_REF_MARKER) == 2,  # line + legend
          repr(report))

    # Control: a fresh binding to the CURRENT name resolves and is NOT
    # flagged in the same report.
    dp_live = dep2.addObject("App::FeaturePython", "DPLive")
    dp_live.Proxy = Proxy(dp_live)
    dp_live.setExpression("Len", "RenamedMaster#Vars.Width")
    dep2.recompute()
    try:
        live_val = float(dp_live.Len.Value)
    except Exception:
        live_val = None
    check("fresh current-name binding resolves (4.0)",
          live_val is not None and abs(live_val - 4.0) < 1e-6, repr(live_val))
    hits2 = core.find_usages_all([dep2, master3], vs2, "Width")
    report2 = core.format_report_multi(hits2, dep2,
                                       open_doc_names=set(App.listDocuments()))
    check("live line unflagged alongside dead line",
          "DPLive.Len = RenamedMaster#Vars.Width" in report2
          and "(!) DPLive.Len" not in report2, repr(report2))

    App.closeDocument(dep2.Name)
    App.closeDocument(master3.Name)
    import shutil as _shutil
    _shutil.rmtree(tmpdir2, ignore_errors=True)

    # -- macro file sanity ------------------------------------------------------
    macro_path = os.path.join(ROOT, "src",
                               "ListVarSetPropertyReferences_dev.FCMacro")
    with open(macro_path, encoding="utf-8") as fh:
        src = fh.read()
    try:
        ast.parse(src)
        check("macro file parses", True)
    except SyntaxError as exc:
        check("macro file parses", False, str(exc))

    failures = sum(1 for _, ok in RESULTS if not ok)
    print("\n{} failure(s) out of {} checks".format(failures, len(RESULTS)))
    App.closeDocument(doc.Name)
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
