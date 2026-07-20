import copy
import json
from pathlib import Path
from typing import Any, Literal

import attrs
import cattrs
from attrs import define, field
from cattrs.gen import make_dict_structure_fn, make_dict_unstructure_fn, override


class SpecValidationError(ValueError):
    """Raised when a lock spec fails validation."""


@define
class InfoSpec:
    platform: str
    python: str
    arch: Literal["wasm32", "wasm64"] = "wasm32"
    # This field is deprecated and will not be included in the output
    version: str = field(default="0.0.0", metadata={"exclude": True})
    abi_version: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InfoSpec":
        return _converter.structure(data, cls)

    def to_dict(self) -> dict[str, Any]:
        return _converter.unstructure(self)


@define
class PackageSpec:
    name: str
    version: str
    #: Path (or URL) to wheel.
    file_name: str
    install_dir: str
    sha256: str = ""
    package_type: Literal[
        "package", "cpython_module", "shared_library", "static_library"
    ] = "package"
    imports: list[str] = field(factory=list)
    depends: list[str] = field(factory=list)
    unvendored_tests: bool = False
    # This field is deprecated and will not be included in the output
    shared_library: bool = field(default=False, metadata={"exclude": True})

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PackageSpec":
        return _converter.structure(data, cls)

    def to_dict(self) -> dict[str, Any]:
        return _converter.unstructure(self)


@define
class PyodideLockSpec:
    """A specification for the pyodide-lock.json file."""

    info: InfoSpec
    packages: dict[str, PackageSpec]

    @classmethod
    def from_json(cls, path: Path) -> "PyodideLockSpec":
        """Read the lock spec from a json file."""
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PyodideLockSpec":
        """Build a lock spec from a dictionary."""
        return _converter.structure(data, cls)

    def to_dict(self) -> dict[str, Any]:
        return _converter.unstructure(self)

    def clone(self) -> "PyodideLockSpec":
        """Return a deep copy of this lock spec."""
        return copy.deepcopy(self)

    def to_json(self, path: Path, indent: int | None = None) -> None:
        """Write the lock spec to a json file."""
        with path.open("w", encoding="utf-8") as fh:
            model_dict = self.to_dict()
            json_str = json.dumps(model_dict, indent=indent, sort_keys=True)
            fh.write(json_str)

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


# ---------------------------------------------------------------------------
# (de)serialization (attrs + cattrs)
# ---------------------------------------------------------------------------


def _exclude_overrides(cls: type) -> dict[str, Any]:
    return {
        f.name: override(omit=True)
        for f in attrs.fields(cls)
        if f.metadata.get("exclude")
    }


_converter = cattrs.Converter(detailed_validation=False)

for _cls in (InfoSpec, PackageSpec, PyodideLockSpec):
    _converter.register_structure_hook(
        _cls,
        make_dict_structure_fn(
            _cls,
            _converter,
            _cattrs_forbid_extra_keys=True,
        ),
    )

# Some fields are deprecated and excluded from the serialized output.
for _cls in (InfoSpec, PackageSpec):
    _converter.register_unstructure_hook(
        _cls,
        make_dict_unstructure_fn(_cls, _converter, **_exclude_overrides(_cls)),
    )
