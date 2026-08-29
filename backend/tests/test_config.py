from app.core.config import Settings
from pydantic import ValidationError


def test_settings_validation_errors_do_not_expose_input_values() -> None:
    try:
        Settings(
            _env_file=None,
            POSTGRES_USER="configured-user",
            POSTGRES_PASSWORD="sensitive-database-password",
            POSTGRES_DB="configured-database",
            POSTGRES_PORT="not-a-number",
        )
    except ValidationError as error:
        rendered_error = str(error)
    else:
        raise AssertionError("Invalid settings should have raised ValidationError")

    assert "sensitive-database-password" not in rendered_error
    assert "input_value" not in rendered_error
