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

### Adding pre-built wheels and dependencies

Recent versions of `uv` directly support the `wasm32-pyodide2024` platform.
Installing `pyodide-lock[uv]` allows for updating a lockfile with new wheels.

> **Note**
>
> This technique is mostly limited to pure Python wheels. See
> [pyodide-build](https://github.com/pyodide/pyodide-build) for a more general
> Pyodide distribution builder, especially compiled binary extensions using C or
> Rust.

```python
from pathlib import Path
from pyodide_lock import PyodideLockSpec
from pyodide_lock.uv_pip_compile import UvPipCompile

lock_path = Path("pyodide-lock.json")
upc = UvPipCompile(
    #: path to a ``pyodide-lock.json`` to use as a baseline
    input_path=lock_path,  # required
    #: the URL for the folder containg the lockfile; if unset, assume files are local
    input_base_url="https://cdn.jsdelivr.net/pyodide/v0.29.0/full",
    #: list of PEP-508 specs to include when solving
    specs=["some-neat-pure-python-package ==1.2.3"],
    #: list of local wheels to include when solving
    wheels=[Path("to/some_local.whl")],
)
lock_spec = upc.update()
```

This will:

- use the lockfile to constrain `uv pip compile` with the given overrides
- download all requested wheels missing from the lockfile
- update the lockfile with new wheel metadata

Downloading and metadata gathering can be modified with optional arguments.

</details>

## License

BSD-3-Clause License
