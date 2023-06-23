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
