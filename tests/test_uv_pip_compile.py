"""Test updating a ``pyodide-lock.json`` with ``uv pip compile``.

These tests are fairly heavy when run for the first time, relying on:
- ``uv`` is installed
- `PyPI<https://pypi.org>`_ is reachable
"""

import json
import shutil
from difflib import unified_diff
from pathlib import Path
from typing import Any
from urllib import request

import pytest

from pyodide_lock.utils import logger
from pyodide_lock.uv_pip_compile import UvPipCompile

HERE = Path(__file__).parent
ROOT = HERE.parent
DIST = (ROOT / "dist").resolve()
WHEELS = [] if not DIST.exists() else sorted(DIST.glob("*.whl"))
WHEEL = WHEELS[-1] if WHEELS else None

#: kwargs to keep when attempting a rebuild
PRESERVE_ON_REBUILD = {
    "debug",
    "extra_uv_args",
    "input_base_url",
    "preserve_url_prefixes",
    "use_base_url_for_missing",
    "wheel_dir",
}

BASE_URL_0290 = "https://cdn.jsdelivr.net/pyodide/v0.29.0/full"
LOCK_URL_0290 = f"{BASE_URL_0290}/pyodide-lock.json"
COMMON_0290 = {
    "extra_uv_args": [
        # date as of writing these test cases
        "--exclude-newer=2026-01-25"
    ],
    "input_base_url": BASE_URL_0290,
    "allow_python_download": True,
    "debug": True,
}

OLD_SELF_SPEC = "pyodide-lock[wheel] <0.1.1"

TEST_CASES: dict[
    str,
    tuple[
        # args
        dict[str, Any],
        # expected new wheels by canonical name
        list[str],
    ],
] = {
    # Pyodide 0.29.0 did not include ``pyodide-lock``
    "0.29.0-add-pkg-by-spec": (
        {"specs": [OLD_SELF_SPEC], **COMMON_0290},
        ["pyodide-lock", "pkginfo"],
    ),
    # Pyodide 0.29.0 shipped ``ipython 9.0.2``
    "0.29.0-replace-distro-pkg": (
        {"specs": ["IPython==9.9.0"], **COMMON_0290},
        ["ipython", "ipython-pygments-lexers"],
    ),
    # Exclude known depenedncies
    "0.29.0-remove-deps": (
        {
            "specs": ["ipywidgets"],
            "excludes": ["widgetsnbextension", "jupyterlab-widgets"],
            **COMMON_0290,
        },
        ["ipywidgets", "comm", "ipython-pygments-lexers"],
    ),
    # replace all local wheels, leaving empty ``wheel_dir``
    "0.29.0-add-pkg-by-spec-use-cdn": (
        {
            "specs": [OLD_SELF_SPEC],
            "preserve_url_prefixes": ["https://"],
            **COMMON_0290,
        },
        [],
    ),
    # replace all missing local wheels
    "0.29.0-use-all-cdn": (
        {
            "base_url_for_missing": BASE_URL_0290,
            **COMMON_0290,
        },
        [],
    ),
}

if WHEEL and WHEEL.is_file():
    TEST_CASES["0.29.0-add-pkg-by-whl"] = (
        {"wheels": [WHEEL], **COMMON_0290},
        ["pyodide-lock"],
    )
    TEST_CASES["0.29.0-add-whl-by-constraint"] = (
        {
            "specs": ["pyodide-lock[wheel]"],
            "constraints": [f"pyodide-lock @ {WHEEL.as_uri()}"],
            **COMMON_0290,
        },
        ["pyodide-lock", "pkginfo"],
    )


@pytest.mark.parametrize("test_case", [*TEST_CASES])
def test_uv_pip_compile(test_case: str, tmp_path: Path) -> None:
    """Verify ``uv pip compile`` provides expected outcome."""
    kwargs, expect_wheel_for = TEST_CASES[test_case]
    dist = tmp_path / "pyodide-distribution"
    dist.mkdir()
    input_path = dist / "pyodide-lock.json"
    output_path = dist / "pyodide-lock-uv-pip-compile.json"
    request.urlretrieve(LOCK_URL_0290, input_path)
    wheel_dir = dist / "from-uv-pip-compile"

    base_kwargs = {
        "input_path": input_path,
        "output_path": output_path,
        "wheel_dir": wheel_dir,
    }

    # run the build
    upc = UvPipCompile(**base_kwargs, **kwargs)
    upc.update()
    raw_lock = json.loads(output_path.read_text(encoding="utf-8"))
    diff = len(diff_json(input_path, output_path))
    assert diff, "expected some change"

    # check the build
    for pkg in expect_wheel_for:
        fname = raw_lock["packages"][pkg]["file_name"]
        assert (dist / f"{fname}").exists()
    found_wheels = sorted(wheel_dir.glob("*"))
    assert len(found_wheels) == len(expect_wheel_for), "unexpected wheels after lock"

    # prepare an in-place, offline re-run
    backup_output_path = output_path.parent / f"backup-{output_path.name}"
    shutil.copy2(output_path, backup_output_path)

    # copy reproducibility kwargs
    relock_kwargs = {k: v for k, v in kwargs.items() if k in PRESERVE_ON_REBUILD}
    relock_kwargs["extra_uv_args"] = [
        "--offline",
        *relock_kwargs.get("extra_uv_args", []),
    ]

    # run the build again, in-place
    upc = UvPipCompile(input_path=output_path, **relock_kwargs)
    upc.update()

    # verify no changes
    rebuild_diff = len(diff_json(output_path, backup_output_path))
    assert not rebuild_diff, "expected no change"


def diff_json(old: Path, new: Path) -> list[str]:
    """Log the normalized diff of two JSON files."""
    old_lines, new_lines = [
        json.dumps(json.loads(p.read_text()), indent=2, sort_keys=True).splitlines()
        for p in (old, new)
    ]
    diff_lines = [*unified_diff(old_lines, new_lines, old.name, new.name)]
    logger.debug(">>> diff\n%s", "\n".join(diff_lines))
    return diff_lines
