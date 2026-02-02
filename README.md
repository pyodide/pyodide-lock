# pyodide-lock

[![PyPI Latest Release](https://img.shields.io/pypi/v/pyodide-lock.svg)](https://pypi.org/project/pyodide-lock/)
![GHA](https://github.com/pyodide/pyodide-lock/actions/workflows/main.yml/badge.svg)
[![codecov](https://codecov.io/gh/pyodide/pyodide-lock/branch/main/graph/badge.svg?token=T0UEJW2F2P)](https://codecov.io/gh/pyodide/pyodide-lock)

Tooling to manage `pyodide-lock.json` files.

The `pyodide-lock.json` file captures the versions of the packages
used in a given Pyodide application. Packages included in `pyodide-lock.json`
will be auto-loaded at import time, when using `pyodide.runPythonAsync` or
running in JupyterLite or PyScript, and do not need to be explicitly installed
with `micropip`.

## Installation

```bash
pip install pyodide-lock
```

## Python API

### Read and writing lock files

To parse and write a `pyodide-lock.json` file:

```python
from pathlib import Path
from pyodide_lock import PyodideLockSpec

lock_path = Path("pyodide-lock.json")
lock_spec = PyodideLockSpec.from_json(lock_path)
# Make some changes
lock_spec.to_json(lock_path)
```

## License

BSD-3-Clause License
