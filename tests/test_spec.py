import gzip
import shutil
from copy import deepcopy
from pathlib import Path

import pytest

from pyodide_lock import PyodideLockSpec
from pyodide_lock.spec import InfoSpec, PackageSpec
from pyodide_lock.utils import update_package_sha256

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


def test_check_wheel_filenames(example_lock_data):
    spec = PyodideLockSpec(**example_lock_data)
    spec.check_wheel_filenames()

    example_lock_data["packages"]["numpy"]["name"] = "numpy2"  # type: ignore[index]
    spec = PyodideLockSpec(**example_lock_data)
    msg = (
        ".*check_wheel_filenames failed.*\n.*numpy:\n.*"
        "Package name in wheel filename 'numpy' does not match 'numpy2'"
    )
    with pytest.raises(ValueError, match=msg):
        spec.check_wheel_filenames()

    example_lock_data["packages"]["numpy"]["version"] = "0.2.3"  # type: ignore[index]
    spec = PyodideLockSpec(**example_lock_data)
    msg = (
        ".*check_wheel_filenames failed.*\n.*numpy:\n.*"
        "Package name in wheel filename 'numpy' does not match 'numpy2'\n.*"
        "Version in the wheel filename '1.24.3' does not match "
        "package version '0.2.3'"
    )
    with pytest.raises(ValueError, match=msg):
        spec.check_wheel_filenames()


def test_to_json_indent(tmp_path, example_lock_data):
    target_path = tmp_path / "pyodide-lock.json"

    spec = PyodideLockSpec(**example_lock_data)
    spec.to_json(target_path)

    assert "\n" not in target_path.read_text()

    spec.to_json(target_path, indent=0)
    assert "\n" in target_path.read_text()

    spec.to_json(target_path, indent=2)
    assert "\n" in target_path.read_text()


def test_update_sha256(monkeypatch, example_lock_data):
    monkeypatch.setattr("pyodide_lock.utils._generate_package_hash", lambda x: "abcd")

    example_lock_data["packages"]["numpy"]["sha256"] = "0"  # type: ignore[index]
    spec = PyodideLockSpec(**example_lock_data)
    assert spec.packages["numpy"].sha256 == "0"
    update_package_sha256(spec.packages["numpy"], Path("/some/path"))
    assert spec.packages["numpy"].sha256 == "abcd"


def test_extra_config_forbidden(example_lock_data):
    from pydantic import ValidationError

    info_data = deepcopy(example_lock_data["info"])
    package_data = deepcopy(
        example_lock_data["packages"]["numpy"]
    )  # type: ignore[index]

    example_lock_data["extra"] = "extra"
    info_data["extra"] = "extra"  # type: ignore[index]
    package_data["extra"] = "extra"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PyodideLockSpec(**example_lock_data)

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        InfoSpec(**info_data)  # type: ignore[arg-type]

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PackageSpec(**package_data)
