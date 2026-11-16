# -*- coding: utf-8 -*-
"""READ-ONLY: what TYPE is a real-world 'VarSet' object? Point TARGET_FILE
at any document of your own that contains one. Nothing is saved or mutated.

Run: freecadcmd.exe research/probe_realvarset.py
"""
import os
import traceback

# Point this at a document of your own that contains a VarSet.
TARGET_FILE = r"<YOUR_PROJECT_DIR>\YourFile.FCStd"

OUT = []


def log(*args):
    line = " ".join(str(a) for a in args)
    OUT.append(line)
    print(line)


try:
    import FreeCAD as App

    if not os.path.isfile(TARGET_FILE):
        raise RuntimeError(
            "TARGET_FILE not found -- point it at a document of your own "
            "that contains a VarSet")
    doc = App.openDocument(TARGET_FILE)
    log("documents:", repr(sorted(App.listDocuments())))
    vs = doc.getObject("VarSet")
    log("VarSet is None?", vs is None)
    if vs is not None:
        log("repr          :", repr(vs))
        log("TypeId        :", vs.TypeId)
        log("isDerivedFrom App::VarSet:",
            vs.isDerivedFrom("App::VarSet"))
        log("isDerivedFrom App::FeaturePython:",
            vs.isDerivedFrom("App::FeaturePython"))
        log("PropertiesList:", repr(vs.PropertiesList))
        # Who else in this doc is an App::VarSet?
        varsets = [o.Name for o in doc.Objects
                   if o.isDerivedFrom("App::VarSet")]
        log("all App::VarSet-derived objects in doc:", repr(varsets))
except Exception:
    log("FATAL:\n" + traceback.format_exc())
finally:
    for nm in list(App.listDocuments()):
        try:
            App.closeDocument(nm)
        except Exception:
            pass

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "PROBE_REALVARSET.txt"),
          "w", encoding="utf-8") as fh:
    fh.write("\n".join(OUT) + "\n")
