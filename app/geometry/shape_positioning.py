import math


def haversine(lat1, lon1, lat2, lon2):
    R = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)

    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlmb/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R*c


def project_vehicle_shape_position(lat, lon, shape_points):
    """
    Retorna:
      - distância acumulada ao longo do shape (em metros)
      - ou None caso não seja possível projetar
    """

    if not shape_points or len(shape_points) < 2:
        return None

    # permite dict OU lista
    def get_latlon(p):
        if isinstance(p, dict):
            return (
                p.get("lat") or p.get("shape_pt_lat"),
                p.get("lon") or p.get("shape_pt_lon"),
            )
        return p[0], p[1]

    best_dist = None
    best_along = None
    total = 0.0

    for i in range(len(shape_points) - 1):
        p1 = get_latlon(shape_points[i])
        p2 = get_latlon(shape_points[i+1])

        seg_len = haversine(p1[0], p1[1], p2[0], p2[1])

        if seg_len == 0:
            continue

        # projeção vetorial
        # convertemos para plano aproximado
        ax = p1[1]
        ay = p1[0]
        bx = p2[1]
        by = p2[0]
        px = lon
        py = lat

        t = ((px-ax)*(bx-ax) + (py-ay)*(by-ay)) / (
            (bx-ax)**2 + (by-ay)**2
        )

        if t < 0:
            proj = p1
        elif t > 1:
            proj = p2
        else:
            proj = (ay + t*(by-ay), ax + t*(bx-ax))

        d = haversine(lat, lon, proj[0], proj[1])

        if best_dist is None or d < best_dist:
            best_dist = d
            best_along = total + t * seg_len

        total += seg_len

    #
    # tolerância generosa
    #
    if best_dist is None:
        return None

    if best_dist > 300:   # <-- aumentamos tolerância
        return None

    return best_along
