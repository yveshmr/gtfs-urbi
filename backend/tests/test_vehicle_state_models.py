from app.models import VehicleCurrentState


def test_vehicle_current_state_uses_realtime_schema_and_prefix_key() -> None:
    table = VehicleCurrentState.__table__

    assert table.schema == "realtime"
    assert [column.name for column in table.primary_key.columns] == ["vehicle_prefix"]


def test_vehicle_current_state_keeps_complete_source_record_and_spatial_index() -> None:
    table = VehicleCurrentState.__table__
    index = next(
        item for item in table.indexes if item.name == "ix_vehicle_current_states_location"
    )

    assert table.c.source_data.type.__class__.__name__ == "JSONB"
    assert index.dialect_options["postgresql"]["using"] == "gist"
    assert {foreign_key.target_fullname for foreign_key in table.foreign_keys} == {
        "audit.ingestion_runs.id",
        "core.gtfs_trips.feed_id",
        "core.gtfs_trips.trip_id",
    }


def test_vehicle_current_state_has_bounded_three_sample_window() -> None:
    table = VehicleCurrentState.__table__

    assert table.c.previous_state_1.type.__class__.__name__ == "JSONB"
    assert table.c.previous_state_2.type.__class__.__name__ == "JSONB"
    assert table.c.position_sample_count.nullable is False
    assert table.c.map_match_status.nullable is False
    assert table.c.shape_progress_m.nullable is True
    assert table.c.last_boundary_stop_id.nullable is True
    assert table.c.last_boundary_projection_quality.nullable is True
    assert table.c.last_boundary_crossed_at.nullable is True
