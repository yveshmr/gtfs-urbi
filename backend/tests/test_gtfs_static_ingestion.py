import io
import zipfile

import pytest
from app.services.gtfs_static_ingestion import (
    GtfsArchive,
    parse_gtfs_date,
    parse_gtfs_time,
)


def build_minimal_gtfs_zip() -> bytes:
    files = {
        "agency.txt": (
            "agency_id,agency_name,agency_url,agency_timezone\n"
            "A,Agency,https://example.com,America/Sao_Paulo\n"
        ),
        "calendar.txt": (
            "service_id,monday,tuesday,wednesday,thursday,friday,"
            "saturday,sunday,start_date,end_date\n"
            "S,1,1,1,1,1,0,0,20260801,20260831\n"
        ),
        "calendar_dates.txt": "service_id,date,exception_type\n",
        "feed_info.txt": (
            "feed_publisher_name,feed_publisher_url,feed_lang,feed_start_date,"
            "feed_end_date,feed_version\n"
            "Publisher,https://example.com,pt-BR,20260801,20260831,v1\n"
        ),
        "routes.txt": (
            "route_id,agency_id,route_short_name,route_long_name,route_type\nR,A,0038,Route 38,3\n"
        ),
        "shapes.txt": (
            "shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\n"
            "SH,-23.0,-46.0,1\n"
            "SH,-23.1,-46.1,2\n"
        ),
        "stop_times.txt": (
            "trip_id,arrival_time,departure_time,stop_id,stop_sequence\nT,25:10:00,25:10:30,P1,1\n"
        ),
        "stops.txt": "stop_id,stop_name,stop_lat,stop_lon\nP1,Stop 1,-23.0,-46.0\n",
        "trips.txt": "route_id,service_id,trip_id,direction_id,shape_id\nR,S,T,1,SH\n",
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_gtfs_archive_reads_version_metadata() -> None:
    archive = GtfsArchive(build_minimal_gtfs_zip())

    metadata = archive.metadata()

    assert metadata.publisher_name == "Publisher"
    assert metadata.version == "v1"
    assert metadata.start_date == parse_gtfs_date("20260801")
    assert metadata.end_date == parse_gtfs_date("20260831")


def test_gtfs_time_supports_service_hours_after_midnight() -> None:
    assert parse_gtfs_time("25:10:30") == 90_630


def test_gtfs_archive_rejects_missing_required_file() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("agency.txt", "agency_id,agency_name\n")

    with pytest.raises(ValueError, match="missing required files"):
        GtfsArchive(buffer.getvalue())
