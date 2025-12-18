from dataclasses import dataclass, field
from typing import Dict
import asyncio

@dataclass
class RuntimeState:
    stops: Dict = field(default_factory=dict)
    vehicles: Dict = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

rt = RuntimeState()
