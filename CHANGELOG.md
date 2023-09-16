# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Added

- Adds `parse_top_level_import_name` for finding importable names in `.whl` files
  [#17](https://github.com/pyodide/pyodide-lock/pull/17)

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
