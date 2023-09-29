import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Extra

if TYPE_CHECKING:
    from packaging.requirements import Requirement

from .utils import (
    _generate_package_hash,
    _get_marker_environment,
    _wheel_depends,
    _wheel_metadata,
    parse_top_level_import_name,
)


class InfoSpec(BaseModel):
    arch: Literal["wasm32", "wasm64"] = "wasm32"
    platform: str
    version: str
    python: str

    class Config:
        extra = Extra.forbid


class PackageSpec(BaseModel):
    name: str
    version: str
    file_name: str
    install_dir: str
    sha256: str = ""
    package_type: Literal[
        "package", "cpython_module", "shared_library", "static_library"
    ] = "package"
    imports: list[str] = []
    depends: list[str] = []
    unvendored_tests: bool = False
    # This field is deprecated
    shared_library: bool = False

    class Config:
        extra = Extra.forbid

    @classmethod
    def _from_wheel(cls, path: Path, info: InfoSpec) -> "PackageSpec":
        """Build a package spec from an on-disk wheel.

        This is internal, because to reliably handle dependencies, we need:
          1) To have access to all the wheels being added at once (to handle extras)
          2) To know whether dependencies are available in the combined lockfile.
          3) To fix up wheel urls and paths consistently

          This is called by PyodideLockSpec.add_wheels below.
        """
        from packaging.utils import (
            InvalidWheelFilename,
            canonicalize_name,
            parse_wheel_filename,
        )
        from packaging.version import InvalidVersion
        from packaging.version import parse as version_parse

        path = path.absolute()
        # throw an error if this is an incompatible wheel
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
                f"Package tags {tags} don't match Python version in lockfile:"
                f"Lockfile python {target_python.major}.{target_python.minor}"
                f"on platform {target_platform} ({python_binary_abi})"
            )
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

    def update_sha256(self, path: Path) -> "PackageSpec":
        """Update the sha256 hash for a package."""
        self.sha256 = _generate_package_hash(path)
        return self


class PyodideLockSpec(BaseModel):
    """A specification for the pyodide-lock.json file."""

    info: InfoSpec
    packages: dict[str, PackageSpec]

    class Config:
        extra = Extra.forbid

    @classmethod
    def from_json(cls, path: Path) -> "PyodideLockSpec":
        """Read the lock spec from a json file."""
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return cls(**data)

    def to_json(self, path: Path, indent: int | None = None) -> None:
        """Write the lock spec to a json file."""
        with path.open("w", encoding="utf-8") as fh:
            fh.write(self.json(indent=indent, sort_keys=True))

    def check_wheel_filenames(self) -> None:
        """Check that the package name and version are consistent in wheel filenames"""
        from packaging.utils import (
            canonicalize_name,
            canonicalize_version,
            parse_wheel_filename,
        )

        errors: dict[str, list[str]] = {}
        for name, spec in self.packages.items():
            if not spec.file_name.endswith(".whl"):
                continue
            name_in_wheel, ver, _, _ = parse_wheel_filename(spec.file_name)
            if canonicalize_name(name_in_wheel) != canonicalize_name(spec.name):
                errors.setdefault(name, []).append(
                    f"Package name in wheel filename {name_in_wheel!r} "
                    f"does not match {spec.name!r}"
                )
            if canonicalize_version(ver) != canonicalize_version(spec.version):
                errors.setdefault(name, []).append(
                    f"Version in the wheel filename {canonicalize_version(ver)!r} "
                    f"does not match package version "
                    f"{canonicalize_version(spec.version)!r}"
                )
        if errors:
            error_msg = "check_wheel_filenames failed:\n"

            error_msg += "  - " + "\n  - ".join(
                f"{name}:\n    - " + "\n    - ".join(errs)
                for name, errs in errors.items()
            )
            raise ValueError(error_msg)

    def add_wheels(
        self,
        wheel_files: list[Path],
        base_path: Path | None = None,
        base_url: str = "",
        ignore_missing_dependencies: bool = False,
    ) -> None:
        """Add a list of wheel files to this pyodide-lock.json

        Args:
            wheel_files (list[Path]): A list of wheel files to import.
            base_path (Path | None, optional):
                Filenames are stored relative to this base path. By default the
                filename is stored relative to the path of the first wheel file
                in the list.

            base_url (str, optional):
                The base URL stored in the pyodide-lock.json. By default this
                is empty which means that wheels must be stored in the same folder
                as the core pyodide packages you are using. If you want to store
                your custom wheels somewhere else, set this base_url to point to it.
        """
        if len(wheel_files) <= 0:
            return
        wheel_files = [f.resolve() for f in wheel_files]
        if base_path is None:
            base_path = wheel_files[0].parent
        else:
            base_path = base_path.resolve()

        new_packages = {}
        for f in wheel_files:
            spec = PackageSpec._from_wheel(f, info=self.info)

            new_packages[spec.name] = spec

        self._fix_new_package_deps(new_packages, ignore_missing_dependencies)
        self._set_package_paths(new_packages, base_path, base_url)
        self.packages |= new_packages

    def _fix_new_package_deps(
        self, new_packages: dict[str, PackageSpec], ignore_missing_dependencies: bool
    ):
        # now fix up the dependencies for each of our new packages
        # n.b. this assumes existing packages have correct dependencies,
        # which is probably a good assumption.
        from packaging.utils import canonicalize_name

        requirements_with_extras = []
        marker_environment = _get_marker_environment(**self.info.dict())
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
                if req_name in new_packages or req_name in self.packages:
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
                self._fix_extra_dep(
                    extra_req, new_packages, ignore_missing_dependencies
                )
            )

    # When requirements have extras, we need to make sure that the
    # required package includes the dependencies for that extra.
    # This is because extras aren't supported in pyodide-lock
    def _fix_extra_dep(
        self,
        extra_req: "Requirement",
        new_packages: dict[str, PackageSpec],
        ignore_missing_dependencies: bool,
    ):
        from packaging.utils import canonicalize_name

        requirements_with_extras = []

        marker_environment = _get_marker_environment(**self.info.dict())
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
                        if req_name in new_packages or req_name in self.packages:
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
        self, new_packages: dict[str, PackageSpec], base_path: Path, base_url: str
    ):
        for p in new_packages.values():
            current_path = Path(p.file_name)
            relative_path = current_path.relative_to(base_path)
            p.file_name = base_url + str(relative_path)
