import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Extra, Field

from .utils import (
    _add_required,
    _generate_package_hash,
    _wheel_depends,
    parse_top_level_import_name,
)


class InfoSpec(BaseModel):
    arch: Literal["wasm32", "wasm64"] = Field(
        default="wasm32",
        description=(
            "the short name for the compiled architecture, available in "
            "dependency markers as `platform_machine`"
        ),
    )
    platform: str = Field(
        description=(
            "the emscripten virtual machine for which this distribution is "
            " compiled, not available directly in a dependency marker: use e.g. "
            """`plaform_system == "Emscripten" and platform_release == "3.1.45"`"""
        ),
        examples=["emscripten_3_1_32", "emscripten_3_1_45"],
    )
    version: str = Field(
        description="the PEP 440 version of pyodide",
        examples=["0.24.1", "0.23.3"],
    )
    python: str = Field(
        description=(
            "the version of python for which this lockfile is valid, available in "
            "version markers as `platform_machine`"
        ),
        examples=["3.11.2", "3.11.3"],
    )

    class Config:
        extra = Extra.forbid

        schema_extra = _add_required(
            "arch",
            description=(
                "the execution environment in which the packages in this lockfile "
                "can be installed"
            ),
        )


class PackageSpec(BaseModel):
    name: str = Field(
        description="the verbatim name as found in the package's metadata",
        examples=["pyodide-lock", "PyYAML", "ruamel.yaml"],
    )
    version: str = Field(
        description="the reported version of the package",
        examples=["0.1.0", "1.0.0a0", "1.0.0a0.post1"],
    )
    file_name: str = Field(
        format="uri-reference",
        description="the URL of the file",
        examples=[
            "pyodide_lock-0.1.0-py3-none-any.whl",
            "https://files.pythonhosted.org/packages/py3/m/micropip/micropip-0.5.0-py3-none-any.whl",
        ],
    )
    install_dir: str = Field(
        default="site",
        description="the file system destination for a package's data",
        examples=["dynlib", "stdlib"],
    )
    sha256: str = Field(description="the SHA256 cryptographic hash of the file")
    package_type: Literal[
        "package", "cpython_module", "shared_library", "static_library"
    ] = Field(
        default="package",
        description="the top-level kind of content provided by this package",
    )
    imports: list[str] = Field(
        default=[],
        description=(
            "the importable names provided by this package."
            "note that PEP 420 namespace packages will likely not be correctly found."
        ),
    )
    depends: list[str] = Field(
        default=[],
        unique_items=True,
        description=(
            "package names that must be installed when this package in installed"
        ),
    )
    unvendored_tests: bool = Field(
        default=False,
        description=(
            "whether the package's tests folder have been repackaged "
            "as a separate archive"
        ),
    )
    # This field is deprecated
    shared_library: bool = Field(
        default=False,
        deprecated=True,
        description=(
            "(deprecated) whether this package is a shared library. "
            "replaced with `package_type: shared_library`"
        ),
    )

    class Config:
        extra = Extra.forbid
        schema_extra = _add_required(
            "depends",
            "imports",
            "install_dir",
            description="a single pyodide-compatible file",
        )

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

    info: InfoSpec = Field(
        description=(
            "the execution environment in which the packages in this lockfile "
            "can be installable"
        )
    )
    packages: dict[str, PackageSpec] = Field(
        default={},
        description="a set of packages keyed by name",
    )

    class Config:
        extra = Extra.forbid
        schema_extra = {
            "$schema": "https://json-schema.org/draft/2019-09/schema#",
            "$id": ("https://pyodide.org/schema/pyodide-lock/v0-lockfile.schema.json"),
            "description": (
                "a description of a viable pyodide runtime environment, "
                "as defined by pyodide-lock"
            ),
        }

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
