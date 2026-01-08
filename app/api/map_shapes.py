from fastapi import APIRouter
from typing import Dict, List, Tuple

from app.services.map_shapes import get_all_map_shapes

router = APIRouter(
    prefix="/map",
    tags=["map-shapes"]
)


@router.get("/shapes")
def list_map_shapes() -> Dict[str, List[Tuple[float, float]]]:
    """
    Endpoint simples que retorna:
      {
        "shape_id": [
          [lat, lon],
          ...
        ]
      }
    """

    return get_all_map_shapes()
