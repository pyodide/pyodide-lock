import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .utils import (
    _generate_package_hash,
    parse_top_level_import_name,
    get_wheel_dependencies,
)


class InfoSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    arch: Literal["wasm32", "wasm64"] = "wasm32"
    platform: str
    version: str
    python: str


class PackageSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

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

    def update_sha256(self, path: Path) -> "PackageSpec":
        """Update the sha256 hash for a package."""
        self.sha256 = _generate_package_hash(path)
        return self


class PyodideLockSpec(BaseModel):
    """A specification for the pyodide-lock.json file."""

    model_config = ConfigDict(extra="forbid")

    info: InfoSpec
    packages: dict[str, PackageSpec]

    @classmethod
    def from_json(cls, path: Path) -> "PyodideLockSpec":
        """Read the lock spec from a json file."""
        with path.open("r") as fh:
            data = json.load(fh)
        return cls(**data)

    def to_json(self, path: Path, indent: int | None = None) -> None:
        """Write the lock spec to a json file."""
        with path.open("w") as fh:
            # old vs new pydantic
            if hasattr(self, "model_dump"):
                json.dump(self.model_dump(), fh, indent=indent)
            else:
                json.dump(self.dict(), fh, indent=indent)

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
            raise RuntimeError(error_msg)

    def add_wheels(
        self,
        wheel_files: list[Path],
        base_path: Path | None = None,
        base_url: str = "",
    ) -> None:
        """Add a list of wheel files to this pyodide-lock.json

        Args:
            wheel_files (list[Path]): A list of wheel files to import.
            base_path (Path | None, optional):
                Filenames are stored relative to this base path. By default the
                filename is stored relative to the path of the first wheel file
                in the list.

            base_url (str, optional):
                The base URL stored in the pyodide-lock.json. By default this is empty
                which means that wheels must be stored in the same folder as the core pyodide
                packages you are using. If you want to store your custom wheels somewhere
                else, set this base_url to point to it.
        """
        if len(wheel_files) <= 0:
            return
        if base_path == None:
            base_path = wheel_files[0].parent

        from packaging.utils import canonicalize_name
        from packaging.version import parse as version_parse

        target_python = version_parse(self.info.python)
        python_binary_tag = f"cp{target_python.major}{target_python.minor}"
        python_pure_tags = [
            f"py2.py{target_python.major}",
            f"py{target_python.major}",
            f"py{target_python.major}{target_python.minor}",
        ]

        target_platform = self.info.platform + "_" + self.info.arch

        new_packages = {}
        new_package_wheels = {}
        for f in wheel_files:
            split_name = f.stem.split("-")
            name = canonicalize_name(split_name[0])
            version = split_name[1]
            python_tag = split_name[-3]
            abi_tag = split_name[-2]
            platform_tag = split_name[-1]

            if platform_tag == "any":
                if python_tag not in python_pure_tags:
                    raise RuntimeError(
                        f"Wheel {f} is built for incorrect python version {python_tag}, this lockfile expects {python_binary_tag} or one of {python_pure_tags}"
                    )
            elif platform_tag != target_platform:
                raise RuntimeError(
                    f"Wheel {f} is built for incorrect platform {platform_tag}, this lockfile expects {target_platform}"
                )
            else:
                if python_tag != python_binary_tag:
                    raise RuntimeError(
                        f"Wheel {f} is built for incorrect python version {python_tag}, this lockfile expects {python_binary_tag}"
                    )

            file_name = base_url + str(f.relative_to(base_path))
            install_dir = "site"
            package_type = "package"
            sha256 = _generate_package_hash(f)
            imports = parse_top_level_import_name(f)

            new_packages[name] = PackageSpec(
                name=name,
                version=version,
                install_dir=install_dir,
                file_name=file_name,
                package_type=package_type,
                sha256=sha256,
                imports=imports,
                depends=[],
            )
            new_package_wheels[name] = f
        # now fix up the dependencies for each of our new packages
        # n.b. this assumes existing packages have correct dependencies,
        # which is probably a good assumption.

        requirements_with_extras = []
        for package in new_packages.values():
            # add any requirements to the list of packages
            our_depends = []
            wheel_file = new_package_wheels[package.name]
            requirements = get_wheel_dependencies(wheel_file, package.name)
            for r in requirements:
                req_marker = r.marker
                req_name = canonicalize_name(r.name)
                if req_marker is not None:
                    if not req_marker.evaluate(
                        {"sys_platform": "emscripten", "platform_system": "Emscripten"}
                    ):
                        # not used in pyodide / emscripten
                        # or optional requirement
                        continue
                if r.extras:
                    # this requirement has some extras, we need to check that the dependency package
                    # depends on whatever needs these extras also.
                    requirements_with_extras.append(r)
                if req_name in new_packages or req_name in self.packages:
                    our_depends.append(req_name)
                else:
                    raise RuntimeError(f"Requirement {req_name} is not in this distribution.")
            package.depends = our_depends

        while len(requirements_with_extras) != 0:
            extra_req = requirements_with_extras.pop()
            extra_package_name = canonicalize_name(r.name)
            if extra_package_name in new_packages:
                package = new_packages[extra_package_name]
                our_depends = package.depends
                wheel_file = new_package_wheels[package.name]
                requirements = get_wheel_dependencies(wheel_file, package.name)
                for extra in extra_req.extras:
                    for r in requirements:
                        req_marker = r.marker
                        req_name = canonicalize_name(r.name)
                        if req_marker is not None:
                            if req_marker.evaluate(
                                {
                                    "sys_platform": "emscripten",
                                    "platform_system": "Emscripten",
                                    "extra": extra,
                                }
                            ):
                                if (
                                    req_name in new_packages
                                    or req_name in self.packages
                                ):
                                    our_depends.append(req_name)
                                    if r.extras:
                                        requirements_with_extras.append(r)
                                else:
                                    raise RuntimeError(f"Requirement {req_name} is not in this distribution.")
                package.depends = our_depends
        self.packages.update(new_packages)
