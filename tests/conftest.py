import gzip
import shutil
from pathlib import Path

import pytest

HERE = Path(__file__).parent
DATA_DIR = Path(__file__).parent / "data"
SPEC_JSON_GZ = sorted(DATA_DIR.glob("*.json.gz"))


@pytest.fixture(params=SPEC_JSON_GZ)
def an_historic_spec_gz(request) -> Path:
    return request.param


@pytest.fixture
def an_historic_spec_json(tmp_path: Path, an_historic_spec_gz: Path) -> Path:
    target_path = tmp_path / "pyodide-lock.json"

    with gzip.open(an_historic_spec_gz) as fh_in:
        with target_path.open("wb") as fh_out:
            shutil.copyfileobj(fh_in, fh_out)

    return target_path
