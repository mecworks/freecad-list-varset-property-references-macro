# -*- coding: utf-8 -*-
"""End-to-end test of the SINGLE-FILE distribution build.

Builds ListVarSetPropertyReferences.FCMacro (project root) from the two
development files in src/ and verifies the artifact the way a recipient
would experience it:

  D0  builder runs and self-verifies (byte-exact embed, metadata, parse)
  D1  generated file parses independently
  D2  embedded core is byte-identical to src/varset_usage_core_dev.py
      (AST extract)
  D3  standalone execution: the distro file ALONE in an empty folder --
      no sibling core anywhere reachable -- loads its embedded copy
      (proven by module name), and the ``if __name__ == "__main__"``
      guard fires main(), which reports "No active document found."
      (QMessageBox stubbed so the headless run cannot block)
  D4  full dialog flow through the distro-built namespace (offscreen Qt):
      local usage, cross-document usage with [doc] prefix, DEAD reference
      flagged with (!) + legend, superset-named decoy excluded, and
      unchecking "Include other open documents" drops foreign lines
  D5  re-execution safety (second exec in a fresh namespace)
  D6  development-layout regression: the DEV macro still loads the
      sibling file (module name 'varset_usage_core_dev'), sys.path untouched

Self-reports to research/DISTRO_E2E.txt (freecadcmd swallows stdout).
Run: freecadcmd.exe tests/test_distro_e2e.py
"""
import ast
import os
import shutil
import sys
import tempfile
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     ".."))
BUILDER_DIR = os.path.join(ROOT, "scripts")
OUT = os.path.join(ROOT, "research", "DISTRO_E2E.txt")

lines = []


def log(msg=""):
    lines.append(str(msg))
    print(msg)


def flush():
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


failures = []


def check(name, ok, detail=""):
    log(("PASS " if ok else "FAIL ") + name + (("  " + repr(detail))
                                               if (detail and not ok) else ""))
    if not ok:
        failures.append(name)


sys.path.insert(0, BUILDER_DIR)
import build_single_file as bld  # noqa: E402

# --------------------------------------------------------------------------
# D0-D2: build + structural verification
# --------------------------------------------------------------------------
try:
    dist_path = bld.build()
    check("D0 build produces the distro file", os.path.isfile(dist_path),
          dist_path)
except Exception as exc:
    check("D0 build produces the distro file", False, repr(exc))
    flush()
    raise SystemExit(1)

gen_src = open(dist_path, encoding="utf-8").read()
core_src = open(os.path.join(ROOT, "src", "varset_usage_core_dev.py"),
                encoding="utf-8").read()

try:
    ast.parse(gen_src)
    check("D1 generated file parses", True)
except SyntaxError as exc:
    check("D1 generated file parses", False, repr(exc))

embedded = bld._extract_embedded(gen_src)
check("D2 embedded core byte-identical to src/varset_usage_core_dev.py",
      embedded == core_src,
      (len(embedded) if embedded is not None else -1, len(core_src)))
for field in ("__Name__", "__Version__", "__License__", "__Requires__",
              "__Help__"):
    check("D2 metadata field present: {}".format(field),
          "{} = ".format(field) in gen_src)

# --------------------------------------------------------------------------
# D3: standalone execution in an EMPTY folder (no sibling core)
# --------------------------------------------------------------------------
solo_dir = tempfile.mkdtemp(prefix="fc_distro_solo_")
solo_path = os.path.join(solo_dir, "ListVarSetPropertyReferences.FCMacro")
shutil.copyfile(dist_path, solo_path)

import PySide6.QtWidgets as QW  # noqa: E402

msg_calls = []
_real_critical = QW.QMessageBox.critical


class _RecordingCritical:
    @staticmethod
    def critical(*args, **kwargs):
        msg_calls.append(args)
        return 0


QW.QMessageBox.critical = _RecordingCritical.critical
ns = {"__file__": solo_path, "__name__": "__main__"}
try:
    exec(compile(gen_src, solo_path, "exec"), ns)
    d3_raised = None
except BaseException as exc:  # noqa: BLE001
    d3_raised = exc
finally:
    QW.QMessageBox.critical = _real_critical

check("D3 standalone exec clean (empty folder, no sibling core)",
      d3_raised is None, repr(d3_raised))
check("D3 core loaded from embedded copy",
      getattr(ns.get("core"), "__name__", "") == "varset_usage_core_embedded",
      getattr(ns.get("core"), "__name__", None))
check("D3 no load error recorded", ns.get("_load_error") is None,
      ns.get("_load_error"))
check("D3 __main__ guard fired main()", len(msg_calls) == 1, len(msg_calls))
if msg_calls:
    check("D3 main() reported missing active document",
          "No active document found." in str(msg_calls[0][-1]),
          str(msg_calls[0][-1]))

# --------------------------------------------------------------------------
# D4: full dialog flow through the distro-built namespace
# --------------------------------------------------------------------------
from PySide6 import QtWidgets as QTW  # noqa: E402

qapp = QTW.QApplication.instance() or QTW.QApplication(["distro_e2e"])
import FreeCAD as App  # noqa: E402

c_tmp = tempfile.mkdtemp(prefix="fc_distro_flow_")


class _P:
    def __init__(self, obj):
        obj.addProperty("App::PropertyDistance", "Len", "Base", "")


home = App.newDocument("DistHome")
vs = home.addObject("App::VarSet", "Dims")
vs.addProperty("App::PropertyLength", "Width", "Base", "")
vs.Width = 10.0
pad = home.addObject("App::FeaturePython", "Pad")
pad.Proxy = _P(pad)
pad.setExpression("Len", "Dims.Width * 2")
decoy = home.addObject("App::FeaturePython", "SuperDims")
decoy.Proxy = _P(decoy)
decoy.addProperty("App::PropertyLength", "Width", "Base", "")
decoy.setExpression("Len", "SuperDims.Width * 3")
home.saveAs(os.path.join(c_tmp, "DistHome.FCStd"))

vent = App.newDocument("DistVent")
vp = vent.addObject("App::FeaturePython", "VP")
vp.Proxy = _P(vp)
vent.saveAs(os.path.join(c_tmp, "DistVent.FCStd"))
vp.setExpression("Len", "DistHome#Dims.Width * 3")
vent.recompute()

ghost = App.newDocument("DistGhost")
gp = ghost.addObject("App::FeaturePython", "GP")
gp.Proxy = _P(gp)
# Accepted although PhantomDoc exists nowhere (verified behaviour,
# research/PROBE_DEADREF5.txt P1); the binding stays Touched/Invalid.
gp.setExpression("Len", "PhantomDoc#Dims.Width * 2")

try:
    dlg = ns["UsageDialog"](home)
    check("D4 dialog constructed from distro namespace", True)
    dlg._on_varset_changed(0)
    props = [dlg.property_combo.itemText(i)
             for i in range(dlg.property_combo.count())]
    check("D4 property combo lists Width", props == ["Width"], props)
    dlg._on_property_changed(0)
    text = dlg.results.toPlainText()
    check("D4 count header is 3 usage(s)", text.startswith("3 usage(s):"),
          text.splitlines()[0] if text else "")
    check("D4 local usage plain", "Pad.Len = Dims.Width * 2" in text, text)
    check("D4 cross-doc usage prefixed",
          "[DistVent] VP.Len = DistHome#Dims.Width * 3" in text, text)
    check("D4 dead reference flagged with marker + doc prefix",
          "(!) [DistGhost] GP.Len = PhantomDoc#Dims.Width * 2" in text, text)
    check("D4 legend names the missing document",
          "Missing documents: PhantomDoc" in text, text)
    check("D4 superset-named decoy excluded",
          "SuperDims.Width" not in text, text)

    dlg.scan_all_cb.setChecked(False)
    dlg._on_property_changed(0)
    text_local = dlg.results.toPlainText()
    check("D4 unchecked -> local only",
          "Pad.Len = Dims.Width * 2" in text_local
          and "[DistVent]" not in text_local
          and "(!)" not in text_local, text_local)
finally:
    for d in ("DistHome", "DistVent", "DistGhost"):
        if d in App.listDocuments():
            App.closeDocument(d)

# --------------------------------------------------------------------------
# D5: re-execution safety
# --------------------------------------------------------------------------
ns2 = {"__file__": solo_path, "__name__": "distro_e2e_re"}
try:
    exec(compile(gen_src, solo_path, "exec"), ns2)
    check("D5 second exec clean", True)
except BaseException as exc:  # noqa: BLE001
    check("D5 second exec clean", False, repr(exc))
check("D5 second exec reloads embedded core",
      getattr(ns2.get("core"), "__name__", "") == "varset_usage_core_embedded")

# --------------------------------------------------------------------------
# D6: development-layout regression (sibling file still wins when no embed)
# --------------------------------------------------------------------------
dev_src = open(os.path.join(ROOT, "src",
                             "ListVarSetPropertyReferences_dev.FCMacro"),
               encoding="utf-8").read()
path_before = list(sys.path)
ns3 = {"__file__": os.path.join(ROOT, "src",
                                "ListVarSetPropertyReferences_dev.FCMacro"),
       "__name__": "dev_check"}
try:
    exec(compile(dev_src, ns3["__file__"], "exec"), ns3)
    check("D6 dev macro exec clean", True)
except BaseException as exc:  # noqa: BLE001
    check("D6 dev macro exec clean", False, repr(exc))
check("D6 dev macro loads sibling core (not embedded)",
      getattr(ns3.get("core"), "__name__", "") == "varset_usage_core_dev",
      getattr(ns3.get("core"), "__name__", None))
check("D6 sys.path unchanged", list(sys.path) == path_before)

# --------------------------------------------------------------------------
log("")
log("{} failure(s)".format(len(failures)))
flush()
raise SystemExit(1 if failures else 0)
