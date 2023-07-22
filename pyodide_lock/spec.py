import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Extra

from .utils import _generate_package_hash


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
        with path.open("r") as fh:
            data = json.load(fh)
        return cls(**data)

    def to_json(self, path: Path, indent: int = 0) -> None:
        """Write the lock spec to a json file."""
        with path.open("w") as fh:
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
            raise ValueError(error_msg)
