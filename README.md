# pyodide-lock

[![PyPI Latest Release](https://img.shields.io/pypi/v/pyodide-lock.svg)](https://pypi.org/project/pyodide-lock/)
![GHA](https://github.com/pyodide/pyodide-lock/actions/workflows/main.yml/badge.svg)

Tooling to manage the `pyodide-lock.json` file.

Note: the API of this package is still being iterated on and may change completely
before the 0.1 release.

The `pyodide-lock` file is used to lock the versions of the packages that are
used in a given Pyodide application. Packages included in `pyodide-lock.json`
will be auto-loaded at import time, when using `pyodide.runPythonAsync` or
running in JupyterLite or PyScript, and do not need to be explicitly installed
with micropip.

## Installation

```bash
pip install pyodide-lock
```

## Python API

To parsing and write the `pyodide-lock.json` (formerly `repodata.json`) file:
```py
from pyodide_lock import PyodideLockSpec

lock_spec = PyodideLockSpec.from_json("pyodide-lock.json")
# Make some changes
lock_spec.to_json("pyodide-lock.json")
```

## License

BSD-3-Clause License
