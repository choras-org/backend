import logging
import math
from typing import List, Tuple
from app.utils.geometry_utils import newell_normal_from_points

logger = logging.getLogger(__name__)

def classify_face_degeneracy(
    verts_ids: List[int],
    points: List[Tuple[float, float, float]],
    *,
    fatal_area_tol: float = 1e-12,
) -> Tuple[str, float]:
    """
    Classify polygon degeneracy using Newell area.
    Returns:
        ("ok" | "warning" | "fatal", area2)
    area2 = squared area proxy (||normal||^2)
    """

    if len(verts_ids) < 3:
        return "fatal", 0.0

    # Remove duplicate consecutive vertices
    unique = []
    seen = set()
    for vid in verts_ids:
        if vid not in seen:
            unique.append(vid)
            seen.add(vid)

    if len(unique) < 3:
        return "fatal", 0.0

    # ---- Newell normal
    nx = ny = nz = 0.0
    n = len(unique)

    for i in range(n):
        p = points[unique[i] - 1]
        q = points[unique[(i + 1) % n] - 1]

        nx += (p[1] - q[1]) * (p[2] + q[2])
        ny += (p[2] - q[2]) * (p[0] + q[0])
        nz += (p[0] - q[0]) * (p[1] + q[1])

    area2 = nx*nx + ny*ny + nz*nz  # proportional to area^2

    if area2 <= fatal_area_tol:
        return "fatal", area2

    return "ok", area2

def classify_face_planarity_m(
    face_ids,
    points,
    *,
    # meters:
    # warn at 0.1 mm, fatal at 1.0 mm
    warn_planar_tol_m=1e-4,
    fatal_planar_tol_m=1e-3,
):
    """
    Returns: (status, max_abs_dist_m, rms_dist_m)
    status:
      - "ok"
      - "warning"
      - "fatal"
      - "skip"   (triangles: always planar; degeneracy handled elsewhere)
    """
    n = len(face_ids)
    if n < 3:
        return ("fatal", float("inf"), float("inf"))

    if n == 3:
        # Triangle is always planar (if non-degenerate).
        return ("skip", 0.0, 0.0)

    max_abs, rms, _, _ = planarity_deviation_m(face_ids, points)
    if not math.isfinite(max_abs):
        return ("fatal", max_abs, rms)
    if max_abs > fatal_planar_tol_m:
        return ("fatal", max_abs, rms)
    if max_abs > warn_planar_tol_m:
        return ("warning", max_abs, rms)
    return ("ok", max_abs, rms)

def planarity_deviation_m(face_ids, points, *, eps=1e-30):
    """
    Returns:
      (max_abs_dist_m, rms_dist_m, normal_unit, plane_point_centroid)
    Plane:
      - normal via Newell
      - plane through centroid of face vertices
    """
    n = len(face_ids)
    if n < 3:
        return (float("inf"), float("inf"), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))

    nrm = newell_normal_from_points(face_ids, points)
    nlen = math.sqrt(nrm[0]*nrm[0] + nrm[1]*nrm[1] + nrm[2]*nrm[2])
    if nlen <= eps:
        # collinear / degenerate -> plane undefined
        return (float("inf"), float("inf"), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))

    nu = (nrm[0]/nlen, nrm[1]/nlen, nrm[2]/nlen)

    # centroid
    cx = cy = cz = 0.0
    for vid in face_ids:
        x, y, z = points[vid - 1]
        cx += x; cy += y; cz += z
    inv = 1.0 / n
    c = (cx * inv, cy * inv, cz * inv)

    # distances
    max_abs = 0.0
    s2 = 0.0
    for vid in face_ids:
        x, y, z = points[vid - 1]
        dx = x - c[0]
        dy = y - c[1]
        dz = z - c[2]
        d = nu[0]*dx + nu[1]*dy + nu[2]*dz  # signed distance in meters
        ad = abs(d)
        if ad > max_abs:
            max_abs = ad
        s2 += d*d

    rms = math.sqrt(s2 / n)
    return (max_abs, rms, nu, c)
