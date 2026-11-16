"""Second probe: findObjects kwargs, signal availability."""
import FreeCAD as App
from PySide6 import QtWidgets

doc = App.newDocument("ProbeDoc2")
vs = doc.addObject("App::VarSet", "MyVars")
other = doc.addObject("App::FeaturePython", "NotAVarSet")
try:
    r = doc.findObjects(Type="App::VarSet")
    print("findObjects(Type='App::VarSet'):", [o.Name for o in r])
except Exception as e:
    print(f"findObjects kwarg FAIL: {type(e).__name__}: {e}")
try:
    r = doc.findObjects(Name=r"^MyVars$")
    print("findObjects(Name regex):", [o.Name for o in r])
except Exception as e:
    print(f"findObjects Name FAIL: {type(e).__name__}: {e}")

print("QComboBox.activated exists:", hasattr(QtWidgets.QComboBox, "activated"))
print("QMessageBox.critical exists:", hasattr(QtWidgets.QMessageBox, "critical"))
print("PROBE2 DONE")
