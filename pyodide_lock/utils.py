import hashlib
import logging
import zipfile
from collections import deque
from pathlib import Path

logger = logging.getLogger(__name__)


def parse_top_level_import_name(whlfile: Path) -> list[str] | None:
    """
    Parse the top-level import names from a wheel file.
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
