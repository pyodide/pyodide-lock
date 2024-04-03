# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

## [0.1.0a5] - 2024-04-03

### Changed

- `pydantic >= 2.0` is now required.
  [#26](https://github.com/pyodide/pyodide-lock/pull/26)

## [0.1.0a4] - 2023-11-17

### Added

- Pinned to `pydantic >=1.10.2,<2`
  [#23](https://github.com/pyodide/pyodide-lock/pull/23)

- Added `PackageSpec.from_wheel` for generating a package spec from a `.whl` file
  [#18](https://github.com/pyodide/pyodide-lock/pull/18)

- Added `parse_top_level_import_name` for finding importable names in `.whl` files
  [#17](https://github.com/pyodide/pyodide-lock/pull/17)

- Added `pyodide lockfile add_wheels` CLI command.
  [#20](https://github.com/pyodide/pyodide-lock/pull/20)

## [0.1.0a3] - 2023-09-15

### Fixed

- Fixed package home/issues URL metadata in `pyproject.toml`
  [#15](https://github.com/pyodide/pyodide-lock/pull/15)

- Fixed `PyodideLockSpec.to_json` to not add newlines to the output by default.
  [#12](https://github.com/pyodide/pyodide-lock/pull/12)

## [0.1.0a2] - 2023-07-21

### Added

 - Add `check_wheel_filenames` method to `PyodideLockSpec` that checks that the
   package name in version are consistent between the wheel filename and the
   corresponding pyodide-lock.json fields
   [#11](https://github.com/pyodide/pyodide-lock/pull/11)

## [0.1.0a1] - 2023-06-23

Initial release
