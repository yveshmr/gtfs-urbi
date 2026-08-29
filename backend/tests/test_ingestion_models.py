from app.models import ApiResponse, IngestionRun


def test_ingestion_run_uses_audit_schema() -> None:
    assert IngestionRun.__table__.schema == "audit"


def test_api_response_uses_raw_schema_and_audit_foreign_key() -> None:
    assert ApiResponse.__table__.schema == "raw"

    foreign_key_targets = {
        foreign_key.target_fullname for foreign_key in ApiResponse.__table__.foreign_keys
    }

    assert foreign_key_targets == {
        "audit.ingestion_runs.id",
    }
