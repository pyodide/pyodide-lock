import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from .utils import (
    _generate_package_hash,
    _wheel_depends,
    parse_top_level_import_name,
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

    @classmethod
    def from_wheel(
        cls,
        path: Path,
        marker_env: None | dict[str, str] = None,
    ) -> "PackageSpec":
        """Build a package spec from an on-disk wheel.

        This currently assumes a "simple" noarch wheel: more complex packages
        may require further postprocessing.
        """
        import pkginfo
        from packaging.utils import canonicalize_name

        metadata = pkginfo.get_metadata(str(path))

        if not metadata:
            raise RuntimeError(f"Could not parse wheel metadata from {path.name}")

        return PackageSpec(
            name=canonicalize_name(metadata.name),
            version=metadata.version,
            file_name=path.name,
            sha256=_generate_package_hash(path),
            package_type="package",
            install_dir="site",
            imports=parse_top_level_import_name(path),
            depends=_wheel_depends(metadata, marker_env),
        )

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
            json.dump(self.model_dump(), fh, indent=indent)

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
