import zipfile

import pytest

from pyodide_lock import parse_top_level_import_name


@pytest.mark.parametrize(
    "pkg",
    [
        {
            "name": "pkg_singlefile-1.0.0-py3-none-any.whl",
            "file": "singlefile.py",
            "content": "pass\n",
            "top_level": ["singlefile"],
        },
        {
            "name": "pkg_flit-1.0.0-py3-none-any.whl",
            "file": "pkg_flit/__init__.py",
            "content": "pass\n",
            "top_level": ["pkg_flit"],
        },
        {
            "name": "pkg_ruamel_yaml_dingdong-1.0.0-py3-none-any.whl",
            "file": "pkg_ruamel/yaml/ding/dong/__init__.py",
            "content": "pass\n",
            "top_level": ["pkg_ruamel"],
        },
        {
            "name": "bad_no_python-1.0.0-py3-none-any.whl",
            "file": "no/python/README.md",
            "content": "pass\n",
            "top_level": None,
        },
        {
            "name": "bad_spaces-1.0.0-py3-none-any.whl",
            "file": "space in path/README.md",
            "content": "pass\n",
            "top_level": None,
        },
    ],
)
def test_top_level_imports(pkg, tmp_path):
    with zipfile.ZipFile(tmp_path / pkg["name"], "w") as whlzip:
        whlzip.writestr(pkg["file"], data=pkg["content"])

    top_level = parse_top_level_import_name(tmp_path / pkg["name"])
    assert top_level == pkg["top_level"]


def test_not_wheel(tmp_path):
    path = tmp_path / "pkg.zip"
    with zipfile.ZipFile(path, "w") as whlzip:
        whlzip.writestr("README.md", data="#")

    with pytest.raises(RuntimeError, match="not a wheel"):
        parse_top_level_import_name(path)
