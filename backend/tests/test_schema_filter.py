import pytest
from app.db.schema_filter import APPLICATION_SCHEMAS, include_application_object


@pytest.mark.parametrize("schema_name", APPLICATION_SCHEMAS)
def test_alembic_includes_application_schemas(schema_name: str) -> None:
    assert include_application_object(schema_name, "schema", {})


@pytest.mark.parametrize("schema_name", [None, "public", "tiger", "topology"])
def test_alembic_excludes_external_schemas(schema_name: str | None) -> None:
    assert not include_application_object(schema_name, "schema", {})


def test_alembic_includes_tables_only_from_application_schemas() -> None:
    assert include_application_object(
        "api_responses",
        "table",
        {"schema_name": "raw"},
    )
    assert not include_application_object(
        "spatial_ref_sys",
        "table",
        {"schema_name": "public"},
    )


def test_alembic_preserves_child_objects_for_included_tables() -> None:
    assert include_application_object(
        "ix_api_responses_payload_hash",
        "index",
        {"schema_name": "raw", "table_name": "api_responses"},
    )
