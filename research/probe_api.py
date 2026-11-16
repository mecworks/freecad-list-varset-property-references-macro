"""Probe FreeCAD 1.1.4 Python API behaviors relevant to the VarSet usage macro."""
import os
import sys

print("PYTHON:", sys.version.replace("\n", " "))
import FreeCAD as App

print("FREECAD VERSION:", tuple(App.Version()))

# --- 1. PySide module availability -------------------------------------------
for m in ("PySide", "PySide2", "PySide6"):
    try:
        __import__(m)
        print(f"MODULE {m}: ok")
    except Exception as e:
        print(f"MODULE {m}: FAIL {type(e).__name__}: {e}")

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    print("PySide6 imports: ok")
except Exception as e:
    print("PySide6 imports FAIL:", e)
    raise SystemExit(1)

# QMessageBox location
try:
    from PySide6.QtGui import QMessageBox as _qb  # noqa
    print("QtGui.QMessageBox: AVAILABLE")
except Exception as e:
    print(f"QtGui.QMessageBox: FAIL {type(e).__name__}: {e}")
try:
    from PySide6.QtWidgets import QMessageBox as _qb2  # noqa
    print("QtWidgets.QMessageBox: AVAILABLE")
except Exception as e:
    print(f"QtWidgets.QMessageBox: FAIL {type(e).__name__}: {e}")

from PySide6.QtWidgets import QDialog
print("QDialog.exec exists:", hasattr(QDialog, "exec"))
print("QDialog.exec_ exists:", hasattr(QDialog, "exec_"))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

# --- 2. Signal argument types -------------------------------------------------
class Probe(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.cb = QtWidgets.QComboBox(self)
        self.got = None
        self.cb.currentIndexChanged.connect(lambda *a: setattr(self, "got", a))
        self.cb.addItem("x")
        self.cb.addItem("y")

p = Probe()
print("currentIndexChanged args after addItem:", p.got)
p.cb.setCurrentIndex(1)
print("currentIndexChanged args after setCurrentIndex:", p.got)

# --- 3. VarSet object model ----------------------------------------------------
doc = App.newDocument("ProbeDoc")
vs = doc.addObject("App::VarSet", "MyVars")
print("VarSet Name:", vs.Name, "| TypeId:", vs.TypeId,
      "| isDerivedFrom App::VarSet:", vs.isDerivedFrom("App::VarSet"))
vs2 = doc.addObject("App::VarSet", "Other")
print("second varset internal name:", vs2.Name)
doc_methods = [m for m in dir(doc) if "bject" in m]
print("Document object-methods:", doc_methods)
try:
    print("getObjectsByType('App::VarSet'):", [o.Name for o in doc.getObjectsByType("App::VarSet")])
except Exception as e:
    print(f"getObjectsByType FAIL: {type(e).__name__}: {e}")
print("isDerivedFrom filter:", [o.Name for o in doc.Objects if o.isDerivedFrom("App::VarSet")])
print("PropertiesList:", list(vs.PropertiesList))
try:
    print("Properties keys:", list(vs.Properties.keys()))
except Exception as e:
    print(f"obj.Properties FAIL: {type(e).__name__}: {e}")
vs.addProperty("App::PropertyLength", "Width", "Base", "test width")
vs.Width = 10
print("after addProperty PropertiesList:", list(vs.PropertiesList))
try:
    prop = vs.Properties["Width"]
    print("Property type:", type(prop).__name__, "| Attribute:", int(prop.Attribute))
except Exception as e:
    print(f"obj.Properties FAIL: {type(e).__name__}: {e}")
print("hasattr obj.Properties:", hasattr(vs, "Properties"))
print("help(findObjects):")
import textwrap
print(textwrap.shorten((doc.findObjects.__doc__ or "(no docstring)"), 400))
try:
    print("findObjects('VarSet'):", [o.Name for o in doc.findObjects("VarSet")])
except Exception as e:
    print(f"findObjects FAIL: {type(e).__name__}: {e}")

# --- 4. Expression engine ------------------------------------------------------
class Proxy:
    def __init__(self, obj):
        obj.addProperty("App::PropertyDistance", "Len", "Base", "")

tgt = doc.addObject("App::FeaturePython", "Target")
tgt.Proxy = Proxy(tgt)
tgt.setExpression("Len", "<<MyVars>>.Width * 2")
tgt2 = doc.addObject("App::FeaturePython", "Target2")
tgt2.Proxy = Proxy(tgt2)
tgt2.setExpression("Len", "MyVars.Width + 1mm")

ee = tgt.ExpressionEngine
print("ExpressionEngine type:", type(ee).__name__)
print("ExpressionEngine repr:", repr(ee))
try:
    print("iter(ee):", list(iter(ee)))
except Exception as e:
    print("iter(ee) FAIL:", type(e).__name__, e)
try:
    print("ee.items():", list(ee.items()))
except Exception as e:
    print("ee.items() FAIL:", type(e).__name__, e)
try:
    t3 = doc.addObject("App::FeaturePython", "T3")
    print("len(ee):", len(ee), "| bool(empty ee):", bool(t3.ExpressionEngine))
except Exception as e:
    print("len/bool FAIL:", type(e).__name__, e)

# getObjectsByLabel
print("getObjectsByLabel('MyVars'):", [o.Name for o in doc.getObjectsByLabel("MyVars")])
# evalExpression
try:
    print("evalExpression('1+1'):", App.evalExpression("1 + 1"))
except Exception as e:
    print("App.evalExpression FAIL:", type(e).__name__, e)
try:
    print("DocumentObject.evalExpression('1+1'):", App.DocumentObject.evalExpression("1 + 1"))
except Exception as e:
    print("DocumentObject.evalExpression FAIL:", type(e).__name__, e)

print("PROBE DONE")
