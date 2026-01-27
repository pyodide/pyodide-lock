"""Update a ``pyodide-lock.josn`` with ``uv pip compile``."""

from __future__ import annotations

import os
import shutil
import sys
import sysconfig
from logging import DEBUG
from pathlib import Path
from pprint import pformat
from subprocess import PIPE, STDOUT, Popen
from tempfile import TemporaryDirectory
from textwrap import indent
from typing import TYPE_CHECKING, Any
from urllib import parse, request

import pkginfo
from packaging.requirements import Requirement
from packaging.utils import NormalizedName, canonicalize_name
from pydantic import BaseModel, Field

from .spec import PackageSpec, PyodideLockSpec
from .utils import add_wheels_to_spec, logger

if sys.version_info >= (3, 11):  # pragma: no cover
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

if TYPE_CHECKING:
    from collections.abc import Iterator

# extra type definitions

#: a PEP-508 spec
TPep508 = str

#: a collection of normalized PEP-508 specs
TReqs = dict[NormalizedName, TPep508]

# constants

#: an environment variable
ENV_VAR_UV_BIN = "UV_BIN"

#: the magic string in ``uv`` for pyodide; it is unclear how to automate this
UV_PYODIDE_PLATFORM = "wasm32-pyodide2024"

#: URL schemes ``uv`` would be able to install
INSTALLABLE_URL_SCHEMES = {"http", "https", "file"}

#: the executable prefix for this platform
CFG_VAR_EXE = sysconfig.get_config_var("EXE")


# errors
class WheelNotFoundError(FileNotFoundError):
    """A wheel cannot be resolve to a local path."""


class UvNotFoundError(FileNotFoundError):
    """The ``uv`` binary cannot be found."""


class PyLockError(FileNotFoundError):
    """A ``pylock.toml`` was not created."""


class Pep508UrlError(ValueError):
    """A given package spec cannot be described as a PEP-508 URL."""


class InvalidPyodideLockError(RuntimeError):
    """The lockfile is invalid."""


# default factories
def _find_uv_path() -> Path | None:  # pragma: no cover
    """Locate the `uv` executable."""
    uv_bin = os.environ.get(ENV_VAR_UV_BIN)
    if not uv_bin:
        try:
            import uv

            uv_bin = uv.find_uv_bin()
        except ImportError:
            uv_bin = None

    if uv_bin:
        uv_path = Path(uv_bin)
        if uv_path.is_file():
            return uv_path

    return None


class UvPipCompile(BaseModel):
    """Update a partial Pyodide distribution with ``uv pip compile``."""

    # input/output #############################################################
    #: (required) path to a ``pyodide-lock.json`` to use as a baseline
    input_path: Path
    #: the URL for the folder containg the lockfile; if unset, assume files are local
    input_base_url: str | None = None
    #: path to a ``pyodide-lock.json`` to write; if unset, update ``input_path``
    output_path: Path | None = None
    #: path to a folder for remote wheels; if unset, put next to ``output_path``
    wheel_dir: Path | None = None
    #: indent level for output lock
    indent: int | None = None
    #: if given, preserve remote URLs starting with these prefixes
    preserve_url_prefixes: list[str] = Field(default_factory=list)

    # packages #################################################################
    #: list of PEP-508 specs to include when solving
    specs: list[str] = Field(default_factory=list)
    #: list of local wheels to include when solving
    wheels: list[Path] = Field(default_factory=list)
    #: list of PEP-508 specs to constrain when solving
    constraints: list[str] = Field(default_factory=list)
    #: list of PEP-508 specs to exclude from solving
    excludes: list[str] = Field(default_factory=list)

    # solver ###################################################################
    #: the ``uv`` python platform for pyodide
    python_platform: str = UV_PYODIDE_PLATFORM
    #: the ``uv`` binary
    uv_path: Path | None = Field(default_factory=_find_uv_path)
    #: extra arguments to ``uv pip compile``
    extra_uv_args: list[str] = Field(default_factory=list)

    # misc #####################################################################
    #: a working directory; if unset, uses a temp folder, cleaned on success
    work_dir: Path | None = None
    #: increase logging level while updating
    debug: bool | None = None

    def update(self) -> PyodideLockSpec:
        """Update a lock with ``uv pip compile``, managing logging and work folder."""
        old_log_level = logger.level
        if self.debug:
            logger.level = DEBUG
        logger.debug("Configuration: %s", indent(pformat(self), "\t"))
        try:
            if self.work_dir is None:
                with TemporaryDirectory(prefix="pyodide-lock-upc-") as work:
                    return self._update(Path(work))
            else:
                return self._update(self.work_dir)
        finally:
            logger.level = old_log_level

    def _update(self, work: Path) -> PyodideLockSpec:
        """Update a lock with ``uv pip compile``."""
        # build a validated lockfile
        lock_spec = PyodideLockSpec.from_json(self.input_path)

        # condition paths
        output_path = self.output_path or self.input_path
        wheel_dir = self.wheel_dir or output_path.parent
        wheel_dir.mkdir(parents=True, exist_ok=True)

        # build PEP-751 ``pylock.toml`` with URLs for all referenced wheels
        pylock_toml = self.pylock_toml(work, lock_spec)

        # resolve wheels
        new_wheels, new_wheel_urls = self.fetch_new_wheels(
            pylock_toml, work, wheel_dir, lock_spec
        )

        new_spec = add_wheels_to_spec(
            lock_spec=lock_spec,
            base_path=self.input_path.parent,
            wheel_files=new_wheels,
            ignore_missing_dependencies=bool(self.excludes),
        )

        self.postprocess_spec(wheel_dir, new_spec, new_wheel_urls)

        new_spec.to_json(path=output_path, indent=self.indent)
        return new_spec

    def resolve_wheel(
        self,
        info: dict[str, Any],
        work: Path,
        wheel_dir: Path,
        lock_spec: PyodideLockSpec,
    ) -> Iterator[tuple[Path, str | None]]:
        """Resolve a wheel to a path in the ``wheel_dir``."""
        archive: dict[str, Any] | None = info.get("archive")
        wheels: list[dict[str, Any]] | None = info.get("wheels")
        in_lock = lock_spec.packages.get(info["name"])
        in_lock_hash = in_lock.sha256 if in_lock else None

        if archive and "path" in archive:
            src = (work / f"""{archive["path"]}""").resolve()
            dest = (wheel_dir / src.name).resolve()
            if src == dest:  # pragma: no cover
                return
            if dest.exists():  # pragma: no cover
                dest.unlink()
            shutil.copy2(src, dest)
            yield dest, None
        elif archive and "url" in archive:
            if in_lock_hash == archive["hashes"]["sha256"]:  # pragma: no cover
                return
            yield self.fetch_wheel(wheel_dir, archive["url"])
        elif wheels:
            wheel = wheels[0]
            if in_lock_hash == wheel["hashes"]["sha256"]:  # pragma: no cover
                return
            yield self.fetch_wheel(wheel_dir, wheel["url"])
        else:  # pragma: no cover
            msg = f"The pylock.toml package entry cannot be resolved to a wheel: {info}"
            raise WheelNotFoundError(msg)

    def pylock_toml(self, work: Path, lock_spec: PyodideLockSpec) -> Pep751Toml:
        """Generate a ``pylock.toml`` from includes, constrains, and excludes."""
        requirements_in = self.requirements_in(work)
        constraints_txt = self.constraints_txt(work, requirements_in.specs, lock_spec)
        excludes_txt = self.excludes_txt(work)
        pylock_toml = work / "pylock.toml"

        uv_path = self.uv_path

        if uv_path is None:  # pragma: no cover
            msg = f"""The `uv` executable could not be found.

            Try one of:
            - ensure `pyodide-lock[uv]` is installed
            - set ${ENV_VAR_UV_BIN} to a location of `uv${CFG_VAR_EXE}`
            - providing an explicit `uv_path`
            """
            raise UvNotFoundError(msg)

        # patch version, e.g. 3.13.4 level might not be available
        python_minor = ".".join(lock_spec.info.python.split(".")[:2])

        uv_args = [
            f"{self.uv_path}",
            "pip",
            "compile",
            "--format=pylock.toml",
            "--no-build",
            f"--python-platform={self.python_platform}",
            f"--python-version={python_minor}",
            # files
            f"--output-file={pylock_toml}",
            f"--constraints={constraints_txt.path}",
            *([] if not excludes_txt else [f"--excludes={excludes_txt.path}"]),
            *self.extra_uv_args,
            f"{requirements_in.path}",
        ]

        return Pep751Toml.from_uv_pip_compile(
            path=pylock_toml,
            uv_pip_compile_args=uv_args,
        )

    def requirements_in(self, work: Path) -> Pep508Text:
        """Build ``requirements.in`` with specs by package name."""
        wheel_specs = [self.wheel_to_pep508(w) for w in self.wheels]
        return Pep508Text.from_raw_specs(
            path=work / "requirements.in",
            raw_spec_sets=[self.specs, wheel_specs],
        )

    def constraints_txt(
        self, work: Path, reqs: TReqs, lock_spec: PyodideLockSpec
    ) -> Pep508Text:
        """Build ``constraints.txt`` from ``pyodide-lock.json``, with overrides."""
        lock_constraints = [
            self.package_spec_to_pep508(p) for p in lock_spec.packages.values()
        ]
        return Pep508Text.from_raw_specs(
            path=work / "constraints.txt",
            raw_spec_sets=[lock_constraints, self.constraints],
            exclude=reqs,
        )

    def wheel_to_pep508(self, wheel: Path) -> TPep508:
        """Convert a path to an installable PEP-508 requirement."""
        meta = pkginfo.get_metadata(f"{wheel}")
        if not (meta and meta.name):  # pragma: no cover
            msg = f"Wheel metadata does not contain a name: {wheel} {meta}"
            raise Pep508UrlError(msg)
        name = canonicalize_name(meta.name)
        return f"{name} @ {wheel.as_uri()}"

    def package_spec_to_pep508(self, pkg_spec: PackageSpec) -> TPep508:
        """Convert a package spec to an installable PEP-508 requirement."""
        url: str | None = None
        file_name = pkg_spec.file_name
        pkg_url = parse.urlparse(file_name)
        pkg_name = canonicalize_name(pkg_spec.name)

        if pkg_url.scheme in INSTALLABLE_URL_SCHEMES:
            url = file_name
        elif not pkg_url.scheme:
            local = (self.input_path.parent / file_name).resolve()
            if local.exists():
                url = local.as_uri()
            elif self.input_base_url:
                url = f"{self.input_base_url}/{file_name}"

        if not url:  # pragma: no cover
            msg = f"Could not construct PEP-508 URL for {pkg_spec}"
            raise Pep508UrlError(msg)

        return f"{pkg_name} @ {url}"

    def excludes_txt(self, work: Path) -> Pep508Text | None:
        """Build ``excludes.txt`` from ``pyodide-lock.json``, with overrides."""
        if not self.excludes:
            return None

        return Pep508Text.from_raw_specs(
            path=work / "excludes.txt",
            raw_spec_sets=[self.excludes],
        )

    def fetch_new_wheels(
        self,
        pylock_toml: Pep751Toml,
        work: Path,
        wheel_dir: Path,
        lock_spec: PyodideLockSpec,
    ) -> tuple[list[Path], dict[str, str]]:
        """Fetch all new wheels."""
        new_wheels: list[Path] = []
        new_wheel_urls: dict[str, str] = {}
        for info in pylock_toml.packages.values():
            info_wheels = [*self.resolve_wheel(info, work, wheel_dir, lock_spec)]
            if info_wheels:
                wheel, url = info_wheels[0]
                new_wheels += [wheel]
                if url:
                    new_wheel_urls[canonicalize_name(info["name"])] = url

        return new_wheels, new_wheel_urls

    def fetch_wheel(self, wheel_dir: Path, url: str) -> tuple[Path, str]:
        """Fetch a wheel to the output folder."""
        parsed = parse.urlparse(url)
        dest = (wheel_dir / parsed.path.rsplit("/")[-1]).resolve()
        logger.debug("Fetching wheel %s from\n\t%s", dest.name, url)
        request.urlretrieve(url, dest)
        return dest, url

    def postprocess_spec(
        self,
        wheel_dir: Path,
        lock_spec: PyodideLockSpec,
        new_wheel_urls: dict[str, str],
    ) -> None:
        """Apply any requested post-processing to lock."""
        for exclude in map(canonicalize_name, self.excludes):
            self.remove_depends(exclude, lock_spec)

        self.validate_depends(lock_spec)

        preserve_url_prefixes = tuple(self.preserve_url_prefixes)

        if preserve_url_prefixes:
            for pkg_name, url in new_wheel_urls.items():
                if url.startswith(preserve_url_prefixes):
                    self.use_remote_wheel(lock_spec.packages[pkg_name], url, wheel_dir)

    def use_remote_wheel(
        self, pkg_spec: PackageSpec, url: str, wheel_dir: Path
    ) -> None:
        """Replace a local wheel with a remote URL."""
        local_wheel = (wheel_dir / Path(pkg_spec.file_name).name).resolve()
        logger.debug(
            "Replacing wheel for %s:\n\t%s\n\t%s", pkg_spec.name, local_wheel, url
        )
        if local_wheel.is_file():
            local_wheel.unlink()
        pkg_spec.file_name = url

    def remove_depends(self, dep_name: str, lock_spec: PyodideLockSpec) -> None:
        """Remove an excluded package from all packages' dependencies."""
        for pkg_name, pkg_spec in lock_spec.packages.items():
            if dep_name in pkg_spec.depends:
                logger.warning("Removing %s dependency on %s", pkg_name, dep_name)
                pkg_spec.depends.remove(dep_name)

    def validate_depends(self, lock_spec: PyodideLockSpec) -> None:
        """Validate all depends exist in lock spec."""
        any_missing: dict[str, list[str]] = {}
        all_pkgs = set(map(canonicalize_name, lock_spec.packages))
        for pkg_name, pkg_spec in sorted(lock_spec.packages.items()):
            missing = set(map(canonicalize_name, pkg_spec.depends)) - all_pkgs
            if missing:
                any_missing[pkg_name] = sorted(missing)

        if any_missing:
            msg = f"Missing dependencies {any_missing}"
            raise InvalidPyodideLockError(msg)


class Pep751Toml(BaseModel):
    """A PEP-751 ``pylock.toml``."""

    #: the path on disk
    path: Path

    @property
    def packages(self) -> dict[str, dict[str, Any]]:
        """Get the packages, keyed by name."""
        text = self.path.read_text(encoding="utf-8")
        logger.debug("Reading %s:\n\n%s\n\n", self.path, indent(text, "\t"))
        return {p["name"]: p for p in tomllib.loads(text).get("packages", [])}

    @classmethod
    def from_uv_pip_compile(
        cls,
        path: Path,
        uv_pip_compile_args: list[str],
    ) -> Pep751Toml:
        logger.debug(
            "Running:\n---\n%s\n---\n",
            indent("\n".join(uv_pip_compile_args), "\t"),
        )

        p = Popen(uv_pip_compile_args, stdout=PIPE, stderr=STDOUT, encoding="utf-8")
        p.wait()
        logger.warning(
            "Output:\n---\n%s\n---\n",
            indent(p.stdout.read() if p.stdout else "<no output>", "\t"),
        )
        if p.returncode:
            msg = f"""Failed to generate {path} from:
                {uv_pip_compile_args}
            """
            raise PyLockError(msg)

        return cls(path=path)


class Pep508Text(BaseModel):
    """A ``requirements.txt``-style file for requirements, constraints, excludes, etc."""

    #: the path on disk
    path: Path
    #: package specs, keyed by normalized package name
    specs: TReqs

    @property
    def text(self) -> str:
        return "\n".join(sorted(self.specs.values()))

    def write(self) -> None:
        """Write the file out to disk"""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        text = self.text
        logger.debug("Writing %s:\n\n%s\n\n", self.path, indent(text, "\t"))
        self.path.write_text(text, encoding="utf-8")

    @classmethod
    def from_raw_specs(
        cls,
        path: Path,
        raw_spec_sets: list[list[TPep508]],
        exclude: TReqs | None = None,
    ) -> Pep508Text:
        """Get canonical name/spec pairs from a list of list of specs; last wins."""
        specs: TReqs = {}
        exclude = exclude or {}

        for spec_set in raw_spec_sets:
            for spec in sorted(spec_set):
                req = Requirement(spec)
                name = canonicalize_name(req.name)
                if name not in exclude:
                    specs[name] = spec

        instance = cls(path=path, specs=specs)
        instance.write()
        return instance
