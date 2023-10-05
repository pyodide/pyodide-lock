import zipfile
from pathlib import Path

import pytest

from pyodide_lock import PackageSpec
from pyodide_lock.utils import (
    _generate_package_hash,
    add_wheels_to_spec,
)

# we test if our own wheel imports nicely
# so check if it is built in /dist, or else skip that test
HERE = Path(__file__).parent
DIST = HERE.parent / "dist"
WHEEL = next(DIST.glob("*.whl")) if DIST.exists() else None


def test_add_one(test_wheel_list, example_lock_spec):
    add_wheels_to_spec(example_lock_spec, test_wheel_list[0:1])
    # py_one only should get added
    assert example_lock_spec.packages["py-one"].imports == ["one"]


def test_add_simple_deps(test_wheel_list, example_lock_spec):
    add_wheels_to_spec(example_lock_spec, test_wheel_list[0:3])
    # py_one, needs_one and needs_one_opt should get added
    assert "py-one" in example_lock_spec.packages
    assert "needs-one" in example_lock_spec.packages
    assert "needs-one-opt" in example_lock_spec.packages
    # needs one opt should not depend on py_one
    assert example_lock_spec.packages["needs-one-opt"].depends == []
    # needs one should depend on py_one
    assert example_lock_spec.packages["needs-one"].depends == ["py-one"]


def test_add_deps_with_extras(test_wheel_list, example_lock_spec):
    add_wheels_to_spec(example_lock_spec, test_wheel_list[0:4])
    # py_one, needs_one, needs_one_opt and test_extra_dependencies should get added
    # because of the extra dependency in test_extra_dependencies,
    # needs_one_opt should now depend on one
    assert "test-extra-dependencies" in example_lock_spec.packages
    assert example_lock_spec.packages["needs-one-opt"].depends == ["py-one"]


def test_missing_dep(test_wheel_list, example_lock_spec):
    # this has a package with a missing dependency so should fail
    with pytest.raises(RuntimeError):
        add_wheels_to_spec(example_lock_spec, test_wheel_list[0:5])


def test_url_rewriting(test_wheel_list, example_lock_spec):
    add_wheels_to_spec(
        example_lock_spec, test_wheel_list[0:3], base_url="http://www.nowhere.org/"
    )
    # py_one, needs_one and needs_one_opt should get added
    assert "py-one" in example_lock_spec.packages
    assert "needs-one" in example_lock_spec.packages
    assert "needs-one-opt" in example_lock_spec.packages
    assert example_lock_spec.packages["py-one"].file_name.startswith(
        "http://www.nowhere.org/py_one"
    )


def test_base_relative_path(test_wheel_list, example_lock_spec):
    # this should make all the file names relative to the
    # parent path of the wheels (which is "dist")
    add_wheels_to_spec(
        example_lock_spec,
        test_wheel_list[0:3],
        base_url="http://www.nowhere.org/",
        base_path=test_wheel_list[0].parent.parent,
    )
    # py_one, needs_one and needs_one_opt should get added
    assert "py-one" in example_lock_spec.packages
    assert "needs-one" in example_lock_spec.packages
    assert "needs-one-opt" in example_lock_spec.packages
    assert example_lock_spec.packages["needs-one-opt"].file_name.startswith(
        "http://www.nowhere.org/dist/nEEds"
    )


# all requirements markers should not be needed, so dependencies should be empty
def test_markers_not_needed(test_wheel_list, example_lock_spec):
    add_wheels_to_spec(example_lock_spec, test_wheel_list[5:6])
    assert example_lock_spec.packages["markers-not-needed-test"].depends == []


# all requirements markers should be needed,
# so returned dependencies should be the same length as marker_examples_needed
def test_markers_needed(test_wheel_list, example_lock_spec, marker_examples_needed):
    add_wheels_to_spec(
        example_lock_spec, test_wheel_list[6:7], ignore_missing_dependencies=True
    )
    assert len(example_lock_spec.packages["markers-needed-test"].depends) == len(
        marker_examples_needed
    )


@pytest.mark.skipif(WHEEL is None, reason="wheel test requires a built wheel")
def test_self_wheel(example_lock_spec):
    assert WHEEL is not None
    add_wheels_to_spec(example_lock_spec, [WHEEL], ignore_missing_dependencies=True)

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

    assert example_lock_spec.packages["pyodide-lock"] == expected


def test_not_wheel(tmp_path, example_lock_spec):
    wheel = tmp_path / "not_a_wheel-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as whlzip:
        whlzip.writestr("README.md", data="Not a wheel")

    with pytest.raises(RuntimeError, match="metadata"):
        add_wheels_to_spec(example_lock_spec, [wheel])


@pytest.mark.parametrize(
    "bad_name",
    [
        "bad-filename-for-a-wheel-1.0.0-py3-none-any.whl",
        "bad_version_for_a_wheel-a.0.0-py3-none-any.whl",
    ],
)
def test_bad_names(tmp_path, bad_name, example_lock_spec):
    wheel = tmp_path / bad_name
    with zipfile.ZipFile(wheel, "w") as whlzip:
        whlzip.writestr("README.md", data="Not a wheel")
    with pytest.raises(RuntimeError, match="Wheel filename"):
        add_wheels_to_spec(example_lock_spec, [wheel])
