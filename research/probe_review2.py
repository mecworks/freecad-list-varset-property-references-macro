"""Probe 2: find the working monospace-font API in this PySide6 build."""
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "PROBE_REVIEW2.txt")
lines = []


def log(msg=""):
    lines.append(str(msg))
    print(msg)


from PySide6 import QtGui

log("=== probe_review2 ===")
log("PySide6 version: {}".format(__import__("PySide6").__version__))

qn_attrs = [a for a in dir(QtGui.QFont) if "amil" in a or "tyle" in a or "ixed" in a]
log("QFont attrs (family/style/fixed): {}".format(qn_attrs))

for enum_name in ("StyleHint", "FontFamily", "Weight", "Capitalization"):
    try:
        enum = getattr(QtGui.QFont, enum_name)
        members = [m for m in dir(enum) if not m.startswith("_")]
        log("{}: {}".format(enum_name, members[:40]))
    except Exception as exc:
        log("{} missing: {!r}".format(enum_name, exc))

# Candidate calls
candidates = [
    ("setStyleHint(StyleHint.Monospace)", lambda f: f.setStyleHint(QtGui.QFont.StyleHint.Monospace)),
    ("setStyleHint(StyleHint.Fixed)", lambda f: f.setStyleHint(QtGui.QFont.StyleHint.Fixed)),
    ("setFamily(FontFamily.Monospace)", lambda f: f.setFamily(QtGui.QFont.FontFamily.Monospace)),
    ('setFamily("Consolas")', lambda f: f.setFamily("Consolas")),
    ("setFixedPitch(True)", lambda f: f.setFixedPitch(True)),
]
for desc, fn in candidates:
    try:
        f = QtGui.QFont()
        fn(f)
        log("OK   {}: family={!r} styleHint={} fixedPitch={}"
            .format(desc, f.family(), f.styleHint(), f.fixedPitch()))
    except Exception as exc:
        log("FAIL {}: {!r}".format(desc, exc))

with open(OUT, "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
