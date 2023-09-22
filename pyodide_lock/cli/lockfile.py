import typer
from pathlib import Path
from typing import List
from typing_extensions import Annotated

from ..spec import PyodideLockSpec

main = typer.Typer()


@main.command()
def add_wheels(
    wheels: Annotated[
        List[Path],
        typer.Argument(help="list of wheels to add to the lockfile", default="[]"),
    ],
    in_lockfile: Path = Path("pyodide-lock.json"),
    out_lockfile: Path = Path("pyodide-lock-new.json"),
):
    """Add a set of wheels to an existing pyodide-lock.json"""
    sp = PyodideLockSpec.from_json(in_lockfile)
    sp.add_wheels(wheels)
    sp.to_json(out_lockfile)
