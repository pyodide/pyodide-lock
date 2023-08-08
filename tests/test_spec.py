import gzip
import shutil
from copy import deepcopy
from pathlib import Path

import pytest

from pyodide_lock import PyodideLockSpec
from pyodide_lock.spec import InfoSpec, PackageSpec

DATA_DIR = Path(__file__).parent / "data"

LOCK_EXAMPLE = {
    "info": {
        "arch": "wasm32",
        "platform": "emscripten_3_1_39",
        "version": "0.24.0.dev0",
        "python": "3.11.3",
    },
    "packages": {
        "numpy": {
            "name": "numpy",
            "version": "1.24.3",
            "file_name": "numpy-1.24.3-cp311-cp311-emscripten_3_1_39_wasm32.whl",
            "install_dir": "site",
            "sha256": (
                "513af43ffb1f7d507c8d879c9f7e5" "d6c789ad21b6a67e5bca1d7cfb86bf8640f"
            ),
            "imports": ["numpy"],
            "depends": [],
        }
    },
}


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


def test_check_wheel_filenames():
    lock_data = deepcopy(LOCK_EXAMPLE)

    spec = PyodideLockSpec(**lock_data)
    spec.check_wheel_filenames()

    lock_data["packages"]["numpy"]["name"] = "numpy2"  # type: ignore[index]
    spec = PyodideLockSpec(**lock_data)
    msg = (
        ".*check_wheel_filenames failed.*\n.*numpy:\n.*"
        "Package name in wheel filename 'numpy' does not match 'numpy2'"
    )
    with pytest.raises(ValueError, match=msg):
        spec.check_wheel_filenames()

    lock_data["packages"]["numpy"]["version"] = "0.2.3"  # type: ignore[index]
    spec = PyodideLockSpec(**lock_data)
    msg = (
        ".*check_wheel_filenames failed.*\n.*numpy:\n.*"
        "Package name in wheel filename 'numpy' does not match 'numpy2'\n.*"
        "Version in the wheel filename '1.24.3' does not match "
        "package version '0.2.3'"
    )
    with pytest.raises(ValueError, match=msg):
        spec.check_wheel_filenames()


def test_to_json_indent(tmp_path):
    lock_data = deepcopy(LOCK_EXAMPLE)
    target_path = tmp_path / "pyodide-lock.json"

    spec = PyodideLockSpec(**lock_data)
    spec.to_json(target_path)

    assert "\n" not in target_path.read_text()

    spec.to_json(target_path, indent=0)
    assert "\n" in target_path.read_text()

    spec.to_json(target_path, indent=2)
    assert "\n" in target_path.read_text()


def test_update_sha256(monkeypatch):
    monkeypatch.setattr("pyodide_lock.spec._generate_package_hash", lambda x: "abcd")
    lock_data = deepcopy(LOCK_EXAMPLE)

    lock_data["packages"]["numpy"]["sha256"] = "0"  # type: ignore[index]
    spec = PyodideLockSpec(**lock_data)
    assert spec.packages["numpy"].sha256 == "0"
    spec.packages["numpy"].update_sha256(Path("/some/path"))
    assert spec.packages["numpy"].sha256 == "abcd"


def test_extra_config_forbidden():
    from pydantic import ValidationError

    lock_data = deepcopy(LOCK_EXAMPLE)
    info_data = deepcopy(lock_data["info"])
    package_data = deepcopy(lock_data["packages"]["numpy"])  # type: ignore[index]

    lock_data["extra"] = "extra"
    info_data["extra"] = "extra"  # type: ignore[index]
    package_data["extra"] = "extra"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PyodideLockSpec(**lock_data)

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        InfoSpec(**info_data)  # type: ignore[arg-type]

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PackageSpec(**package_data)
