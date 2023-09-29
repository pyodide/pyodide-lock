import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import ValidationError
from jsonschema.validators import Draft201909Validator as Validator

from pyodide_lock import PyodideLockSpec

#: a schema that constrains the schema itself for schema syntax
META_SCHEMA = {
    "type": "object",
    "required": ["description", "$id", "$schema"],
    "properties": {
        "description": {"type": "string"},
        "$id": {"type": "string", "format": "uri"},
        "$schema": {"type": "string", "format": "uri"},
        "definitions": {"patternProperties": {".*": {"required": ["description"]}}},
    },
}

FORMAT_CHECKER = Validator.FORMAT_CHECKER


@pytest.fixture
def schema() -> dict[str, Any]:
    return PyodideLockSpec.schema()


@pytest.fixture
def spec_validator(schema: dict[str, Any]) -> Validator:
    return Validator(schema, format_checker=FORMAT_CHECKER)


def test_documentation(schema: dict[str, Any]) -> None:
    meta_validator = Validator(META_SCHEMA, format_checker=FORMAT_CHECKER)
    _assert_validation_errors(meta_validator, schema)


def test_validate(an_historic_spec_json: Path, spec_validator: Validator) -> None:
    spec_json = json.loads(an_historic_spec_json.read_text(encoding="utf-8"))
    _assert_validation_errors(spec_validator, spec_json)


def _assert_validation_errors(
    validator: Validator,
    instance: dict[str, Any],
    expect_errors: list[str] | None = None,
) -> None:
    expect_errors = expect_errors or []
    expect_error_count = len(expect_errors)

    errors: list[ValidationError] = list(validator.iter_errors(instance))
    error_count = len(errors)

    print("\n".join([f"""{err.json_path}: {err.message}""" for err in errors]))

    assert error_count == expect_error_count
