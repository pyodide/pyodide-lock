import zipfile
from pathlib import Path

import pytest

from pyodide_lock import PackageSpec
from pyodide_lock.utils import _generate_package_hash

HERE = Path(__file__).parent
DIST = HERE.parent / "dist"
WHEEL = next(DIST.glob("*.whl")) if DIST.exists() else None


@pytest.mark.skipif(WHEEL is None, reason="wheel test requires a built wheel")
def test_self_wheel():
    assert WHEEL is not None

    spec = PackageSpec.from_wheel(WHEEL).model_dump_json(indent=2)

    expected = PackageSpec(
        name="pyodide-lock",
        version=WHEEL.name.split("-")[1],
        file_name=WHEEL.name,
        install_dir="site",
        sha256=_generate_package_hash(WHEEL),
        package_type="package",
        imports=["pyodide_lock"],
        depends=["pydantic"],
        unvendored_tests=False,
        shared_library=False,
    ).model_dump_json(indent=2)

    assert spec == expected


def test_not_wheel(tmp_path):
    wheel = tmp_path / "not-a-wheel-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as whlzip:
        whlzip.writestr("README.md", data="Not a wheel")

    with pytest.raises(RuntimeError, match="metadata"):
        PackageSpec.from_wheel(wheel)
