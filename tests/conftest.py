import json
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import build
import pytest
from packaging.utils import canonicalize_name

from pyodide_lock import PyodideLockSpec
from pyodide_lock.utils import _get_marker_environment

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

# marker environment for testing
_ENV = _get_marker_environment(**LOCK_EXAMPLE["info"])  # type:ignore[arg-type]
# marker environment for testing, filtered only to numerical values
_ENV_NUM = {k: v for k, v in _ENV.items() if v[0] in "0123456789"}

MARKER_EXAMPLES_NOT_NEEDED = (
    [
        'requests [security,tests] >= 2.8.1, == 2.8.* ; python_version < "2.7"',
        'argparse;python_version<"2.7"',
    ]
    + [f'Not.expected ; {k} != "{v}"' for k, v in _ENV.items()]
    + [f'Not.expected ; {k} > "{v}"' for k, v in _ENV_NUM.items()]
)


MARKER_EXAMPLES_NEEDED = (
    [
        'a;python_version>="3.5"',
        'b;sys_platform=="emscripten"',
    ]
    + [f'c_{k}; {k} == "{v}"' for k, v in _ENV.items()]
    + [f'd_{k} ; {k} <= "{v}"' for k, v in _ENV_NUM.items()]
)


@pytest.fixture
def marker_examples_needed():
    return MARKER_EXAMPLES_NEEDED


@pytest.fixture
def marker_examples_not_needed():
    return MARKER_EXAMPLES_NOT_NEEDED


@pytest.fixture
def example_lock_data():
    return deepcopy(LOCK_EXAMPLE)


@pytest.fixture
def example_lock_spec():
    return PyodideLockSpec(**deepcopy(LOCK_EXAMPLE))


# build a wheel
def make_test_wheel(
    dir: Path,
    package_name: str,
    deps: list[str] | None = None,
    optional_deps: dict[str, list[str]] | None = None,
    modules: list[str] | None = None,
):
    package_dir = dir / package_name
    package_dir.mkdir()
    if not modules:
        modules = [canonicalize_name(package_name).replace("-", "_")]
    for m in modules:
        (package_dir / f"{m}.py").write_text("")
    toml = package_dir / "pyproject.toml"
    if deps is None:
        deps = []

    all_deps = json.dumps(deps)
    if optional_deps:
        all_optional_deps = "[project.optional-dependencies]\n" + "\n".join(
            [x + "=" + json.dumps(optional_deps[x]) for x in optional_deps.keys()]
        )
    else:
        all_optional_deps = ""
    toml_text = f"""
[build-system]
requires = ["setuptools"]
build-backend = "setuptools.build_meta"

[project]
name = "{package_name}"
description = "{package_name} example package"
version = "1.0.0"
authors = [
    {{ name = "Bob Jones", email = "bobjones@nowhere.nowhere" }}
]
dependencies = {
    all_deps
}

{ all_optional_deps }

"""
    toml.write_text(toml_text)
    builder = build.ProjectBuilder(package_dir)
    return Path(builder.build("wheel", dir / "dist"))


@pytest.fixture(scope="module")
def test_wheel_list():
    @dataclass
    class TestWheel:
        package_name: str
        modules: list[str] | None = None
        deps: list[str] | None = None
        optional_deps: dict[str, list[str]] | None = None

    # a set of test wheels - note that names are non-canonicalized
    # deliberately to test this
    test_wheels: list[TestWheel] = [
        TestWheel(package_name="py-one", modules=["one"]),
        TestWheel(package_name="NEeds-one", deps=["py_one"]),
        TestWheel(package_name="nEEds-one-opt", optional_deps={"with_one": ["py_One"]}),
        TestWheel(
            package_name="test-extra_dependencies", deps=["needs-one-opt[with_one]"]
        ),
        TestWheel(package_name="failure", deps=["two"]),
        TestWheel(
            package_name="markers_not_needed_test", deps=MARKER_EXAMPLES_NOT_NEEDED
        ),
        TestWheel(package_name="markers_needed_test", deps=MARKER_EXAMPLES_NEEDED),
    ]

    with TemporaryDirectory() as tmpdir:
        path_temp = Path(tmpdir)
        path_temp.mkdir(exist_ok=True)
        all_wheels = []
        for wheel_data in test_wheels:
            all_wheels.append(make_test_wheel(path_temp, **asdict(wheel_data)))
        yield all_wheels
