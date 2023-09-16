import hashlib
import logging
import re
import sys
import zipfile
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pkginfo import Distribution

logger = logging.getLogger(__name__)

#: the last-observed state of ``packaging.markers.default_environment`` in ``pyodide``
_PYODIDE_MARKER_ENV = {
    "implementation_name": "cpython",
    "implementation_version": "3.11.3",
    "os_name": "posix",
    "platform_machine": "wasm32",
    "platform_release": "3.1.45",
    "platform_system": "Emscripten",
    "platform_version": "#1",
    "python_full_version": "3.11.3",
    "platform_python_implementation": "CPython",
    "python_version": "3.11",
    "sys_platform": "emscripten",
}


def parse_top_level_import_name(whlfile: Path) -> list[str] | None:
    """
    Parse the top-level import names from a wheel file.

    While this behavior matches the way ``setuptools`` creates ``top_level.txt``,
    some cases, such as PEP 420 namespace packages, may not be handled correctly.
    """

    if not whlfile.name.endswith(".whl"):
        raise RuntimeError(f"{whlfile} is not a wheel file.")

    whlzip = zipfile.Path(whlfile)

    # If there is no top_level.txt file, we will find top level imports by
    # 1) a python file on a top-level directory
    # 2) a sub directory with __init__.py
    # following: https://github.com/pypa/setuptools/blob/d680efc8b4cd9aa388d07d3e298b870d26e9e04b/setuptools/discovery.py#L122
    top_level_imports = []
    for subdir in whlzip.iterdir():
        if subdir.is_file() and subdir.name.endswith(".py"):
            top_level_imports.append(subdir.name[:-3])
        elif subdir.is_dir() and _valid_package_name(subdir.name):
            if _has_python_file(subdir):
                top_level_imports.append(subdir.name)

    if not top_level_imports:
        logger.warning(
            f"WARNING: failed to parse top level import name from {whlfile}."
        )
        return None

    return top_level_imports


def _valid_package_name(dirname: str) -> bool:
    return all([invalid_chr not in dirname for invalid_chr in ".- "])


def _has_python_file(subdir: zipfile.Path) -> bool:
    queue = deque([subdir])
    while queue:
        nested_subdir = queue.pop()
        for subfile in nested_subdir.iterdir():
            if subfile.is_file() and subfile.name.endswith(".py"):
                return True
            elif subfile.is_dir() and _valid_package_name(subfile.name):
                queue.append(subfile)

    return False


def _generate_package_hash(full_path: Path) -> str:
    """Generate a sha256 hash for a package

    Examples
    --------
    >>> tmp_path = getfixture("tmp_path")
    >>> input_path = tmp_path / "a.txt"
    >>> _ = input_path.write_text("foo")
    >>> _generate_package_hash(input_path)
    '2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae'
    """
    sha256_hash = hashlib.sha256()
    with open(full_path, "rb") as f:
        while chunk := f.read(4096):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def _normalized_name(raw_name: str) -> str:
    """Get a PEP 503 normalized name for a python package.

    https://peps.python.org/pep-0503/#normalized-names
    """
    return re.sub(r"[-_.]+", "-", raw_name).lower()


def _wheel_depends(
    metadata: "Distribution", marker_env: None | dict[str, str] = None
) -> list[str]:
    """Get the normalized runtime distribution dependencies from wheel metadata.

    ``marker_env`` is an optional dictionary of platform information, used to find
    platform-specific requirments.

    An accurate enumeration can be generated inside the target pyodide environment
    such as the example below:

    .. code:

        from packaging.markers import default_environment
        print(default_enviroment())
    """
    from packaging.requirements import Requirement

    depends: list[str] = []

    env = {} if "pyodide" in sys.modules else _PYODIDE_MARKER_ENV
    env.update(marker_env or {})

    for dep_str in metadata.requires_dist:
        req = Requirement(re.sub(r";$", "", dep_str))
        if req.marker is None or req.marker.evaluate(env):
            depends += [_normalized_name(req.name)]

    return sorted(set(depends))
