from app.models import (
    SegmentCompletionObservation,
    SegmentDailyMetric5m,
    SegmentLiveMetric5m,
    SegmentProfile5m,
    SegmentProfileRefreshState,
)


def test_segment_completion_buffer_has_no_vehicle_or_position_columns() -> None:
    table = SegmentCompletionObservation.__table__

    assert table.schema == "analytics"
    assert "vehicle_prefix" not in table.c
    assert "latitude" not in table.c
    assert "longitude" not in table.c
    assert {foreign_key.target_fullname for foreign_key in table.foreign_keys} == {
        "core.gtfs_feeds.id"
    }


def test_live_segment_metric_overwrites_by_stable_metric_key() -> None:
    table = SegmentLiveMetric5m.__table__

    assert table.schema == "analytics"
    assert [column.name for column in table.primary_key.columns] == ["metric_key"]
    assert {foreign_key.target_fullname for foreign_key in table.foreign_keys} == {
        "core.gtfs_feeds.id"
    }
    assert table.c.accepted_weight.nullable is False


def test_profile_refresh_state_serializes_the_daily_refresh() -> None:
    table = SegmentProfileRefreshState.__table__

    assert [column.name for column in table.primary_key.columns] == ["profile_name"]


def test_daily_segment_metric_is_keyed_by_date_and_five_minute_slot() -> None:
    table = SegmentDailyMetric5m.__table__

    assert [column.name for column in table.primary_key.columns] == [
        "metric_key",
        "service_date",
        "slot_index",
    ]
    assert table.c.m2_seconds.nullable is False


def test_segment_profile_has_bounded_weekday_and_five_minute_slot_key() -> None:
    table = SegmentProfile5m.__table__

    assert table.schema == "analytics"
    assert [column.name for column in table.primary_key.columns] == [
        "metric_key",
        "day_type",
        "slot_index",
    ]
    assert table.c.m2_seconds.nullable is False
    assert table.c.accepted_weight.nullable is False
    assert table.c.reference_start_date.nullable is False
    assert table.c.reference_end_date.nullable is False
