import gzip
import shutil
from pathlib import Path

from typer.testing import CliRunner

from pyodide_lock.cli import main

DATA_DIR = Path(__file__).parent / "data"


runner = CliRunner()


def test_cli_modify_file(test_wheel_list, tmp_path):
    source_path = DATA_DIR / "pyodide-lock-0.23.3.json.gz"
    target_path = tmp_path / "pyodide-lock.json"
    new_lock_path = tmp_path / "pyodide-lock.json"

    with gzip.open(source_path) as fh_in:
        with target_path.open("wb") as fh_out:
            shutil.copyfileobj(fh_in, fh_out)

    result = runner.invoke(
        main,
        [
            "--input=" + str(target_path),
            "--output=" + str(new_lock_path),
            str(test_wheel_list[0]),
        ],
    )
    assert result.exit_code == 0
    assert target_path.read_text() != new_lock_path.read_text()
