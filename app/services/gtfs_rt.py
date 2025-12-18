import requests
from google.transit import gtfs_realtime_pb2

from app.config import GTFS_RT_VEHICLE_POSITIONS_URL


def fetch_vehicle_positions():
    feed = gtfs_realtime_pb2.FeedMessage()

    resp = requests.get(GTFS_RT_VEHICLE_POSITIONS_URL, timeout=30)
    resp.raise_for_status()

    feed.ParseFromString(resp.content)
    return feed
