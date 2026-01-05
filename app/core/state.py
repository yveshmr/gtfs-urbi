from dataclasses import dataclass, field
from typing import Dict, Tuple, List
from gtfs_core.pipeline_trechos import Subtrecho
import asyncio


@dataclass
class RuntimeState:
    stops: dict = field(default_factory=dict)
    routes: dict = field(default_factory=dict)
    trips: dict = field(default_factory=dict)
    stop_times: dict = field(default_factory=dict)
    shapes: dict = field(default_factory=dict)
    vehicles: dict = field(default_factory=dict)
    route_shapes: dict = field(default_factory=dict)

    vehicle_history: dict = field(default_factory=dict)

    # 👇 NOVO — lista de subtrechos calculados pelo pipeline
    subtrechos: List[Subtrecho] = field(default_factory=list)

    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


rt = RuntimeState()
