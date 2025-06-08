from typer.testing import CliRunner

from pyodide_lock.cli import main
from pyodide_lock.spec import PyodideLockSpec

runner = CliRunner()


def test_add_wheels_cli_integration(tmp_path, example_lock_spec, test_wheel_list):
    """Test that the CLI command correctly calls add_wheels_to_spec and writes output."""
    input_file = tmp_path / "input.json"
    output_file = tmp_path / "output.json"
    example_lock_spec.to_json(input_file)

    result = runner.invoke(
        main,
        [
            str(test_wheel_list[0]),
            "--input",
            str(input_file),
            "--output",
            str(output_file),
        ],
    )

    assert result.exit_code == 0
    assert output_file.exists()

    # Verify the output file contains the added wheel
    new_spec = PyodideLockSpec.from_json(output_file)
    assert "py-one" in new_spec.packages
