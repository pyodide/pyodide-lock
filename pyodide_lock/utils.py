import hashlib
import logging
import zipfile
from collections import deque
from pathlib import Path
from zipfile import ZipFile
from email.parser import BytesParser

from packaging.utils import canonicalize_name as canonicalize_package_name
from packaging.utils import parse_wheel_filename
from packaging.requirements import Requirement


logger = logging.getLogger(__name__)


def parse_top_level_import_name(whlfile: Path) -> list[str] | None:
    """
    Parse the top-level import names from a wheel file.

    While this behavior matches the way ``setuptools`` creates ``top_level.txt``,
    some cases, such as PEP 420 namespace packages, may not be handled correctly.
    """

    if not whlfile.name.endswith(".whl"):
        raise RuntimeError(f"{whlfile} is not a wheel file.")

    whlzip = zipfile.Path(whlfile)

    # if there is a directory with .dist_info at the end with a top_level.txt file
    # then just use that
    for subdir in whlzip.iterdir():
        if subdir.name.endswith(".dist-info"):
            top_level_path = subdir / "top_level.txt"
            if top_level_path.exists():
                return top_level_path.read_text().splitlines()

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


def get_wheel_dependencies(wheel_path: Path, pkg_name: str) -> list[str]:
    deps = []
    if not wheel_path.name.endswith(".whl"):
        raise RuntimeError(f"{wheel_path} is not a wheel file.")
    with ZipFile(wheel_path, mode="r") as wheel:
        dist_info_dir = get_wheel_dist_info_dir(wheel, pkg_name)
        metadata_path = f"{dist_info_dir}/METADATA"
        p = BytesParser()
        headers = p.parse(wheel.open(metadata_path), headersonly=True)
        requires = headers.get_all("Requires-Dist", failobj=[])
        for r in requires:
            deps.append(Requirement(r))
    return deps


def get_wheel_dist_info_dir(wheel: ZipFile, pkg_name: str) -> str:
    """Returns the path of the contained .dist-info directory.

    Raises an Exception if the directory is not found, more than
    one is found, or it does not match the provided `pkg_name`.

    Adapted from:
    https://github.com/pypa/pip/blob/ea727e4d6ab598f34f97c50a22350febc1214a97/src/pip/_internal/utils/wheel.py#L38
    """

    # Zip file path separators must be /
    subdirs = {name.split("/", 1)[0] for name in wheel.namelist()}
    info_dirs = [subdir for subdir in subdirs if subdir.endswith(".dist-info")]

    if len(info_dirs) == 0:
        raise Exception(f".dist-info directory not found for {pkg_name}")

    if len(info_dirs) > 1:
        raise Exception(
            f"multiple .dist-info directories found for {pkg_name}: {', '.join(info_dirs)}"
        )

    (info_dir,) = info_dirs

    info_dir_name = canonicalize_package_name(info_dir)
    canonical_name = canonicalize_package_name(pkg_name)

    if not info_dir_name.startswith(canonical_name):
        raise Exception(
            f".dist-info directory {info_dir!r} does not start with {canonical_name!r}"
        )

    return info_dir
