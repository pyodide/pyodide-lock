import json
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import build
import pytest
from test_spec import LOCK_EXAMPLE

from pyodide_lock import PyodideLockSpec


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
requires = ["setuptools", "setuptools-scm"]
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

    test_wheels: list[TestWheel] = [
        TestWheel(package_name="py-one", modules=["one"]),
        TestWheel(package_name="needs-one", deps=["py_one"]),
        TestWheel(package_name="needs-one-opt", optional_deps={"with_one": ["py-one"]}),
        TestWheel(
            package_name="test-extra-dependencies", deps=["needs-one-opt[with_one]"]
        ),
        TestWheel(package_name="failure", deps=["two"]),
    ]

    with TemporaryDirectory() as tmpdir:
        path_temp = Path(tmpdir)
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
