import json
import zipfile
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import build
import pytest

from pyodide_lock import PackageSpec, PyodideLockSpec
from pyodide_lock.utils import _generate_package_hash, _get_marker_environment

from .test_spec import LOCK_EXAMPLE

# we test if our own wheel imports nicely
# so check if it is built in /dist, or else skip that test
HERE = Path(__file__).parent
DIST = HERE.parent / "dist"
WHEEL = next(DIST.glob("*.whl")) if DIST.exists() else None

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
    if modules is None:
        modules = [package_name]
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


def test_add_one(test_wheel_list):
    lock_data = deepcopy(LOCK_EXAMPLE)
    spec = PyodideLockSpec(**lock_data)
    spec.add_wheels(test_wheel_list[0:1])
    # py_one only should get added
    assert spec.packages["py-one"].imports == ["one"]


def test_add_simple_deps(test_wheel_list):
    lock_data = deepcopy(LOCK_EXAMPLE)
    spec = PyodideLockSpec(**lock_data)
    spec.add_wheels(test_wheel_list[0:3])
    # py_one, needs_one and needs_one_opt should get added
    assert "py-one" in spec.packages
    assert "needs-one" in spec.packages
    assert "needs-one-opt" in spec.packages
    # needs one opt should not depend on py_one
    assert spec.packages["needs-one-opt"].depends == []
    # needs one should depend on py_one
    assert spec.packages["needs-one"].depends == ["py-one"]


def test_add_deps_with_extras(test_wheel_list):
    lock_data = deepcopy(LOCK_EXAMPLE)
    spec = PyodideLockSpec(**lock_data)
    spec.add_wheels(test_wheel_list[0:4])
    # py_one, needs_one, needs_one_opt and test_extra_dependencies should get added
    # because of the extra dependency in test_extra_dependencies,
    # needs_one_opt should now depend on one
    assert "test-extra-dependencies" in spec.packages
    assert spec.packages["needs-one-opt"].depends == ["py-one"]


def test_missing_dep(test_wheel_list):
    lock_data = deepcopy(LOCK_EXAMPLE)
    spec = PyodideLockSpec(**lock_data)
    # this has a package with a missing dependency so should fail
    with pytest.raises(RuntimeError):
        spec.add_wheels(test_wheel_list[0:5])


def test_path_rewriting(test_wheel_list):
    lock_data = deepcopy(LOCK_EXAMPLE)
    spec = PyodideLockSpec(**lock_data)
    spec.add_wheels(test_wheel_list[0:3], base_url="http://www.nowhere.org/")
    # py_one, needs_one and needs_one_opt should get added
    assert "py-one" in spec.packages
    assert "needs-one" in spec.packages
    assert "needs-one-opt" in spec.packages
    assert spec.packages["py-one"].file_name.startswith("http://www.nowhere.org/py_one")

    lock_data = deepcopy(LOCK_EXAMPLE)
    spec = PyodideLockSpec(**lock_data)
    # this should add the base path "dist" to the file name
    spec.add_wheels(
        test_wheel_list[0:3],
        base_url="http://www.nowhere.org/",
        base_path=test_wheel_list[0].parent.parent,
    )
    # py_one, needs_one and needs_one_opt should get added
    assert "py-one" in spec.packages
    assert "needs-one" in spec.packages
    assert "needs-one-opt" in spec.packages
    assert spec.packages["needs-one-opt"].file_name.startswith(
        "http://www.nowhere.org/dist/nEEds"
    )


# all requirements markers should not be needed, so dependencies should be empty
def test_markers_not_needed(test_wheel_list):
    lock_data = deepcopy(LOCK_EXAMPLE)
    spec = PyodideLockSpec(**lock_data)
    spec.add_wheels(test_wheel_list[5:6])
    assert spec.packages["markers-not-needed-test"].depends == []


# all requirements markers should be needed,
# so returned dependencies should be the same length as MARKER_EXAMPLES_NEEDED
def test_markers_needed(test_wheel_list):
    lock_data = deepcopy(LOCK_EXAMPLE)
    spec = PyodideLockSpec(**lock_data)
    spec.add_wheels(test_wheel_list[6:7], ignore_missing_dependencies=True)
    assert len(spec.packages["markers-needed-test"].depends) == len(
        MARKER_EXAMPLES_NEEDED
    )


@pytest.mark.skipif(WHEEL is None, reason="wheel test requires a built wheel")
def test_self_wheel():
    assert WHEEL is not None
    lock_data = deepcopy(LOCK_EXAMPLE)
    spec = PyodideLockSpec(**lock_data)
    spec.add_wheels([WHEEL], ignore_missing_dependencies=True)

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
    )

    assert spec.packages["pyodide-lock"] == expected


def test_not_wheel(tmp_path):
    lock_data = deepcopy(LOCK_EXAMPLE)
    spec = PyodideLockSpec(**lock_data)
    wheel = tmp_path / "not_a_wheel-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as whlzip:
        whlzip.writestr("README.md", data="Not a wheel")

    with pytest.raises(RuntimeError, match="metadata"):
        spec.add_wheels([wheel])


@pytest.mark.parametrize(
    "bad_name",
    [
        "bad-filename-for-a-wheel-1.0.0-py3-none-any.whl",
        "bad_version_for_a_wheel-a.0.0-py3-none-any.whl",
    ],
)
def test_bad_names(tmp_path, bad_name):
    lock_data = deepcopy(LOCK_EXAMPLE)
    spec = PyodideLockSpec(**lock_data)
    wheel = tmp_path / bad_name
    with zipfile.ZipFile(wheel, "w") as whlzip:
        whlzip.writestr("README.md", data="Not a wheel")
    with pytest.raises(RuntimeError, match="Wheel filename"):
        spec.add_wheels([wheel])
