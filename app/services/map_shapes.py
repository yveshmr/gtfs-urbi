from typing import Dict, List, Tuple
from app.core.state import rt


def normalize_point(p):
    """
    Aceita:
      • objeto com lat/lon
      • dict {"lat": .., "lon": ..}
      • tupla/lista (lat, lon)
    Retorna: (lat, lon)
    """

    # caso seja objeto (p.lat)
    if hasattr(p, "lat") and hasattr(p, "lon"):
        return (p.lat, p.lon)

    # caso dict
    if isinstance(p, dict):
        return (float(p["lat"]), float(p["lon"]))

    # caso tuple/list
    if isinstance(p, (list, tuple)) and len(p) == 2:
        return (float(p[0]), float(p[1]))

    raise ValueError(f"Formato de ponto desconhecido: {p}")


def get_all_map_shapes() -> Dict[str, List[Tuple[float, float]]]:
    """
    Expõe os shapes do runtime em formato:
      shape_id -> [(lat, lon), ...]
    """

    shapes_dict = {}

    for sid, pts in rt.shapes.items():
        shapes_dict[sid] = [normalize_point(p) for p in pts]

    return shapes_dict
