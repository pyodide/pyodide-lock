# pyodide-lock

[![PyPI Latest Release](https://img.shields.io/pypi/v/pyodide-lock.svg)](https://pypi.org/project/pyodide-lock/)
![GHA](https://github.com/pyodide/pyodide-lock/actions/workflows/main.yml/badge.svg)

Shared utils for the Pyodide ecosystem

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
