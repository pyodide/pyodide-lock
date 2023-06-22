# pyodide-utils

[![PyPI Latest Release](https://img.shields.io/pypi/v/pyodide-utils.svg)](https://pypi.org/project/pyodide-utils/)
![GHA](https://github.com/rth/pyodide-utils/actions/workflows/main.yml/badge.svg)

Shared utils for the Pyodide ecosystem

## Installation

```bash
pip install pyodide-utils
```


## Functionality

1. Parsing and writing the `pyodide-lock.json` (formerly `repodata.json`) file:
```py
from pyodide_utils.lock_spec import PyodideLockSpec

lock_spec = PyodideLockSpec.from_json("pyodide-lock.json")
# Make some changes
lock_spec.to_json("pyodide-lock.json")
```

## License

BSD-3-Clause License
