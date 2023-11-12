from pathlib import Path

import typer

from .spec import PyodideLockSpec
from .utils import add_wheels_to_spec

main = typer.Typer(help="manipulate pyodide-lock.json lockfiles.")


@main.command()
def add_wheels(
    wheels: list[Path],
    ignore_missing_dependencies: bool = typer.Option(
        help="If this is true, dependencies "
        "which are not in the original lockfile or "
        "the added wheels will be added to the lockfile. "
        "Warning: This will allow a broken lockfile to "
        "be created.",
        default=False,
    ),
    input: Path = typer.Option(
        help="Source lockfile", default=Path("pyodide-lock.json")
    ),
    output: Path = typer.Option(
        help="Updated lockfile", default=Path("pyodide-lock-new.json")
    ),
    base_path: Path = typer.Option(
        help="Base path for wheels - wheel file "
        "names will be created relative to this path.",
        default=None,
    ),
    wheel_url: str = typer.Option(
        help="Base url which will be appended to the wheel location."
        "Use this if you are hosting these wheels on a different "
        "server to core pyodide packages",
        default="",
    ),
):
    """Add a set of package wheels to an existing pyodide-lock.json and
    write it out to pyodide-lock-new.json

    Each package in the wheel will be added to the output lockfile,
    including resolution of dependencies in the lock file. By default
    this will fail if a dependency isn't available in either the
    existing lock file, or in the set of new wheels.

    """
    sp = PyodideLockSpec.from_json(input)
    add_wheels_to_spec(
        sp,
        wheels,
        base_path=base_path,
        base_url=wheel_url,
        ignore_missing_dependencies=ignore_missing_dependencies,
    )
    sp.to_json(output)
