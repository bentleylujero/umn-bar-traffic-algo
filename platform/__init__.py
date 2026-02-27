# This package is named 'platform', which would normally shadow the Python
# stdlib 'platform' module. To prevent breaking third-party libraries that
# do `import platform` (e.g. pandas uses platform.python_implementation()),
# we load the stdlib module directly by path and re-export its public API.
import importlib.util as _util
import sys as _sys

# Locate the stdlib platform.py using its known path (Python 3 stdlib)
_stdlib_path = None
for _candidate_dir in [
    "/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/lib/python3.9",
    "/usr/lib/python3.9",
    "/usr/local/lib/python3.9",
]:
    import os as _os
    _p = _os.path.join(_candidate_dir, "platform.py")
    if _os.path.isfile(_p):
        _stdlib_path = _p
        break

if _stdlib_path:
    _spec = _util.spec_from_file_location("_stdlib_platform", _stdlib_path)
    _stdlib_platform = _util.module_from_spec(_spec)  # type: ignore[arg-type]
    _spec.loader.exec_module(_stdlib_platform)  # type: ignore[union-attr]
    # Re-export all stdlib platform attributes into this namespace
    for _attr in dir(_stdlib_platform):
        if not _attr.startswith("__"):
            globals()[_attr] = getattr(_stdlib_platform, _attr)
    # Also register under the old name so `import platform; platform.X` works
    # for any code that cached a reference to the stdlib module
    _sys.modules.setdefault("_stdlib_platform", _stdlib_platform)
