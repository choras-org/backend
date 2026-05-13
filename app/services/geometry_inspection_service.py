from __future__ import annotations
from collections import defaultdict
import logging
import math
from typing import List, Tuple, Dict, Any
from matplotlib.pylab import cross
from app.utils.geometry_utils import FaceRecord, _uedge, dot, sub, triangulate_face_cdt_shapely
from app.utils.geometry_validation_utils import classify_face_planarity_m, classify_face_degeneracy

logger = logging.getLogger(__name__)

def inspect_face_planarity_issues(
    faces: List[FaceRecord],
    unique_vertices: List[Tuple[float, float, float]],
    *,
    warn_planar_tol_m: float = 1e-4,
    fatal_planar_tol_m: float = 1e-3,
) -> List[Dict[str, Any]]:
    """
    Inspect faces for planarity issues and return problematic faces with their coordinates.

    Parameters
    ----------
    faces : List[FaceRecord]
        List of FaceRecord objects to inspect.
    unique_vertices : List[Tuple[float, float, float]]
        List of unique vertex coordinates.
    warn_planar_tol_m : float
        Warning tolerance for planarity deviation in meters.
    fatal_planar_tol_m : float
        Fatal tolerance for planarity deviation in meters.

    Returns
    -------
    List[Dict[str, Any]]
        List of dictionaries containing problematic faces:
        - "type": str - always "face"
        - "points": list[list[float]] - list of [x, y, z] coordinates for the face vertices
        - "severity": str - "medium" for warning, "high" for fatal
        - "worst_vertex_deviation": float - maximum distance from plane in meters
        - "overall_spread_deviation": float - RMS distance from plane in meters
    """
    problematic_faces = []

    for face in faces:
        status, max_dist_m, rms_dist_m = classify_face_planarity_m(
            face.verts,
            unique_vertices,
            warn_planar_tol_m=warn_planar_tol_m,
            fatal_planar_tol_m=fatal_planar_tol_m,
        )

        if status in ("warning", "fatal"):
            # Get coordinates for the face vertices
            coordinates = [unique_vertices[vid - 1] for vid in face.verts]

            severity = "medium" if status == "warning" else "high"

            face_info = {
                "type": "face",
                "points": [[coord[0], coord[1], coord[2]] for coord in coordinates],
                "severity": severity,
                "worst_vertex_deviation": max_dist_m,
                "overall_spread_deviation": rms_dist_m,
            }
            problematic_faces.append(face_info)

    return problematic_faces

def detect_boundary_edges(
    faces: List["FaceRecord"],
    unique_vertices: List[Tuple[float, float, float]],
) -> List[Dict[str, Any]]:
    """
    Detect boundary / open edges in a face set.

    A boundary edge is an undirected edge that is connected to exactly one face.

    Parameters
    ----------
    faces : list[FaceRecord]
        Face list. Each face must provide:
        - fid : int
        - verts : list[int]
          Ordered 1-based vertex ids of the face loop.
    unique_vertices : list[tuple[float, float, float]]
        List of unique vertex coordinates in meters, 0-based indexed.

    Returns
    -------
    list[dict]
        Standardized list of boundary edges. Each entry is a dict with:
        - "type": str - always "edge"
        - "points": list[list[float]] - list of two [x, y, z] coordinates for the edge endpoints
        - "severity": str - always "medium"

    Notes
    -----
    - The returned edge is undirected, so ((x1,y1,z1), (x2,y2,z2)) and ((x2,y2,z2), (x1,y1,z1)) are treated as the same edge.
    - For a valid closed watertight manifold, this function should return an empty list.
    """
    edge_to_faces: Dict[Tuple[int, int], List[int]] = defaultdict(list)

    for f in faces:
        n = len(f.verts)
        if n < 2:
            continue

        for i in range(n):
            a = f.verts[i]
            b = f.verts[(i + 1) % n]
            edge_to_faces[_uedge(a, b)].append(f.fid)

    boundary_edges: List[Dict[str, Any]] = []
    for edge, face_fids in edge_to_faces.items():
        if len(face_fids) == 1:
            a, b = edge
            coord_a = unique_vertices[a - 1]
            coord_b = unique_vertices[b - 1]
            boundary_edges.append({
                "type": "edge",
                "points": [[coord_a[0], coord_a[1], coord_a[2]], [coord_b[0], coord_b[1], coord_b[2]]],
                "severity": "medium"
            })

    return boundary_edges

def detect_degenerate_faces(
    faces: List["FaceRecord"],
    unique_vertices: List[Tuple[float, float, float]],
    *,
    fatal_area2_tol: float = 1e-16,
) -> List[Dict[str, Any]]:
    """
    Detect degenerate faces in a face set.

    A degenerate face is one classified as "fatal" by classify_face_degeneracy.

    Parameters
    ----------
    faces : list[FaceRecord]
        Face list.
    unique_vertices : list[tuple[float, float, float]]
        List of unique vertex coordinates in meters, 0-based indexed.
    fatal_area2_tol : float, optional
        Tolerance for fatal degeneracy (area squared proxy).

    Returns
    -------
    list[dict]
        Standardized list of degenerate faces. Each entry is a dict with:
        - "type": str - always "face"
        - "points": list[list[float]] - list of [x, y, z] coordinates for the face vertices
        - "severity": str - always "high"
        - "fid": int - face id
        - "area2": float - area squared proxy
        - "fatal_tol": float - tolerance used

    Notes
    -----
    - Uses classify_face_degeneracy for consistency with repair functions.
    """
    degenerate_faces: List[Dict[str, Any]] = []

    for f in faces:
        status, area2 = classify_face_degeneracy(
            f.verts,
            unique_vertices,
            fatal_area_tol=fatal_area2_tol,
        )

        if status == "fatal":
            coordinates = [unique_vertices[vid - 1] for vid in f.verts]
            degenerate_faces.append({
                "type": "face",
                "points": [[coord[0], coord[1], coord[2]] for coord in coordinates],
                "severity": "high",
                # "fid": f.fid,
                # "area2": area2,
                # "fatal_tol": fatal_area2_tol,
            })

    return degenerate_faces

def polygon_area_3d(coords: List[Tuple[float, float, float]]) -> float:
    """
    Compute the area of a 3D polygon assuming it is planar.

    Uses the shoelace formula after projecting to the best-fit plane.
    """
    if len(coords) < 3:
        return 0.0

    # Find the normal to determine projection plane
    # Use first three points
    a, b, c = coords[0], coords[1], coords[2]
    normal = cross(sub(b, a), sub(c, a))
    normal_len = math.sqrt(dot(normal, normal))
    if normal_len < 1e-12:
        # Degenerate triangle
        return 0.0
    normal = (normal[0] / normal_len, normal[1] / normal_len, normal[2] / normal_len)

    # Project to plane: choose the axis with largest normal component
    abs_normal = (abs(normal[0]), abs(normal[1]), abs(normal[2]))
    if abs_normal[0] >= abs_normal[1] and abs_normal[0] >= abs_normal[2]:
        # Project to YZ plane
        proj = lambda p: (p[1], p[2])
    elif abs_normal[1] >= abs_normal[2]:
        # Project to XZ plane
        proj = lambda p: (p[0], p[2])
    else:
        # Project to XY plane
        proj = lambda p: (p[0], p[1])

    # Shoelace
    proj_coords = [proj(p) for p in coords]
    n = len(proj_coords)
    area = 0.0
    for i in range(n):
        x1, y1 = proj_coords[i]
        x2, y2 = proj_coords[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0

def detect_possible_holes_from_faces(
    faces: List["FaceRecord"],
    unique_vertices: List[Tuple[float, float, float]],
) -> List[Dict[str, Any]]:
    """
    Detect possible holes in a model using only face topology.

    A "possible hole" here means a closed loop of boundary edges that is
    supported by more than one adjacent face overall.

    Boundary edges are edges that belong to exactly one face. Loops that are
    contributed by only a single face are usually just open face perimeters,
    not real hole candidates, so they are filtered out.

    This implementation finds all connected components of boundary edges
    and identifies those that form simple cycles (each vertex has degree 2).

    Parameters
    ----------
    faces : list[FaceRecord]
        Face list. Each face must provide an ordered vertex loop in ``face.verts``.
    unique_vertices : list[tuple[float, float, float]]
        List of unique vertex coordinates in meters, 0-based indexed.

    Returns
    -------
    list[dict]
        Standardized list of detected boundary loops. Each entry is a dict with:
        - "type": str - always "edge_loop"
        - "points": list[dict] - list of edge dicts, each with "type": "edge" and "points": list of two [x, y, z] coordinates
        - "severity": str - always "high"

    Notes
    -----
    - This is a topology-based detector only.
    - It guarantees finding all simple closed loops in isolated boundary components.
    - It does not guarantee that every loop is a real geometric hole.
    - It is still very useful for identifying open boundaries in the mesh.
    """
    edge_to_faces: Dict[Tuple[int, int], List[int]] = defaultdict(list)

    # Build edge -> adjacent face ids
    for f in faces:
        n = len(f.verts)
        if n < 2:
            continue
        for i in range(n):
            a = f.verts[i]
            b = f.verts[(i + 1) % n]
            edge_to_faces[_uedge(a, b)].append(f.fid)

    # Boundary edges = edges used by exactly one face
    boundary_edges = {e for e, adj in edge_to_faces.items() if len(adj) == 1}
    if not boundary_edges:
        return []

    # Build adjacency graph of boundary edges at vertices
    adj: Dict[int, set[int]] = defaultdict(set)
    for a, b in boundary_edges:
        adj[a].add(b)
        adj[b].add(a)

    # Find connected components
    visited = set()
    components = []
    for v in adj:
        if v not in visited:
            component = set()
            stack = [v]
            while stack:
                curr = stack.pop()
                if curr not in visited:
                    visited.add(curr)
                    component.add(curr)
                    stack.extend(adj[curr] - visited)
            components.append(component)

    loops: List[Dict[str, Any]] = []
    for comp in components:
        # Check if component is a cycle: all vertices have degree 2
        if all(len(adj[v]) == 2 for v in comp):
            comp_boundary_edges = [e for e in boundary_edges if e[0] in comp and e[1] in comp]
            adjacent_face_fids = sorted({fid for e in comp_boundary_edges for fid in edge_to_faces[e]})

            # Real hole candidates should be bounded by more than one face.
            # A loop formed entirely from one face is typically just an open
            # perimeter of that face, not a hole in the surface.
            if len(adjacent_face_fids) < 2:
                continue

            # Traverse the cycle
            start_v = min(comp)
            vertex_loop = [unique_vertices[start_v - 1]]
            edge_loop = []
            prev_v = start_v
            cur_v = next(iter(adj[start_v]))
            while cur_v != start_v:
                vertex_loop.append(unique_vertices[cur_v - 1])
                edge_loop.append((unique_vertices[prev_v - 1], unique_vertices[cur_v - 1]))
                neighbors = adj[cur_v]
                next_v = next(n for n in neighbors if n != prev_v)
                prev_v = cur_v
                cur_v = next_v
            # Close the loop
            edge_loop.append((unique_vertices[prev_v - 1], unique_vertices[cur_v - 1]))
            
            points = []
            for edge in edge_loop:
                points.append({
                    "type": "edge",
                    "points": [list(edge[0]), list(edge[1])]
                })
            
            loops.append({
                "type": "edge_loop",
                "points": points,
                "severity": "high"
            })

    return loops

def detect_faces_with_area_below_threshold(
    faces: List["FaceRecord"],
    vertices: List[Tuple[float, float, float]],
    *,
    area_threshold_m2: float = 0.001,
) -> List[Dict[str, Any]]:
    """
    Detect faces whose area is below a given threshold.

    Parameters
    ----------
    faces : list[FaceRecord]
        Face list.
    vertices : list[(x, y, z)]
        Global vertex list in meters.
    area_threshold_m2 : float, optional
        Area threshold in square meters.

        Default = 0.001 m² = 10 cm².

    Returns
    -------
    list[dict]
        One entry per small face:
        - "fid": int
        - "verts": list[int]
        - "area_m2": float
        - "threshold_m2": float

    Notes
    -----
    I assumed "10 cm" means "10 cm²" for face area.
    If you want another interpretation, just change ``area_threshold_m2``.
    """
    small_faces: List[Dict[str, Any]] = []

    for f in faces:
        area = polygon_area_3d(f.verts, vertices)
        if area < area_threshold_m2:
            small_faces.append({
                "fid": f.fid,
                "verts": f.verts[:],
                "area_m2": area,
                "threshold_m2": area_threshold_m2,
            })

    return small_faces

def detect_t_junctions_from_facerecords_global_plc(
    faces: "List[FaceRecord]",
    points: List[Tuple[float, float, float]],
    *,
    tol: float = 1e-8,
    max_reports: int = 2000,
) -> List[Dict[str, Any]]:
    """
    PLC-grade, global T-junction detection (FaceRecord-only).
    A "T-junction" here means:
      - A FACE uses an edge (u,v) on its boundary
      - There exists some vertex w that lies on segment u-v (within tol, interior)
      - AND w is NOT a vertex of that face
    This catches the exact condition that leads to Gmsh PLC errors
    like "segment and facet intersect at point".
    Returns dicts like:
      {
        "edge": (u, v),
        "edge_coordinates": [[x1, y1, z1], [x2, y2, z2]],
        "split_vertex": w,
        "split_vertex_coordinates": [xw, yw, zw],
        "t_param": t,
        "edge_face_fids": [ ...faces that use (u,v)... ],
        "culprit_face_fid": <the face that uses (u,v) but doesn't include w>,
        "v_face_fids": [ ...faces that contain w... ],
      }
    """

    def uedge(i, j):
        return (i, j) if i < j else (j, i)

    def point_on_segment_scale_correct(P, A, B, tol_):
        """
        Returns (on_segment, t) where t is param along A->B.
        Uses scale-correct distance-to-line check:
          |AB x AP|^2 <= tol^2 * |AB|^2
        """
        AB = sub(B, A)
        AP = sub(P, A)
        ab2 = dot(AB, AB)
        if ab2 <= 0.0:
            return (False, 0.0)

        cr = cross(AB, AP)
        if dot(cr, cr) > (tol_ * tol_) * ab2:
            return (False, 0.0)

        t = dot(AP, AB) / ab2
        if not (-tol_ <= t <= 1.0 + tol_):
            return (False, t)

        return (True, t)

    # Build: edge -> face indices that use the edge on their boundary
    edge_to_face_idxs = defaultdict(list)
    vert_to_face_idxs = defaultdict(list)
    edge_set = set()

    for fi, face in enumerate(faces):
        poly = face.verts
        n = len(poly)
        for v in poly:
            vert_to_face_idxs[v].append(fi)
        for i in range(n):
            a = poly[i]
            b = poly[(i + 1) % n]
            e = uedge(a, b)
            edge_set.add(e)
            edge_to_face_idxs[e].append(fi)

    all_verts = list(range(1, len(points) + 1))

    reports = []
    for (u, v) in edge_set:
        A = points[u - 1]
        B = points[v - 1]

        # faces that *actually* use this long edge
        face_idxs_using_edge = edge_to_face_idxs[uedge(u, v)]
        if not face_idxs_using_edge:
            continue

        for w in all_verts:
            if w == u or w == v:
                continue

            P = points[w - 1]
            ok, t = point_on_segment_scale_correct(P, A, B, tol)
            if not ok:
                continue

            # interior only
            if not (tol < t < 1.0 - tol):
                continue

            # If ANY face uses (u,v) but doesn't include w, that's a PLC T-junction
            culprit_fid = None
            for fi in face_idxs_using_edge:
                if w not in faces[fi].verts:
                    culprit_fid = faces[fi].fid
                    break

            if culprit_fid is None:
                # all faces that use (u,v) already include w (rare; usually (u,v) would disappear)
                continue

            edge_face_fids = [faces[fi].fid for fi in face_idxs_using_edge]
            v_face_fids = [faces[fi].fid for fi in vert_to_face_idxs.get(w, [])]

            if len(v_face_fids) > 0 :
                reports.append({
                    "edge": (u, v),
                    "edge_coordinates": [[A[0], A[1], A[2]], [B[0], B[1], B[2]]],
                    "split_vertex": w,
                    "split_vertex_coordinates": [P[0], P[1], P[2]],
                    "t_param": t,
                    "edge_face_fids": edge_face_fids,
                    "culprit_face_fid": culprit_fid,
                    "v_face_fids": v_face_fids,
                })

            if len(reports) >= max_reports:
                return reports

    return reports

def detect_duplicate_vertices(vertices: List[Tuple[float, float, float]], tol: float = 1e-2) -> List[Dict[str, Any]]:
    """
    Detect duplicate vertices within a tolerance.

    Parameters
    ----------
    vertices : list[tuple[float, float, float]]
        List of vertex coordinates.
    tol : float
        Tolerance for considering vertices as duplicates.

    Returns
    -------
    list[dict]
        List of dictionaries containing duplicate vertices:
        - "type": str - always "vertex"
        - "points": list[list[float]] - list containing one sublist [x, y, z] of the vertex coordinates
        - "severity": str - always "high"
    """
    unique_vertices = []
    orig_to_unique = {}

    for i, v in enumerate(vertices, start=1):
        found = None
        
        for j, uv in enumerate(unique_vertices, start=1):
            if (abs(uv[0] - v[0]) < tol and
                abs(uv[1] - v[1]) < tol and
                abs(uv[2] - v[2]) < tol):
                found = j
                break
        if found is None:
            unique_vertices.append(v)
            orig_to_unique[i] = len(unique_vertices)
        else:
            orig_to_unique[i] = found

    # Build duplicate groups
    unique_to_originals = {}
    for orig, uniq in orig_to_unique.items():
        if uniq not in unique_to_originals:
            unique_to_originals[uniq] = []
        unique_to_originals[uniq].append(orig)

    duplicate_reports = []
    for uniq_idx, origs in unique_to_originals.items():
        if len(origs) > 1:
            # All originals in this group are duplicates
            for orig in sorted(origs):
                coord = vertices[orig - 1]
                duplicate_reports.append({
                    "type": "vertex",
                    "points": [[coord[0], coord[1], coord[2]]],
                    "severity": "medium"
                })

    return duplicate_reports

# -----------------------------
# PLC check: segment-facet intersections using CDT triangulation
# -----------------------------
def detect_segment_facet_intersections_cdt(
    faces,                                  # List[FaceRecord]
    points: List[Tuple[float,float,float]], # unique_vertices
    *,
    warn_planar_tol_m=1e-4,
    fatal_planar_tol_m=1e-3,
    eps=1e-10,
    bbox_pad=1e-9,
    max_reports=200,
    skip_warped_faces=True,
) -> List[Dict[str,Any]]:
    """
    Reports intersections where a boundary segment (edge) intersects a triangle
    from a non-incident face.

    Parameters
    ----------
    faces : list[FaceRecord]
        List of FaceRecord objects (each must provide `.fid` and `.verts`,
        with `.verts` being an ordered 1-based vertex id loop).
    points : list[tuple[float, float, float]]
        Global unique vertex coordinates (0-based list; vertex id i -> points[i-1]).
    warn_planar_tol_m : float, optional
        Warning tolerance for planarity checks in meters (default 1e-4).
    fatal_planar_tol_m : float, optional
        Fatal tolerance for planarity checks in meters (default 1e-3).
    eps : float, optional
        Numerical epsilon used by the segment-triangle intersection test.
    bbox_pad : float, optional
        Padding applied to AABB overlap checks to avoid missing near-boundary hits.
    max_reports : int, optional
        Maximum number of intersection reports to collect before returning.
    skip_warped_faces : bool, optional
        If True, faces flagged as non-planar ("fatal") are skipped from
        triangulation and intersection tests.

    Returns
    -------
    list[dict]
        A list of intersection report dictionaries. Each report contains keys
        such as:
        - "edge": (u, v)  -- vertex ids defining the tested segment
        - "edge_coordinates": list[tuple[float, float, float]]  -- coordinates of the edge endpoints
        - "edge_fids": list[int]  -- face ids adjacent to that edge
        - "facet_fid": int  -- the face id of the triangle that was hit
        - "facet_fid_coordinates": list[tuple[float, float, float]]  -- coordinates of the original face vertices before triangulation
        - "facet_tri": (a, b, c)  -- triangle vertex ids
        - "point": (x, y, z)  -- intersection point coordinates
        - "t_param", "bary_u", "bary_v", "bary_w" -- intersection params
        - "hit_type" -- classification string (vertex/edge/interior touch)
        - "facet_planarity_flag" -- planarity status of the triangle's originating face

    Notes:
    - Uses CDT triangulation internally for faces with n>3 (good for concave).
    - If skip_warped_faces=True and planarity_fn provided:
         faces with pstat=="fatal" are not triangulated (skipped).
    - Does NOT modify your exported topology.
    """

    # 1) Triangle soup
    tri_list = []  # each: {fid, tri=(a,b,c), aabb, planar_flag}
    skipped_nonplanar = 0
    tri_fail = 0

    for f in faces:
        poly = f.verts
        if len(poly) < 3:
            continue

        planar_flag = None
        if len(poly) > 3:
            pstat, pmax_m, prms_m = classify_face_planarity_m(
                poly, points,
                warn_planar_tol_m=warn_planar_tol_m,
                fatal_planar_tol_m=fatal_planar_tol_m,
            )
            planar_flag = pstat
            if skip_warped_faces and pstat == "fatal":
                skipped_nonplanar += 1
                continue

        # triangulate
        if len(poly) == 3:
            tris = [poly[:]]
        else:
            tris = triangulate_face_cdt_shapely(poly, points)

        if not tris:
            tri_fail += 1
            continue

        for tri in tris:
            if len(tri) != 3:
                continue
            a,b,c = tri
            A, B, C = points[a-1], points[b-1], points[c-1]
            tri_list.append({
                "fid": f.fid,
                "tri": (a,b,c),
                "aabb": aabb_of_tri(A,B,C),
                "planar_flag": planar_flag,
            })

    # 2) Unique edges + incident face ids
    edge_to_faces = defaultdict(set)
    edge_set = set()
    for f in faces:
        poly = f.verts
        n = len(poly)
        if n < 2:
            continue
        for i in range(n):
            u = poly[i]
            v = poly[(i+1) % n]
            e = (u,v) if u < v else (v,u)
            edge_set.add(e)
            edge_to_faces[e].add(f.fid)

    # 3) Precompute triangle vertex sets for incident skipping
    tri_vset = [set(t["tri"]) for t in tri_list]

    # 4) Intersections
    reports = []
    for (u,v) in edge_set:
        P0 = points[u-1]
        P1 = points[v-1]
        seg_bb = aabb_of_seg(P0,P1)

        for ti, tinfo in enumerate(tri_list):
            if not aabb_overlap(seg_bb, tinfo["aabb"], pad=bbox_pad):
                continue

            a,b,c = tinfo["tri"]

            # Skip triangles incident to this segment (share any vertex)
            if u in tri_vset[ti] or v in tri_vset[ti]:
                continue

            A, B, C = points[a-1], points[b-1], points[c-1]
            hit, t, uu, vv = segment_intersects_triangle(P0, P1, A, B, C, eps=eps)
            if not hit:
                continue

            hit_type = classify_segment_triangle_hit(
                t, uu, vv,
                t_eps=1e-9,
                bary_eps=1e-9,
            )

            I = vadd(P0, vmul(sub(P1, P0), t))

            # Get original face coordinates before triangulation
            original_face = next(f for f in faces if f.fid == tinfo["fid"])
            facet_fid_coordinates = [points[vid - 1] for vid in original_face.verts]

            reports.append({
                "edge": (u, v),
                "edge_coordinates": [P0, P1],
                "edge_fids": sorted(edge_to_faces[(u, v) if u < v else (v, u)]),
                "facet_fid": tinfo["fid"],
                "facet_fid_coordinates": facet_fid_coordinates,
                "facet_tri": (a, b, c),
                "point": I,
                "t_param": float(t),
                "bary_u": float(uu),
                "bary_v": float(vv),
                "bary_w": float(1.0 - uu - vv),
                "hit_type": hit_type,
                "facet_planarity_flag": tinfo["planar_flag"],
            })
            if len(reports) >= max_reports:
                return reports

    return reports

def classify_segment_triangle_hit(t, u, v, *, t_eps=1e-9, bary_eps=1e-9):
    """
    Classify a non-coplanar segment-triangle hit using segment parameter t
    and barycentric coordinates u,v,w.

    Returns one of:
      - endpoint_vertex_touch
      - endpoint_edge_touch
      - endpoint_face_interior_touch
      - segment_vertex_touch
      - segment_edge_intersection
      - segment_face_interior_intersection
      - unknown
    """
    w = 1.0 - u - v

    # ---- segment side
    at_start = abs(t) <= t_eps
    at_end   = abs(t - 1.0) <= t_eps
    at_endpoint = at_start or at_end

    vals = [u, v, w]

    near_zero = [abs(x) <= bary_eps for x in vals]
    near_one  = [abs(x - 1.0) <= bary_eps for x in vals]

    n_zero = sum(near_zero)
    n_one = sum(near_one)

    # triangle location
    if n_one == 1 and n_zero >= 2:
        tri_loc = "vertex"
    elif n_zero == 1 and n_one == 0:
        tri_loc = "edge"
    elif all((bary_eps < x < 1.0 - bary_eps) for x in vals):
        tri_loc = "interior"
    else:
        tri_loc = "unknown"

    # combine
    if at_endpoint:
        if tri_loc == "vertex":
            return "endpoint_vertex_touch"
        elif tri_loc == "edge":
            return "endpoint_edge_touch"
        elif tri_loc == "interior":
            return "endpoint_face_interior_touch"
        else:
            return "unknown"
    else:
        if tri_loc == "vertex":
            return "segment_vertex_touch"
        elif tri_loc == "edge":
            return "segment_edge_intersection"
        elif tri_loc == "interior":
            return "segment_face_interior_intersection"
        else:
            return "unknown"
      
# Segment facet intersection detection
# -----------------------------
# Basic vector ops
# -----------------------------
def vadd(a,b): return (a[0]+b[0], a[1]+b[1], a[2]+b[2])
def vmul(a,s): return (a[0]*s, a[1]*s, a[2]*s)

def aabb_of_tri(A,B,C):
    return (min(A[0],B[0],C[0]), min(A[1],B[1],C[1]), min(A[2],B[2],C[2]),
            max(A[0],B[0],C[0]), max(A[1],B[1],C[1]), max(A[2],B[2],C[2]))

def aabb_of_seg(A,B):
    return (min(A[0],B[0]), min(A[1],B[1]), min(A[2],B[2]),
            max(A[0],B[0]), max(A[1],B[1]), max(A[2],B[2]))

def aabb_overlap(bb1, bb2, pad=0.0):
    ax0,ay0,az0,ax1,ay1,az1 = bb1
    bx0,by0,bz0,bx1,by1,bz1 = bb2
    return not (ax1+pad < bx0 or bx1+pad < ax0 or
                ay1+pad < by0 or by1+pad < ay0 or
                az1+pad < bz0 or bz1+pad < az0)

def polygon_area_3d(
    loop_vids: List[int],
    vertices: List[Tuple[float, float, float]],
) -> float:
    """
    Compute polygon area in 3D using Newell's method.

    Parameters
    ----------
    loop_vids : list[int]
        Ordered 1-based vertex ids of one face.
    vertices : list[(x, y, z)]
        Global vertex list.

    Returns
    -------
    float
        Polygon area in square meters if input coordinates are in meters.
    """
    if len(loop_vids) < 3:
        return 0.0

    nx = ny = nz = 0.0
    n = len(loop_vids)

    for i in range(n):
        p = vertices[loop_vids[i] - 1]
        q = vertices[loop_vids[(i + 1) % n] - 1]

        nx += (p[1] - q[1]) * (p[2] + q[2])
        ny += (p[2] - q[2]) * (p[0] + q[0])
        nz += (p[0] - q[0]) * (p[1] + q[1])

    return 0.5 * math.sqrt(nx * nx + ny * ny + nz * nz)

# -----------------------------
# Segment-triangle intersection (Möller–Trumbore variant)
# Returns (hit, t, u, v) with t in [0,1] along segment
# -----------------------------
def segment_intersects_triangle(P0, P1, A, B, C, eps=1e-12):
    D  = sub(P1, P0)
    E1 = sub(B, A)
    E2 = sub(C, A)

    H = cross(D, E2)
    det = dot(E1, H)

    # parallel / coplanar-ish (we treat as "no hit" here)
    if abs(det) < eps:
        return (False, None, None, None)

    inv_det = 1.0 / det
    S = sub(P0, A)
    u = inv_det * dot(S, H)
    if u < -eps or u > 1.0 + eps:
        return (False, None, None, None)

    Q = cross(S, E1)
    v = inv_det * dot(D, Q)
    if v < -eps or (u + v) > 1.0 + eps:
        return (False, None, None, None)

    t = inv_det * dot(E2, Q)
    if t < -eps or t > 1.0 + eps:
        return (False, None, None, None)

    return (True, t, u, v)