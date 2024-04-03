import hashlib
import logging
import re
import sys
import zipfile
from collections import deque
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING  #

from .spec import InfoSpec, PackageSpec, PyodideLockSpec

if TYPE_CHECKING:
    from packaging.requirements import Requirement
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

    # We will find top level imports by
    # 1) a python file on a top-level directory
    # 2) a sub directory with __init__.py
    # following: https://github.com/pypa/setuptools/blob/d680efc8b4cd9aa388d07d3e298b870d26e9e04b/setuptools/discovery.py#L122
    # - n.b. this is more reliable than using top-level.txt which is
    # sometimes broken
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


def _get_marker_environment(
    platform: str, version: str, arch: str, python: str
) -> dict[str, str]:
    """
    Get the marker environment for this pyodide-lock file. If running
    inside pyodide it returns the current marker environment.
    """
    if "pyodide" in sys.modules:
        from packaging.markers import default_environment

        return default_environment()
    else:
        marker_env = _PYODIDE_MARKER_ENV.copy()
        from packaging.version import parse as version_parse

        target_python = version_parse(python)
        match = re.match("([^_]+)_(.*)", platform)
        if match is not None:
            marker_env["sys_platform"] = match.group(1)
            marker_env["platform_release"] = match.group(2)
        marker_env["implementation_version"] = python
        marker_env["python_full_version"] = python
        marker_env["python_version"] = f"{target_python.major}.{target_python.minor}"
        marker_env["platform_machine"] = arch
        return marker_env


@cache
def _wheel_metadata(path: Path) -> "Distribution":
    """Cached wheel metadata to save opening the file multiple times"""
    from pkginfo import get_metadata

    metadata = get_metadata(str(path))
    return metadata


def _wheel_depends(metadata: "Distribution") -> list["Requirement"]:
    """Get distribution dependencies from wheel metadata."""
    from packaging.requirements import Requirement

    depends: list[Requirement] = []

    for dep_str in metadata.requires_dist:
        req = Requirement(dep_str)
        depends.append(req)

    return depends


def add_wheels_to_spec(
    lock_spec: PyodideLockSpec,
    wheel_files: list[Path],
    base_path: Path | None = None,
    base_url: str = "",
    ignore_missing_dependencies: bool = False,
) -> PyodideLockSpec:
    """Add a list of wheel files to this pyodide-lock.json and return a
    new PyodideLockSpec

    Parameters:
    wheel_files : list[Path]
         A list of wheel files to import.
    base_path : Path | None, optional
        Filenames are stored relative to this base path. By default the
        filename is stored relative to the path of the first wheel file
        in the list.
    base_url : str, optional
        The base URL stored in the pyodide-lock.json. By default this
        is empty which means that wheels must be stored in the same folder
        as the core pyodide packages you are using. If you want to store
        your custom wheels somewhere else, set this base_url to point to it.
    ignore_missing_dependencies: bool, optional
        If this is set to True, any dependencies not found in the lock file
        or the set of wheels being added will be added to the spec. This is
        not 100% reliable, because it ignores any extras and does not do any
        sub-dependency or version resolution.
    """
    new_spec = lock_spec.model_copy(deep=True)
    if not wheel_files:
        return new_spec
    wheel_files = [f.resolve() for f in wheel_files]
    if base_path is None:
        base_path = wheel_files[0].parent
    else:
        base_path = base_path.resolve()

    new_packages = {}
    for f in wheel_files:
        spec = package_spec_from_wheel(f, info=lock_spec.info)

        new_packages[spec.name] = spec

    _fix_new_package_deps(lock_spec, new_packages, ignore_missing_dependencies)
    _set_package_paths(new_packages, base_path, base_url)
    new_spec.packages |= new_packages
    return new_spec


def _fix_new_package_deps(
    lock_spec: PyodideLockSpec,
    new_packages: dict[str, PackageSpec],
    ignore_missing_dependencies: bool,
):
    # now fix up the dependencies for each of our new packages
    # n.b. this assumes existing packages have correct dependencies,
    # which is probably a good assumption.
    from packaging.utils import canonicalize_name

    requirements_with_extras = []
    marker_environment = _get_marker_environment(**lock_spec.info.model_dump())
    for package in new_packages.values():
        # add any requirements to the list of packages
        our_depends = []
        wheel_file = package.file_name
        metadata = _wheel_metadata(wheel_file)
        requirements = _wheel_depends(metadata)
        for r in requirements:
            req_marker = r.marker
            req_name = canonicalize_name(r.name)
            if req_marker is not None:
                if not req_marker.evaluate(marker_environment):
                    # not used in pyodide / emscripten
                    # or optional requirement
                    continue
            if r.extras:
                # this requirement has some extras, we need to check
                # that the required package depends on these extras also.
                requirements_with_extras.append(r)
            if req_name in new_packages or req_name in lock_spec.packages:
                our_depends.append(req_name)
            elif ignore_missing_dependencies:
                our_depends.append(req_name)
            else:
                raise RuntimeError(
                    f"Requirement {req_name} from {r} is not in this distribution."
                )
        package.depends = our_depends
    while len(requirements_with_extras) != 0:
        extra_req = requirements_with_extras.pop()
        requirements_with_extras.extend(
            _fix_extra_dep(
                lock_spec, extra_req, new_packages, ignore_missing_dependencies
            )
        )


# When requirements have extras, we need to make sure that the
# required package includes the dependencies for that extra.
# This is because extras aren't supported in pyodide-lock
def _fix_extra_dep(
    lock_spec: PyodideLockSpec,
    extra_req: "Requirement",
    new_packages: dict[str, PackageSpec],
    ignore_missing_dependencies: bool,
) -> list["Requirement"]:
    from packaging.utils import canonicalize_name

    requirements_with_extras = []

    marker_environment = _get_marker_environment(**lock_spec.info.model_dump())
    extra_package_name = canonicalize_name(extra_req.name)
    if extra_package_name not in new_packages:
        return []
    package = new_packages[extra_package_name]
    our_depends = package.depends
    wheel_file = package.file_name
    metadata = _wheel_metadata(wheel_file)
    requirements = _wheel_depends(metadata)
    for extra in extra_req.extras:
        this_marker_env = marker_environment.copy()
        this_marker_env["extra"] = extra

        for r in requirements:
            req_marker = r.marker
            req_name = canonicalize_name(r.name)
            if req_name not in our_depends:
                if req_marker is None:
                    # no marker - this will have been processed above
                    continue
                if req_marker.evaluate(this_marker_env):
                    if req_name in new_packages or req_name in lock_spec.packages:
                        our_depends.append(req_name)
                        if r.extras:
                            requirements_with_extras.append(r)
                    elif ignore_missing_dependencies:
                        our_depends.append(req_name)
                    else:
                        raise RuntimeError(
                            f"Requirement {req_name} is not in this distribution."
                        )
    package.depends = our_depends
    return requirements_with_extras


def _set_package_paths(
    new_packages: dict[str, PackageSpec], base_path: Path, base_url: str
):
    for p in new_packages.values():
        current_path = Path(p.file_name)
        relative_path = current_path.relative_to(base_path)
        p.file_name = base_url + str(relative_path)


def _check_wheel_compatible(path: Path, info: InfoSpec) -> None:
    from packaging.utils import (
        InvalidWheelFilename,
        parse_wheel_filename,
    )
    from packaging.version import InvalidVersion
    from packaging.version import parse as version_parse

    target_python = version_parse(info.python)
    target_platform = info.platform + "_" + info.arch
    try:
        (name, version, build_number, tags) = parse_wheel_filename(str(path.name))
    except (InvalidWheelFilename, InvalidVersion) as e:
        raise RuntimeError(f"Wheel filename {path.name} is not valid") from e
    python_binary_abi = f"cp{target_python.major}{target_python.minor}"
    tags = list(tags)

    tag_match = False
    for t in tags:
        # abi should be
        if (
            t.abi == python_binary_abi
            and t.interpreter == python_binary_abi
            and t.platform == target_platform
        ):
            tag_match = True
        elif t.abi == "none" and t.platform == "any":
            match = re.match(rf"py{target_python.major}(\d*)", t.interpreter)
            if match:
                subver = match.group(1)
                if len(subver) == 0 or int(subver) <= target_python.minor:
                    tag_match = True
    if not tag_match:
        raise RuntimeError(
            f"Package tags for {path} don't match Python version in lockfile:"
            f"Lockfile python {target_python.major}.{target_python.minor}"
            f"on platform {target_platform} ({python_binary_abi})"
        )


def package_spec_from_wheel(path: Path, info: InfoSpec) -> PackageSpec:
    """Build a package spec from an on-disk wheel.

    Warning - to reliably handle dependencies, we need:
        1) To have access to all the wheels being added at once (to handle extras)
        2) To know whether dependencies are available in the combined lockfile.
        3) To fix up wheel urls and paths consistently

        This is called by add_wheels_to_spec
    """
    from packaging.utils import (
        canonicalize_name,
    )

    path = path.absolute()
    # throw an error if this is an incompatible wheel

    _check_wheel_compatible(path, info)
    metadata = _wheel_metadata(path)

    if not metadata:
        raise RuntimeError(f"Could not parse wheel metadata from {path.name}")

    # returns a draft PackageSpec with:
    # 1) absolute path to wheel,
    # 2) empty dependency list
    return PackageSpec(
        name=canonicalize_name(metadata.name),
        version=metadata.version,
        file_name=str(path),
        sha256=_generate_package_hash(path),
        package_type="package",
        install_dir="site",
        imports=parse_top_level_import_name(path),
        depends=[],
    )


def update_package_sha256(spec: PackageSpec, path: Path) -> "PackageSpec":
    """Update the sha256 hash for a package."""
    spec.sha256 = _generate_package_hash(path)
    return spec
