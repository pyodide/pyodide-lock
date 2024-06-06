from pathlib import Path
import gzip
import shutil

DATA_DIR = Path(__file__).parent / "data"

from pyodide_lock.cli import add_wheels

def test_cli_modify_file(test_wheel_list, tmp_path):
    source_path = DATA_DIR / f"pyodide-lock-0.23.3.json.gz"
    target_path = tmp_path / "pyodide-lock.json"
    new_lock_path = tmp_path / "pyodide-lock.json"

    with gzip.open(source_path) as fh_in:
        with target_path.open("wb") as fh_out:
            shutil.copyfileobj(fh_in, fh_out)

    add_wheels(wheels=test_wheel_list, input=target_path, output=new_lock_path)
    assert target_path.read_text() != new_lock_path.read_text()

    