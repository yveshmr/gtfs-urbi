from app.models import GtfsFeed, GtfsShape, GtfsShapeSegment, GtfsStopTime, GtfsTrip


def test_gtfs_models_use_core_schema() -> None:
    assert GtfsFeed.__table__.schema == "core"
    assert GtfsShape.__table__.schema == "core"
    assert GtfsTrip.__table__.schema == "core"
    assert GtfsStopTime.__table__.schema == "core"


def test_gtfs_trip_references_versioned_route_service_and_shape() -> None:
    targets = {foreign_key.target_fullname for foreign_key in GtfsTrip.__table__.foreign_keys}

    assert "core.gtfs_routes.feed_id" in targets
    assert "core.gtfs_routes.route_id" in targets
    assert "core.gtfs_services.feed_id" in targets
    assert "core.gtfs_services.service_id" in targets
    assert "core.gtfs_shapes.feed_id" in targets
    assert "core.gtfs_shapes.shape_id" in targets


def test_gtfs_trip_materializes_start_time_for_exact_correlation() -> None:
    assert "start_seconds" in GtfsTrip.__table__.columns
    correlation_index = next(
        index for index in GtfsTrip.__table__.indexes if index.name == "ix_gtfs_trips_correlation"
    )
    assert [column.name for column in correlation_index.columns] == [
        "feed_id",
        "route_id",
        "direction_id",
        "start_seconds",
    ]


def test_stop_times_materialize_shape_position_for_live_segment_lookup() -> None:
    columns = GtfsStopTime.__table__.c
    index = next(
        item
        for item in GtfsStopTime.__table__.indexes
        if item.name == "ix_gtfs_stop_times_trip_shape_position"
    )

    assert columns.shape_position.nullable is True
    assert columns.shape_progress_m.nullable is True
    assert columns.distance_to_shape_m.nullable is True
    assert columns.shape_projection_quality.nullable is True
    assert [column.name for column in index.columns] == [
        "feed_id",
        "trip_id",
        "shape_position",
    ]
    progress_index = next(
        item
        for item in GtfsStopTime.__table__.indexes
        if item.name == "ix_gtfs_stop_times_trip_shape_progress"
    )
    assert [column.name for column in progress_index.columns] == [
        "feed_id",
        "trip_id",
        "shape_progress_m",
    ]


def test_shape_segments_materialize_distance_and_spatial_index() -> None:
    table = GtfsShapeSegment.__table__
    spatial_index = next(
        item for item in table.indexes if item.name == "ix_gtfs_shape_segments_geometry"
    )

    assert table.schema == "core"
    assert [column.name for column in table.primary_key.columns] == [
        "feed_id",
        "shape_id",
        "segment_sequence",
    ]
    assert spatial_index.dialect_options["postgresql"]["using"] == "gist"
    assert {foreign_key.target_fullname for foreign_key in table.foreign_keys} == {
        "core.gtfs_shapes.feed_id",
        "core.gtfs_shapes.shape_id",
    }
