import gzip
import shutil
from pathlib import Path

import pytest

from pyodide_lock import PyodideLockSpec

DATA_DIR = Path(__file__).parent / "data"


@pytest.mark.parametrize("pyodide_version", ["0.22.1", "0.23.3"])
def test_lock_spec_parsing(pyodide_version, tmp_path):
    source_path = DATA_DIR / f"pyodide-lock-{pyodide_version}.json.gz"
    target_path = tmp_path / "pyodide-lock.json"
    target2_path = tmp_path / "pyodide-lock2.json"

    with gzip.open(source_path) as fh_in:
        with target_path.open("wb") as fh_out:
            shutil.copyfileobj(fh_in, fh_out)

    spec = PyodideLockSpec.from_json(target_path)
    spec.to_json(target2_path, indent=2)

    spec2 = PyodideLockSpec.from_json(target2_path)

    assert spec.info == spec2.info
    assert set(spec.packages.keys()) == set(spec2.packages.keys())
    for key in spec.packages:
        assert spec.packages[key] == spec2.packages[key]
