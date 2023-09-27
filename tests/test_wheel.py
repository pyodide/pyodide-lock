import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

import pkginfo
import pytest

from pyodide_lock import PackageSpec
from pyodide_lock.utils import (
    _PYODIDE_MARKER_ENV as _ENV,
)
from pyodide_lock.utils import (
    _generate_package_hash,
    _wheel_depends,
)

if TYPE_CHECKING:
    TDepExamples = dict[tuple[str], list[str]]

HERE = Path(__file__).parent
DIST = HERE.parent / "dist"
WHEEL = next(DIST.glob("*.whl")) if DIST.exists() else None

_ENV_NUM = {k: v for k, v in _ENV.items() if v[0] in "0123456789"}

# from https://peps.python.org/pep-0508/#examples
PEP_0508_EXAMPLES: "TDepExamples" = {
    ('requests [security,tests] >= 2.8.1, == 2.8.* ; python_version < "2.7"',): [],
    ('argparse;python_version<"2.7"',): [],
}
MARKER_EXAMPLES: "TDepExamples" = {
    (f'Expected ; {k} == "{v}"',): ["expected"] for k, v in _ENV.items()
}
NOT_MARKER_EXAMPLES: "TDepExamples" = {
    (f'Not.expected ; {k} != "{v}"',): [] for k, v in _ENV.items()
}
NUM_MARKER_EXAMPLES: "TDepExamples" = {
    (f'Expected ; {k} >= "{v}"',): ["expected"] for k, v in _ENV_NUM.items()
}
NOT_NUM_MARKER_EXAMPLES: "TDepExamples" = {
    (f'Not-expected ; {k} < "{v}"',): [] for k, v in _ENV_NUM.items()
}


@pytest.mark.skipif(WHEEL is None, reason="wheel test requires a built wheel")
def test_self_wheel():
    assert WHEEL is not None

    spec = PackageSpec.from_wheel(WHEEL).json(indent=2, sort_keys=True)

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
    ).json(indent=2, sort_keys=True)

    assert spec == expected


def test_not_wheel(tmp_path):
    wheel = tmp_path / "not-a-wheel-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as whlzip:
        whlzip.writestr("README.md", data="Not a wheel")

    with pytest.raises(RuntimeError, match="metadata"):
        PackageSpec.from_wheel(wheel)


@pytest.mark.parametrize(
    "requires_dist,depends",
    [
        *PEP_0508_EXAMPLES.items(),
        *MARKER_EXAMPLES.items(),
        *NOT_MARKER_EXAMPLES.items(),
        *NUM_MARKER_EXAMPLES.items(),
        *NOT_NUM_MARKER_EXAMPLES.items(),
        # normalized names
        (("PyYAML",), ["pyyaml"]),
        (("pyyaml",), ["pyyaml"]),
        (("pyyaml", "PyYAML"), ["pyyaml"]),
        (("ruamel-yaml",), ["ruamel-yaml"]),
        (("ruamel.yaml",), ["ruamel-yaml"]),
        (("ruamel.yaml", "ruamel-yaml"), ["ruamel-yaml"]),
        (("ruamel.yaml.jinja2",), ["ruamel-yaml-jinja2"]),
    ],
)
def test_wheel_depends(requires_dist: tuple[str], depends: list[str]) -> None:
    metadata = pkginfo.Distribution()
    metadata.name = "foo"
    metadata.requires_dist = requires_dist
    assert (
        _wheel_depends(metadata) == depends
    ), f"{requires_dist} does not yield {depends}"
