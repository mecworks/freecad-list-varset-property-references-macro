# -*- coding: utf-8 -*-
"""Runner for test_integration_freecad.py under freecadcmd.

freecadcmd swallows script stdout and masks exceptions with exit code 0,
so this wrapper captures the test's own output and exit code into
research/INTEGRATION_RUN.txt.

Run: freecadcmd.exe tests/run_capture.py
"""
import contextlib
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

OUT_PATH = os.path.join(ROOT, "research", "INTEGRATION_RUN.txt")

buf = io.StringIO()
code = 0
try:
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        import test_integration_freecad as t
        t.main()
except SystemExit as exc:
    code = exc.code if isinstance(exc.code, int) else 1
except Exception:
    import traceback
    buf.write("RUNNER EXCEPTION:\n" + traceback.format_exc())
    code = 99

with open(OUT_PATH, "w", encoding="utf-8") as fh:
    fh.write(buf.getvalue())
    fh.write("\nEXIT_CODE={}\n".format(code))
