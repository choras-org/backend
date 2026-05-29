from dataclasses import dataclass
from typing import List, Tuple, Dict, Any
from shapely.geometry import Polygon
from shapely import constrained_delaunay_triangles

@dataclass
class FaceRecord:
    """
    A single polygon face with all associated metadata.
    Attributes:
        fid      : unique integer face id
        verts    : ordered list of 1-based vertex indices
        group    : OBJ group name (from the 'g' directive)
        group_material : material UUID string associated with the group (from the usemtl)
        material : material UUID string (from the Rhino3dm file)
    """
    fid:      int
    verts:    List[int]
    group:    str  = "default"
    group_material: str  = "default_group_material"
    material: str  = "unknown"

    # Convenience: iterate over edges (pairs of consecutive vertex ids)
    def edges(self):
        n = len(self.verts)
        return [(self.verts[i], self.verts[(i + 1) % n]) for i in range(n)]

    def undirected_edges(self):
        return [_uedge(u, v) for u, v in self.edges()]
    
def _uedge(u, v):
    return (u, v) if u < v else (v, u)

def remove_duplicate_faces(faces: List[FaceRecord]) -> List[FaceRecord]:
    """Remove faces whose vertex sets (regardless of order) are duplicates."""
    seen: dict = {}
    out: List[FaceRecord] = []
    for face in faces:
        key = tuple(sorted(face.verts))
        if key in seen:
            continue
        seen[key] = True
        out.append(face)
    return out

def newell_normal_from_points(face_ids, points):
    """
    face_ids: list of vertex ids (1-based)
    points: list[(x,y,z)] 0-based
    returns (nx, ny, nz) unnormalized
    """
    nx = ny = nz = 0.0
    n = len(face_ids)
    for i in range(n):
        p = points[face_ids[i] - 1]
        q = points[face_ids[(i + 1) % n] - 1]
        nx += (p[1] - q[1]) * (p[2] + q[2])
        ny += (p[2] - q[2]) * (p[0] + q[0])
        nz += (p[0] - q[0]) * (p[1] + q[1])
    return (nx, ny, nz)

# HELPER MATH

def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])

def cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )

def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]

def triangulate_face_cdt_shapely(
    face: List[int],
    points: List[Tuple[float, float, float]],
    *,
    tol: float = 1e-12,
    round_ndigits: int = 12,
) -> List[List[int]]:
    """
    Constrained Delaunay triangulation of a polygon face using Shapely 2.1+.
    face: list of vertex indices (>=3), 1-based indices into points
    points: list[(x,y,z)] 0-based; vertex id i -> points[i-1]
    Returns: list of triangles [[i,j,k], ...] with original 1-based vertex ids.
    Notes:
      - Does NOT add vertices (triangles use existing polygon vertices).
      - Polygon must be simple (non-self-intersecting) for reliable results.
    """
    if len(face) < 3:
        return []
    if len(face) == 3:
        return [face[:]]

    # --- choose projection plane (drop dominant normal axis)
    nrm = newell_normal_from_points(face, points)
    ax, ay, az = abs(nrm[0]), abs(nrm[1]), abs(nrm[2])

    if az >= ax and az >= ay:
        proj = lambda pid: (points[pid - 1][0], points[pid - 1][1])  # drop z
    elif ay >= ax and ay >= az:
        proj = lambda pid: (points[pid - 1][0], points[pid - 1][2])  # drop y
    else:
        proj = lambda pid: (points[pid - 1][1], points[pid - 1][2])  # drop x

    face_ids = face[:]
    poly2d = [proj(pid) for pid in face_ids]

    # Ensure CCW for consistency
    if area2(poly2d) < 0:
        face_ids.reverse()
        poly2d.reverse()

    # Remove consecutive duplicate points (Shapely dislikes them)
    cleaned_ids = [face_ids[0]]
    cleaned_2d = [poly2d[0]]
    for pid, p2 in zip(face_ids[1:], poly2d[1:]):
        if abs(p2[0] - cleaned_2d[-1][0]) <= tol and abs(p2[1] - cleaned_2d[-1][1]) <= tol:
            continue
        cleaned_ids.append(pid)
        cleaned_2d.append(p2)

    # If last equals first, drop last
    if len(cleaned_2d) >= 2:
        if abs(cleaned_2d[0][0] - cleaned_2d[-1][0]) <= tol and abs(cleaned_2d[0][1] - cleaned_2d[-1][1]) <= tol:
            cleaned_ids.pop()
            cleaned_2d.pop()

    if len(cleaned_ids) < 3:
        return []
    if len(cleaned_ids) == 3:
        return [cleaned_ids]

    # Map rounded 2D coords -> original vertex id (1-based)
    key = lambda x, y: (round(x, round_ndigits), round(y, round_ndigits))
    coord_to_vid = {}
    for vid, (x, y) in zip(cleaned_ids, cleaned_2d):
        coord_to_vid[key(x, y)] = vid

   

    poly = Polygon(cleaned_2d)

    # Fix minor invalidities (e.g., nearly-collinear artifacts)
    if not poly.is_valid:
        poly = poly.buffer(0)

    if poly.is_empty or (not poly.is_valid):
        return []

    # Shapely returns a GeometryCollection of triangle polygons
    tris_geom = constrained_delaunay_triangles(poly)

    geoms = getattr(tris_geom, "geoms", [])
    if not geoms:
        return []

    out: List[List[int]] = []
    for tri in geoms:
        # triangle polygon coords includes closing point == first point
        coords = list(tri.exterior.coords)
        if len(coords) < 4:
            continue
        coords = coords[:-1]  # drop closing coordinate
        if len(coords) != 3:
            continue

        vids = []
        ok = True
        for (x, y) in coords:
            vid = coord_to_vid.get(key(x, y))
            if vid is None:
                ok = False
                break
            vids.append(vid)

        if not ok or len(set(vids)) < 3:
            continue

        out.append(vids)

    return out

# Triangulation helper math
def orient(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    
def area2(poly2d):
    s = 0.0
    m = len(poly2d)
    for i in range(m):
        x1, y1 = poly2d[i]
        x2, y2 = poly2d[(i + 1) % m]
        s += x1 * y2 - x2 * y1
    return s