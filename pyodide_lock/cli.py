from pathlib import Path

import click

from .spec import PyodideLockSpec
from .utils import add_wheels_to_spec


@click.group(help="Manipulate pyodide-lock.json lockfiles.")
def main():
    """Manipulate pyodide-lock.json lockfiles."""
    pass


@main.command(short_help="Add wheels to a pyodide-lock.json lockfile.")
@click.argument(
    "wheels", nargs=-1, type=click.Path(exists=True, path_type=Path), required=True
)
@click.option(
    "--ignore-missing-dependencies",
    is_flag=True,
    default=False,
    help="If this is true, dependencies which are not in the original lockfile or "
    "the added wheels will be added to the lockfile. Warning: This will allow a broken lockfile to be created.",
)
@click.option(
    "--input",
    type=click.Path(path_type=Path),
    default=Path("pyodide-lock.json"),
    help="Source lockfile",
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    default=Path("pyodide-lock-new.json"),
    help="Updated lockfile",
)
@click.option(
    "--base-path",
    type=click.Path(path_type=Path),
    default=None,
    help="Base path for wheels - wheel file names will be created relative to this path.",
)
@click.option(
    "--wheel-url",
    type=str,
    default="",
    help="Base url which will be appended to the wheel location. "
    "Use this if you are hosting these wheels on a different server to core pyodide packages",
)
def add_wheels(
    wheels,
    ignore_missing_dependencies,
    input,
    output,
    base_path,
    wheel_url,
):
    """Add a set of package wheels to an existing pyodide-lock.json and
    write it out to pyodide-lock-new.json

    Each package in the wheel will be added to the output lockfile,
    including resolution of dependencies in the lock file. By default
    this will fail if a dependency isn't available in either the
    existing lock file, or in the set of new wheels.

    \b
    Arguments:
        WHEELS: List of paths to wheel files. (required)
    
    """
    sp = PyodideLockSpec.from_json(input)
    sp = add_wheels_to_spec(
        sp,
        wheels,
        base_path=base_path,
        base_url=wheel_url,
        ignore_missing_dependencies=ignore_missing_dependencies,
    )
    sp.to_json(output)
