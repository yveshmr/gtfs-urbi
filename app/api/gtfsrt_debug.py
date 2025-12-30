from fastapi import APIRouter
from google.transit import gtfs_realtime_pb2
import httpx
from app.core.config import URL_VEHICLE_REALTIME

router = APIRouter()

@router.get("/debug/gtfs-rt/raw")
def debug_gtfs_rt_raw():
    """
    Retorna todo o conteúdo do feed GTFS-RT sem nenhuma transformação.
    Único objetivo: inspecionar tudo o que o provedor envia.
    """
    feed = gtfs_realtime_pb2.FeedMessage()

    resp = httpx.get(URL_VEHICLE_REALTIME, timeout=25)
    resp.raise_for_status()

    feed.ParseFromString(resp.content)

    result = {
        "header": {},
        "entity_count": len(feed.entity),
        "entities": []
    }

    # header
    if hasattr(feed, "header"):
        hdr = feed.header
        result["header"] = {
            "gtfs_realtime_version": getattr(hdr, "gtfs_realtime_version", None),
            "incrementality": getattr(hdr, "incrementality", None),
            "timestamp": getattr(hdr, "timestamp", None),
        }

    # entities
    for e in feed.entity:
        entity_object = {
            "id": getattr(e, "id", None),
            "vehicle": {},
            "trip_update": {},
            "alert": {}
        }

        # vehicle positions
        if e.HasField("vehicle"):
            v = e.vehicle

            entity_object["vehicle"] = {
                "timestamp": getattr(v, "timestamp", None),
                "trip": {
                    "trip_id": getattr(v.trip, "trip_id", None),
                    "route_id": getattr(v.trip, "route_id", None),
                    "direction_id": getattr(v.trip, "direction_id", None),
                    "start_time": getattr(v.trip, "start_time", None),
                    "start_date": getattr(v.trip, "start_date", None),
                },
                "vehicle_descriptor": {
                    "id": getattr(v.vehicle, "id", None),
                    "label": getattr(v.vehicle, "label", None),
                    "license_plate": getattr(v.vehicle, "license_plate", None),
                },
                "position": {
                    "latitude": getattr(v.position, "latitude", None),
                    "longitude": getattr(v.position, "longitude", None),
                    "bearing": getattr(v.position, "bearing", None),
                    "speed": getattr(v.position, "speed", None),
                },
                "stop_id": getattr(v, "stop_id", None),
                "current_stop_sequence": getattr(v, "current_stop_sequence", None),
                "current_status": getattr(v, "current_status", None)
            }

        # trip update
        if e.HasField("trip_update"):
            tu = e.trip_update
            entity_object["trip_update"] = {
                "trip": {
                    "trip_id": getattr(tu.trip, "trip_id", None),
                    "route_id": getattr(tu.trip, "route_id", None),
                    "start_date": getattr(tu.trip, "start_date", None),
                    "start_time": getattr(tu.trip, "start_time", None),
                },
                "stop_time_update_count": len(tu.stop_time_update)
            }

        # alert
        if e.HasField("alert"):
            entity_object["alert"] = {"exists": True}

        result["entities"].append(entity_object)

    return result
