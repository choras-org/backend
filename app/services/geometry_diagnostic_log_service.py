from collections import Counter, defaultdict
from dataclasses import asdict, is_dataclass
import json
import math
from typing import Any, Dict, List, Tuple

from app.utils.geometry_utils import FaceRecord, dot, _uedge, newell_normal_from_points, sub

def build_topology_report(vertices: List[Tuple[float, float, float]], faces: List[FaceRecord]) -> Dict[str, Any]:
    """
    Build a topology summary for the current geometry state.

    Parameters
    ----------
    vertices : list[tuple[float, float, float]]
        Global vertex list.
    faces : list[FaceRecord]
        Current face records.

    Returns
    -------
    dict
        Counts and short samples for faces, vertices, unique edges,
        boundary edges, and non-manifold edges.
    """
    edge_count: Dict[Tuple[int, int], int] = defaultdict(int)
    for face in faces:
        for edge in face.undirected_edges():
            edge_count[edge] += 1

    boundary_edges = [edge for edge, count in edge_count.items() if count == 1]
    non_manifold_edges = [edge for edge, count in edge_count.items() if count > 2]

    return {
        "num_vertices": len(vertices),
        "num_faces": len(faces),
        "num_edges": len(edge_count),
        "num_boundary_edges": len(boundary_edges),
        "num_non_manifold_edges": len(non_manifold_edges),
        "boundary_edge_samples": boundary_edges[:20],
        "non_manifold_edge_samples": non_manifold_edges[:20],
    }

def build_issue_detection_report(
    *,
    vertices_before_dedup: int,
    vertices_after_dedup: int,
    degenerate_fatal_count: int,
    degenerate_warning_count: int,
    nonplanar_fatal_count: int,
    nonplanar_warning_count: int,
    tjunctions: List[Dict[str, Any]],
    intersections: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Build a structured issue report for the inspection stage.

    Parameters
    ----------
    vertices_before_dedup : int
        Number of vertices before deduplication.
    vertices_after_dedup : int
        Number of vertices after deduplication.
    degenerate_fatal_count : int
        Number of fatal degenerate faces detected.
    degenerate_warning_count : int
        Number of warning degenerate faces detected.
    nonplanar_fatal_count : int
        Number of fatal non-planar faces detected.
    nonplanar_warning_count : int
        Number of warning non-planar faces detected.
    tjunctions : list[dict]
        Raw T-junction detection records.
    intersections : list[dict]
        Raw segment-facet intersection records.

    Returns
    -------
    dict
        Structured issue summary.
    """
    return {
        "vertex_deduplication": {
            "before": vertices_before_dedup,
            "after": vertices_after_dedup,
            "deduplicated": max(0, vertices_before_dedup - vertices_after_dedup),
        },
        "degenerate_faces": {
            "fatal": degenerate_fatal_count,
            "warning": degenerate_warning_count,
        },
        "non_planar_faces": {
            "fatal": nonplanar_fatal_count,
            "warning": nonplanar_warning_count,
        },
        "tjunctions": {
            "count": len(tjunctions),
            "samples": tjunctions[:20],
        },
        "intersections": {
            "count": len(intersections),
            "by_type": dict(Counter(hit.get("hit_type", "unknown") for hit in intersections)),
            "samples": intersections[:20],
        },
    }

def append_repair_report(
    repair_report: List[Dict[str, Any]],
    *,
    repair_type: str,
    affected_count: int = 0,
    before: Any = None,
    after: Any = None,
    details: Any = None,
) -> None:
    """
    Append one repair event to the repair report.

    Parameters
    ----------
    repair_report : list[dict]
        Mutable list storing all repair events.
    repair_type : str
        Name of the repair operation.
    affected_count : int, optional
        Number of affected entities.
    before : Any, optional
        Relevant state before the repair.
    after : Any, optional
        Relevant state after the repair.
    details : Any, optional
        Extra contextual information.
    """
    repair_report.append({
        "repair_type": repair_type,
        "affected_count": affected_count,
        "before": before,
        "after": after,
        "details": details,
    })

def build_revalidation_report(
    vertices: List[Tuple[float, float, float]],
    faces: List[FaceRecord],
    *,
    tjunctions: List[Dict[str, Any]],
    intersections: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Build the final revalidation report after repair.

    Parameters
    ----------
    vertices : list[tuple[float, float, float]]
        Final vertex list.
    faces : list[FaceRecord]
        Final face list.
    tjunctions : list[dict]
        Remaining T-junctions after repair.
    intersections : list[dict]
        Remaining intersections after repair.

    Returns
    -------
    dict
        Final issue state and topology snapshot.
    """
    holes = find_free_edge_loops(faces)
    return {
        "remaining_tjunctions": {
            "count": len(tjunctions),
            "samples": tjunctions[:20],
        },
        "remaining_intersections": {
            "count": len(intersections),
            "by_type": dict(Counter(hit.get("hit_type", "unknown") for hit in intersections)),
            "samples": intersections[:20],
        },
        "remaining_holes": {
            "count": len(holes),
            "samples": holes[:10],
        },
        "topology_after_repair": build_topology_report(vertices, faces),
    }

def convert_tjunctions_to_standard_format(tjunctions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert T-junction detection output to a standardized format for diagnostic logging.

    Parameters
    ----------
    tjunctions : list[dict]
        Raw T-junction reports from detect_t_junctions_from_facerecords_global_plc.

    Returns
    -------
    list[dict]
        Standardized reports with "points" and "severity" keys.
        Each report contains:
        - "points": list of dicts with "type" ("edge" or "vertex") and "points" (coordinates).
        - "severity": str, always "high".
    """
    standardized = []
    for tj in tjunctions:
        points = [
            {
                "type": "edge",
                "points": tj["edge_coordinates"]
            },
            {
                "type": "vertex",
                "points": tj["split_vertex_coordinates"]
            }
        ]
        standardized.append({
            "type": "vertex_on_edge",
            "points": points,
            "severity": "high"
        })
    return standardized

def convert_intersections_to_standard_format(intersections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert segment-facet intersection detection output to a standardized format for diagnostic logging.

    Parameters
    ----------
    intersections : list[dict]
        Raw intersection reports from detect_segment_facet_intersections_cdt.

    Returns
    -------
    list[dict]
        Standardized reports with "type", "points", and "severity" keys.
        Each report contains:
        - "type": str, always "edge_on_face".
        - "points": list of dicts with "type" ("edge", "face", or "vertex") and "points" (coordinates).
        - "severity": str, always "high".
    """
    standardized = []
    for inter in intersections:
        points = [
            {
                "type": "edge",
                "points": inter["edge_coordinates"]
            },
            {
                "type": "face",
                "points": inter["facet_fid_coordinates"]
            },
            {
                "type": "vertex",
                "points": [inter["point"]]
            }
        ]
        standardized.append({
            "type": "edge_on_face",
            "points": points,
            "severity": "high"
        })
    return standardized

def create_geometry_processing_report(
    *,
    obj_file: str,
    repaired_obj: str,
    topology_before_repair: Dict[str, Any],
    issue_detection_report: Dict[str, Any],
    repair_report: List[Dict[str, Any]],
    revalidation_report: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Assemble the full geometry processing report.

    Returns
    -------
    dict
        Full report structure ready to be serialized as JSON.
    """
    return {
        "input_obj": obj_file,
        "output_repaired_obj": repaired_obj,
        "topology_before_repair": topology_before_repair,
        "issue_detection_report": issue_detection_report,
        "repair_report": repair_report,
        "revalidation_report": revalidation_report,
    }

def write_geometry_processing_report(report: Dict[str, Any], report_path: str) -> None:
    """
    Write a geometry processing report to disk.

    Parameters
    ----------
    report : dict
        Report payload.
    report_path : str
        Output JSON path.
    """
    def _json_safe(value: Any) -> Any:
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value

        if isinstance(value, FaceRecord):
            return {
                "fid": value.fid,
                "verts": value.verts,
                "group": value.group,
                "group_material": value.group_material,
                "material": value.material,
            }

        if is_dataclass(value):
            return _json_safe(asdict(value))

        if isinstance(value, dict):
            return {str(k): _json_safe(v) for k, v in value.items()}

        if isinstance(value, (list, tuple, set)):
            return [_json_safe(v) for v in value]

        return str(value)

    safe_report = _json_safe(report)
    with open(report_path, "w") as fp:
        json.dump(safe_report, fp, indent=2)

def find_free_edge_loops(faces):
    """
    faces: list of FaceRecord (any polygon, not just triangles)
    Returns: list of loops, each loop is a list of vertex ids in order (closed implied).
    """
    # Count undirected edge incidence
    edge_count = defaultdict(int)
    for face in faces:
        for u, v in face.undirected_edges():
            edge_count[_uedge(u, v)] += 1

    free_edges = [e for e, cnt in edge_count.items() if cnt == 1]
    if not free_edges:
        return []

    # Build adjacency graph of free edges: vertex -> neighboring vertices along boundary
    adj = defaultdict(list)
    for u, v in free_edges:
        adj[u].append(v)
        adj[v].append(u)

    # Extract loops by walking until we return to start
    loops = []
    visited_edges = set()

    def mark_edge(u, v):
        visited_edges.add(_uedge(u, v))

    def edge_visited(u, v):
        return _uedge(u, v) in visited_edges

    for (u0, v0) in free_edges:
        if edge_visited(u0, v0):
            continue

        # Start a new loop walk
        loop = [u0, v0]
        mark_edge(u0, v0)

        prev = u0
        cur = v0

        safety = 0
        while safety < 100000:
            safety += 1

            # Choose next neighbor not equal to prev and not yet visited, if possible
            nxt = None
            for cand in adj[cur]:
                if cand == prev:
                    continue
                if not edge_visited(cur, cand):
                    nxt = cand
                    break

            if nxt is None:
                # might be closing edge back to start
                # try to close if possible
                if loop[0] in adj[cur] and not edge_visited(cur, loop[0]):
                    nxt = loop[0]
                else:
                    break

            mark_edge(cur, nxt)

            if nxt == loop[0]:
                # closed
                loops.append(loop[:] )  # loop without repeating start at end
                break

            loop.append(nxt)
            prev, cur = cur, nxt

    # Normalize loops (remove duplicates / rotate to smallest id)
    norm = []
    seen = set()
    for loop in loops:
        if len(loop) < 3:
            continue
        # rotate so smallest vertex id comes first
        m = min(loop)
        mi = loop.index(m)
        rotated = loop[mi:] + loop[:mi]
        # also consider reverse as same
        key1 = tuple(rotated)
        key2 = tuple([rotated[0]] + list(reversed(rotated[1:])))
        key = min(key1, key2)
        if key in seen:
            continue
        seen.add(key)
        norm.append(rotated)

    return norm

# -----------------------------
# Polygon quality report 
# -----------------------------
def log_polygon_quality(logger, face_id, grp, mat, mapped, qrep):
    logger_fn = logger.error if qrep["status"] == "fatal" else logger.warning

    logger_fn(
        "[FACE POLY %s] id=%d group=%s mat=%s n=%d "
        "min_edge=%.6e m max_edge=%.6e m ratio=%.3e min_angle=%.3f deg "
        "self_intersects_2d=%s drop_axis=%s reasons=%s verts=%s",
        qrep["status"].upper(),
        face_id,
        grp,
        mat,
        qrep["n"],
        qrep["min_edge_len_m"],
        qrep["max_edge_len_m"],
        qrep["edge_len_ratio"],
        qrep["min_angle_deg"],
        qrep["self_intersects_2d"],
        qrep["projection_axis_dropped"],
        qrep["reasons"],
        mapped,
    )
    
def polygon_quality_report(
    face_ids,
    points,
    *,
    edge_len_warn_ratio=100.0,
    edge_len_fatal_ratio=1000.0,
    min_angle_warn_deg=10.0,
    min_angle_fatal_deg=3.0,
    min_edge_warn_m=1e-4,
    min_edge_fatal_m=1e-6,
    proj_tol=1e-12,
):
    """
    Polygon-level diagnostics independent of triangulation.

    Parameters
    ----------
    face_ids : list[int]
        1-based vertex ids of one polygon face
    points : list[(x,y,z)]
        unique_vertices list; vertex id i -> points[i-1]

    Returns
    -------
    dict with:
      {
        "n": int,
        "min_edge_len_m": float,
        "max_edge_len_m": float,
        "edge_len_ratio": float,
        "min_angle_deg": float,
        "self_intersects_2d": bool,
        "projection_axis_dropped": "x"|"y"|"z"|None,
        "status": "ok"|"warning"|"fatal",
        "reasons": [str, ...],
      }
    """

    def dist(a, b):
        dx = a[0] - b[0]
        dy = a[1] - b[1]
        dz = a[2] - b[2]
        return math.sqrt(dx*dx + dy*dy + dz*dz)

    def norm(v):
        return math.sqrt(dot(v, v))

    def clamp(x, lo, hi):
        return max(lo, min(hi, x))

    def project_face(ids):
        nrm = newell_normal_from_points(ids, points)
        ax, ay, az = abs(nrm[0]), abs(nrm[1]), abs(nrm[2])

        if ax == 0.0 and ay == 0.0 and az == 0.0:
            return None, None

        if az >= ax and az >= ay:
            # drop z -> XY
            poly2d = [(points[pid - 1][0], points[pid - 1][1]) for pid in ids]
            return poly2d, "z"
        elif ay >= ax and ay >= az:
            # drop y -> XZ
            poly2d = [(points[pid - 1][0], points[pid - 1][2]) for pid in ids]
            return poly2d, "y"
        else:
            # drop x -> YZ
            poly2d = [(points[pid - 1][1], points[pid - 1][2]) for pid in ids]
            return poly2d, "x"

    def orient2d(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    def on_segment_2d(p, a, b, tol=1e-12):
        # assumes near-collinear
        return (
            min(a[0], b[0]) - tol <= p[0] <= max(a[0], b[0]) + tol and
            min(a[1], b[1]) - tol <= p[1] <= max(a[1], b[1]) + tol
        )

    def seg_intersect_2d(a, b, c, d, tol=1e-12):
        """
        Proper/general 2D segment intersection.
        Returns True if segments intersect.
        """
        o1 = orient2d(a, b, c)
        o2 = orient2d(a, b, d)
        o3 = orient2d(c, d, a)
        o4 = orient2d(c, d, b)

        # proper intersection
        if ((o1 > tol and o2 < -tol) or (o1 < -tol and o2 > tol)) and \
           ((o3 > tol and o4 < -tol) or (o3 < -tol and o4 > tol)):
            return True

        # collinear / touching cases
        if abs(o1) <= tol and on_segment_2d(c, a, b, tol): return True
        if abs(o2) <= tol and on_segment_2d(d, a, b, tol): return True
        if abs(o3) <= tol and on_segment_2d(a, c, d, tol): return True
        if abs(o4) <= tol and on_segment_2d(b, c, d, tol): return True

        return False

    def polygon_self_intersects_2d(poly2d):
        n = len(poly2d)
        if n < 4:
            return False

        for i in range(n):
            a = poly2d[i]
            b = poly2d[(i + 1) % n]

            for j in range(i + 1, n):
                # edge j
                c = poly2d[j]
                d = poly2d[(j + 1) % n]

                # skip same edge
                if i == j:
                    continue

                # skip adjacent edges sharing a vertex
                if (i + 1) % n == j or (j + 1) % n == i:
                    continue

                # skip first/last adjacency in closed polygon
                if i == 0 and (j + 1) % n == 0:
                    continue

                if seg_intersect_2d(a, b, c, d, tol=proj_tol):
                    return True
        return False

    n = len(face_ids)
    report = {
        "n": n,
        "min_edge_len_m": float("inf"),
        "max_edge_len_m": 0.0,
        "edge_len_ratio": float("inf"),
        "min_angle_deg": float("inf"),
        "self_intersects_2d": False,
        "projection_axis_dropped": None,
        "status": "ok",
        "reasons": [],
    }

    if n < 3:
        report["status"] = "fatal"
        report["reasons"].append("fewer_than_3_vertices")
        return report

    pts = [points[vid - 1] for vid in face_ids]

    # --------------------------------------------------
    # 1) minimum / maximum edge length
    # --------------------------------------------------
    edge_lengths = []
    for i in range(n):
        a = pts[i]
        b = pts[(i + 1) % n]
        L = dist(a, b)
        edge_lengths.append(L)

    min_edge = min(edge_lengths) if edge_lengths else float("inf")
    max_edge = max(edge_lengths) if edge_lengths else 0.0
    ratio = (max_edge / min_edge) if min_edge > 0.0 else float("inf")

    report["min_edge_len_m"] = min_edge
    report["max_edge_len_m"] = max_edge
    report["edge_len_ratio"] = ratio

    # --------------------------------------------------
    # 2) minimum internal angle
    # --------------------------------------------------
    min_angle = float("inf")
    for i in range(n):
        p_prev = pts[(i - 1) % n]
        p_cur  = pts[i]
        p_next = pts[(i + 1) % n]

        v1 = sub(p_prev, p_cur)
        v2 = sub(p_next, p_cur)

        n1 = norm(v1)
        n2 = norm(v2)

        if n1 <= 0.0 or n2 <= 0.0:
            ang = 0.0
        else:
            c = clamp(dot(v1, v2) / (n1 * n2), -1.0, 1.0)
            ang = math.degrees(math.acos(c))

        if ang < min_angle:
            min_angle = ang

    report["min_angle_deg"] = min_angle

    # --------------------------------------------------
    # 3) self-intersection in projected loop
    # --------------------------------------------------
    poly2d, dropped = project_face(face_ids)
    report["projection_axis_dropped"] = dropped
    if poly2d is not None:
        report["self_intersects_2d"] = polygon_self_intersects_2d(poly2d)

    # --------------------------------------------------
    # 4) classify severity
    # --------------------------------------------------
    fatal = False
    warning = False

    if report["self_intersects_2d"]:
        fatal = True
        report["reasons"].append("self_intersects_2d")

    if min_edge <= min_edge_fatal_m:
        fatal = True
        report["reasons"].append("min_edge_too_small_fatal")
    elif min_edge <= min_edge_warn_m:
        warning = True
        report["reasons"].append("min_edge_too_small_warn")

    if ratio >= edge_len_fatal_ratio:
        fatal = True
        report["reasons"].append("edge_len_ratio_fatal")
    elif ratio >= edge_len_warn_ratio:
        warning = True
        report["reasons"].append("edge_len_ratio_warn")

    if min_angle <= min_angle_fatal_deg:
        fatal = True
        report["reasons"].append("min_angle_too_small_fatal")
    elif min_angle <= min_angle_warn_deg:
        warning = True
        report["reasons"].append("min_angle_too_small_warn")

    if fatal:
        report["status"] = "fatal"
    elif warning:
        report["status"] = "warning"
    else:
        report["status"] = "ok"

    return report

def mesh_topology_report(faces, *, sample_n=20):
    """
    faces: list of FaceRecord (any polygon, not just triangles)
    Returns a dict with topology statistics.
    """

    # --- edge -> incident face fids
    edge_to_fids = defaultdict(list)
    for face in faces:
        for u, v in face.undirected_edges():
            edge_to_fids[_uedge(u, v)].append(face.fid)

    # --- classify edges
    edge_count = {e: len(fids) for e, fids in edge_to_fids.items()}
    boundary_edges = [e for e, cnt in edge_count.items() if cnt == 1]
    interior_ok_edges = [e for e, cnt in edge_count.items() if cnt == 2]
    nonmanifold_edges = [e for e, cnt in edge_count.items() if cnt > 2]

    # --- build boundary adjacency (graph of free edges)
    badj = defaultdict(set)
    for u, v in boundary_edges:
        badj[u].add(v)
        badj[v].add(u)

    bdeg = {v: len(nbrs) for v, nbrs in badj.items()}
    bdeg_hist = dict(Counter(bdeg.values()))

    boundary_endpoints = sorted([v for v, d in bdeg.items() if d == 1])
    boundary_branch_vertices = sorted([v for v, d in bdeg.items() if d > 2])

    # --- boundary connected components classification
    # component is:
    #   cycle: all vertices degree 2
    #   chain: has deg1 endpoints and max deg <=2
    #   branched: contains deg >2
    seen_v = set()
    comps = []
    for v0 in badj.keys():
        if v0 in seen_v:
            continue
        stack = [v0]
        comp_vs = set()
        while stack:
            v = stack.pop()
            if v in comp_vs:
                continue
            comp_vs.add(v)
            for w in badj[v]:
                if w not in comp_vs:
                    stack.append(w)
        seen_v |= comp_vs

        degs = [bdeg[v] for v in comp_vs]
        dmax = max(degs) if degs else 0
        dmin = min(degs) if degs else 0
        n1 = sum(1 for d in degs if d == 1)
        n2 = sum(1 for d in degs if d == 2)
        ngt2 = sum(1 for d in degs if d > 2)

        if ngt2 > 0:
            kind = "branched_nonmanifold_boundary"
        elif n1 == 0 and dmin == 2 and dmax == 2:
            kind = "cycle"
        else:
            kind = "open_chain_or_path"

        comps.append({
            "kind": kind,
            "n_vertices": len(comp_vs),
            "deg_hist": dict(Counter(degs)),
            "sample_vertices": sorted(list(comp_vs))[:min(sample_n, len(comp_vs))]
        })

    # summary counts
    comp_kind_hist = dict(Counter(c["kind"] for c in comps))

    return {
        # global
        "n_faces": len(faces),
        "n_unique_edges": len(edge_count),
        "n_boundary_edges": len(boundary_edges),
        "n_nonmanifold_edges": len(nonmanifold_edges),

        # high-level flags
        # Watertighness still needs more checks (e.g self intersections)
        "is_watertight": (len(boundary_edges) == 0),
        "has_nonmanifold_edges": (len(nonmanifold_edges) > 0),
        "has_nonmanifold_boundary": (len(boundary_branch_vertices) > 0),

        # samples
        "boundary_edges_sample": boundary_edges[:sample_n],
        "nonmanifold_edges_sample": nonmanifold_edges[:sample_n],

        # boundary vertex degrees
        "n_boundary_vertices": len(bdeg),
        "boundary_degree_hist": bdeg_hist,
        "boundary_endpoints_sample": boundary_endpoints[:sample_n],
        "boundary_branch_vertices_sample": boundary_branch_vertices[:sample_n],

        # boundary component breakdown
        "boundary_component_kind_hist": comp_kind_hist,
        "boundary_components_sample": comps[:min(10, len(comps))],
    }

def log_topology(logger, label, faces):
    rep = mesh_topology_report(faces, sample_n=10)
    logger.info(f"[TOPO] {label}: "
                f"faces={rep['n_faces']} edges={rep['n_unique_edges']} "
                f"boundary_edges={rep['n_boundary_edges']} nonmanifold_edges={rep['n_nonmanifold_edges']} "
    )

    return rep
