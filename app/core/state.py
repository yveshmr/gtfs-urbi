from dataclasses import dataclass, field
from typing import Dict
import asyncio


@dataclass
class RuntimeState:
    stops: Dict = field(default_factory=dict)
    routes: Dict = field(default_factory=dict)
    trips: Dict = field(default_factory=dict)
    shapes: Dict = field(default_factory=dict)
    stop_times: Dict = field(default_factory=dict)
    segments: Dict = field(default_factory=dict)
    vehicles: Dict = field(default_factory=dict)

    # mapping: (route_id, direction_id) -> shape_id
    route_shapes: Dict = field(default_factory=dict)

    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


rt = RuntimeState()
