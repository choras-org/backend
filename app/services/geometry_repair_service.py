from collections import defaultdict, deque
import logging
import math
from typing import List, Tuple, Dict, Any, Optional

import numpy as np
from app.utils.geometry_utils import FaceRecord, _uedge, area2, cross, dot, newell_normal_from_points, orient, sub, triangulate_face_cdt_shapely
from app.utils.geometry_validation_utils import classify_face_degeneracy, classify_face_planarity_m, planarity_deviation_m
from app.services.geometry_inspection_service import detect_segment_facet_intersections_cdt, detect_t_junctions_from_facerecords_global_plc
from app.services.geometry_parsing_service import clean_face_loop

logger = logging.getLogger(__name__)

def remove_degenerate_faces(
    faces: List[FaceRecord],
    unique_vertices: List[Tuple[float, float, float]],
    *,
    fatal_area_tol: float = 1e-12,
    logger: logging.Logger = None,
) -> Tuple[List[FaceRecord], int, int]:
    """
    Remove degenerate faces from a list of FaceRecord objects.

    Parameters
    ----------
    faces : List[FaceRecord]
        List of FaceRecord objects to process.
    unique_vertices : List[Tuple[float, float, float]]
        List of unique vertex coordinates.
    fatal_area_tol : float
        Tolerance for fatal degeneracy (area squared).
    warn_area_tol : float
        Tolerance for warning degeneracy (area squared).
    logger : logging.Logger, optional
        Logger instance for logging messages.

    Returns
    -------
    Tuple[List[FaceRecord], int, int]
        (clean_faces, fatal_removed, warn_removed)
        - clean_faces: List of non-degenerate FaceRecord objects
        - fatal_removed: Number of fatally degenerate faces removed
        - warn_removed: Number of warning degenerate faces kept (but counted)
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    faces_clean = []
    fatal_removed = 0

    for f in faces:
        status = classify_face_degeneracy(
            f.verts,
            unique_vertices,
            fatal_area_tol=fatal_area_tol,
        )

        if status == "fatal":
            fatal_removed += 1
            continue

        faces_clean.append(f)

    return faces_clean, fatal_removed

def sort_vertices_deterministically(
    unique_vertices: List[Tuple[float, float, float]], 
    faces: List[FaceRecord]
) -> Tuple[List[Tuple[float, float, float]], List[FaceRecord]]:
    """
    Sort vertices deterministically for reproducibility and remap face vertex indices.

    Parameters
    ----------
    unique_vertices : List[Tuple[float, float, float]]
        List of unique vertex coordinates.
    faces : List[FaceRecord]
        List of FaceRecord objects with vertex indices.

    Returns
    -------
    Tuple[List[Tuple[float, float, float]], List[FaceRecord]]
        (sorted_vertices, remapped_faces)
        - sorted_vertices: Vertices sorted deterministically by coordinates
        - remapped_faces: Faces with vertex indices updated to match sorted vertices
    """
    unique_vertices_sorted = sorted(
        enumerate(unique_vertices, start=1),
        key=lambda kv: (
            round(kv[1][0], 8),
            round(kv[1][1], 8),
            round(kv[1][2], 8),
        ),
    )
    index_map = {old: new for new, (old, _) in enumerate(unique_vertices_sorted, start=1)}
    unique_vertices = [v for _, v in unique_vertices_sorted]
    # Remap all face vertex indices
    for face in faces:
        face.verts = [index_map[i] for i in face.verts]
    
    return unique_vertices, faces

def fix_t_junctions_iterative(
    faces: List[FaceRecord],
    points: List[Tuple[float, float, float]],
    *,
    tol: float = 1e-8,
    max_iters: int = 100,
    max_reports: int = 5000,
    logger: Optional[logging.Logger] = None,
) -> Tuple[List[FaceRecord], bool]:
    changed_any = False

    for it in range(max_iters):
        tjs = detect_t_junctions_from_facerecords_global_plc(
            faces, points, tol=tol, max_reports=max_reports
        )
        if not tjs:
            if logger:
                logger.info("[TJUNC FIX] stable after %d iterations", it)
            return faces, changed_any

        if logger:
            logger.warning("[TJUNC FIX] iter=%d found=%d (showing up to 5)", it, len(tjs))
            for r in tjs[:5]:
                logger.warning("[TJUNC] edge=%s split_v=%d t=%.6f culprit=%s",
                               r["edge"], r["split_vertex"], r["t_param"],
                               r.get("culprit_face_fid"))

        faces, changed = fix_t_junctions_by_edge_splitting_facerecords(
            faces, tjs, points, tol=tol, max_passes=1, logger=logger
        )
        if not changed:
            # nothing changed but still detecting => tolerance mismatch or a harder intersection
            if logger:
                logger.warning("[TJUNC FIX] no changes applied but TJUNC still detected; stopping")
            return faces, changed_any

        changed_any = True

    if logger:
        logger.warning("[TJUNC FIX] reached max_iters=%d; may still have TJUNCs", max_iters)
    return faces, changed_any

def fix_t_junctions_by_edge_splitting_facerecords(
    faces: List[FaceRecord],
    tjunc_reports: List[Dict[str, Any]],
    points: List[Tuple[float, float, float]],
    *,
    tol: float = 1e-8,
    max_passes: int = 10,
    logger: Optional[logging.Logger] = None,
) -> Tuple[List[FaceRecord], bool]:
    """
    Fix PLC T-junctions WITHOUT triangulation by splitting polygon edges.
    faces: List[FaceRecord] (modified in place; returned too)
    tjunc_reports: output of detect_t_junctions_from_facerecords_local_plc or global_plc
                  each report has:
                    - edge=(u,v)
                    - split_vertex=w
                    - t_param=t
                    - edge_face_fids=[...]
                    - culprit_face_fid=<fid>  (if you use plc detector)
                  If your report doesn't include culprit_face_fid, we'll apply to all edge_face_fids.
    points: unique_vertices list (1-based id -> points[id-1])
    tol: used to reject near-endpoint inserts
    max_passes: repeat because inserting vertices may create new detectable cases
    """

    # Build fid -> face object map
    fid_to_face = {f.fid: f for f in faces}

    def uedge(a, b):
        return (a, b) if a < b else (b, a)

    # Param along directed edge (u->v)
    def edge_param_t(u, v, w):
        Ax, Ay, Az = points[u - 1]
        Bx, By, Bz = points[v - 1]
        Px, Py, Pz = points[w - 1]
        ABx, ABy, ABz = (Bx - Ax, By - Ay, Bz - Az)
        APx, APy, APz = (Px - Ax, Py - Ay, Pz - Az)
        ab2 = ABx*ABx + ABy*ABy + ABz*ABz
        if ab2 <= 0.0:
            return 0.0
        return (APx*ABx + APy*ABy + APz*ABz) / ab2

    changed_any = False

    for pass_i in range(max_passes):
        # Collect insert operations:
        # (fid, undirected_edge) -> list of (u,v,w,t)
        ops = defaultdict(list)

        for r in tjunc_reports:
            u, v = r["edge"]
            w = r["split_vertex"]

            # choose target faces:
            if "culprit_face_fid" in r and r["culprit_face_fid"] is not None:
                target_fids = [r["culprit_face_fid"]]
            else:
                target_fids = r.get("edge_face_fids") or r.get("edge_fids") or []

            for fid in target_fids:
                if fid not in fid_to_face:
                    continue
                # store (directed u,v) as in report; we'll handle reverse in insertion
                t = edge_param_t(u, v, w)
                if not (tol < t < 1.0 - tol):
                    continue
                ops[(fid, uedge(u, v))].append((u, v, w, t))

        if not ops:
            if logger:
                logger.info("[TJUNC FIX] pass=%d: no ops; done", pass_i)
            break

        pass_changed = 0

        for (fid, _e), items in ops.items():
            face = fid_to_face[fid]
            poly = face.verts

            # If multiple w on the same edge, insert in correct order
            # Need consistent direction along the edge as it appears in the polygon
            # We'll just sort by t from the report direction; insertion function handles either direction.
            items_sorted = sorted(items, key=lambda x: x[3])

            for (u, v, w, _t) in items_sorted:
                new_poly, did = _insert_vertex_on_edge_in_poly(poly, u, v, w)
                if did:
                    poly = new_poly
                    pass_changed += 1

            face.verts = poly

        if logger:
            logger.info("[TJUNC FIX] pass=%d: faces_changed=%d", pass_i, pass_changed)

        if pass_changed == 0:
            break

        changed_any = True
        break

    return faces, changed_any

def _insert_vertex_on_edge_in_poly(poly, u, v, w):
    """
    poly: list of vertex ids (cycle, no repeated start/end)
    Insert w between u and v if edge (u->v) or (v->u) appears.
    Returns (new_poly, changed_bool).
    Does NOT insert if w is already in poly.
    """
    if w in poly:
        return poly, False

    n = len(poly)
    if n < 2:
        return poly, False

    # Look for directed edge u->v in the cyclic list
    for i in range(n):
        a = poly[i]
        b = poly[(i + 1) % n]
        if a == u and b == v:
            # Insert w after a
            return poly[: i + 1] + [w] + poly[i + 1 :], True

    # Look for directed edge v->u (reverse direction)
    for i in range(n):
        a = poly[i]
        b = poly[(i + 1) % n]
        if a == v and b == u:
            return poly[: i + 1] + [w] + poly[i + 1 :], True

    return poly, False

def flip_all_faces_if_majority_inward(
    faces: "List[FaceRecord]",
    unique_vertices: List[Tuple[float,float,float]],
    room_center: Tuple[float,float,float],
    logger=None,
) -> bool:
    """
    Uses Newell normal + centroid->room_center dot test.
    If majority of faces look inward, flip all faces.
    Returns True if flipped all, else False.
    """

    inward = 0
    outward = 0

    for f in faces:
        pts = [unique_vertices[i - 1] for i in f.verts]
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        cz = sum(p[2] for p in pts) / len(pts)

        nx, ny, nz = newell_normal_from_points(f.verts, unique_vertices)
        to_center = (room_center[0] - cx, room_center[1] - cy, room_center[2] - cz)
        dotp = nx*to_center[0] + ny*to_center[1] + nz*to_center[2]

        # Your rule: outward if dotp < 0
        if dotp < 0:
            outward += 1
        else:
            inward += 1

    if inward > outward:
        for f in faces:
            f.verts.reverse()
        if logger:
            logger.info("[ORIENT] flipped ALL faces (majority inward: inward=%d outward=%d)", inward, outward)
        return True
    else:
        if logger:
            logger.info("[ORIENT] kept orientation (majority outward: inward=%d outward=%d)", inward, outward)
        return False

def trim_component_against_facet_plane(
    faces: List["FaceRecord"],
    points: List[Tuple[float, float, float]],
    *,
    clipping_facet_fid: int,
    seed_face_fids: List[int],
    room_center: Tuple[float, float, float],
    tol: float = 1e-9,
    logger=None,
) -> Tuple[List["FaceRecord"], List[Tuple[float, float, float]], bool, Dict[str, Any]]:
    """
    Trim a connected face component against the plane of a clipping facet.

    Parameters
    ----------
    faces : list[FaceRecord]
        Current face list.
    points : list[(x, y, z)]
        Global mutable point list. New intersection vertices may be appended.
    clipping_facet_fid : int
        Face id whose plane defines the clipping boundary.
    seed_face_fids : list[int]
        One or more faces belonging to the protruding component that should be clipped.
        For PLC reports, ``edge_fids`` is usually a good seed.
    room_center : tuple[float, float, float]
        A point known to lie on the side of the clipping plane that should be kept.
        In CHORAS this is usually the room center.
    tol : float
        Numerical tolerance for clipping and vertex reuse.
    logger : logging.Logger | None
        Optional logger.

    Returns
    -------
    tuple
        (updated_faces, updated_points, changed, diagnostics)

        diagnostics contains:
        - status
        - clipping_facet_fid
        - seed_face_fids
        - component_face_fids
        - keep_sign
        - faces_removed
        - faces_clipped
        - new_vertices_added

    Purpose
    -------
    This helper performs a best-effort half-space clip of a selected connected
    component. It is useful when a protruding object crosses a room boundary face and
    the desired behavior is to keep only the part on the room side of that face plane.

    Limitation
    ----------
    The clipping facet itself is not split or reconstructed. Therefore, this helper is
    best used as a controlled trimming utility for clearly unwanted outside geometry.
    """
    diag: Dict[str, Any] = {
        "status": "noop",
        "clipping_facet_fid": clipping_facet_fid,
        "seed_face_fids": list(seed_face_fids),
        "component_face_fids": [],
        "keep_sign": None,
        "faces_removed": 0,
        "faces_clipped": 0,
        "new_vertices_added": 0,
    }

    clipping_face = _find_face_by_fid(faces, clipping_facet_fid)
    if clipping_face is None:
        diag["status"] = "clipping_face_not_found"
        return faces, points, False, diag

    plane = _plane_from_face(clipping_face, points)
    if plane is None:
        diag["status"] = "invalid_clipping_plane"
        return faces, points, False, diag

    plane_point, plane_normal = plane
    room_sd = _signed_distance_to_plane(room_center, plane_point, plane_normal)
    keep_sign = 1.0 if room_sd >= 0.0 else -1.0
    diag["keep_sign"] = keep_sign

    component_face_fids = collect_face_component_from_seed_faces(
        faces,
        seed_face_fids,
        excluded_face_fids=[clipping_facet_fid],
    )
    diag["component_face_fids"] = component_face_fids

    if not component_face_fids:
        diag["status"] = "empty_component"
        return faces, points, False, diag

    start_n_points = len(points)
    changed = False
    updated_faces: List[FaceRecord] = []

    for face in faces:
        if face.fid not in component_face_fids:
            updated_faces.append(face)
            continue

        clipped_loop = _clip_face_loop_against_plane(
            face.verts,
            points,
            plane_point,
            plane_normal,
            keep_sign,
            tol=tol,
        )

        if len(clipped_loop) < 3:
            diag["faces_removed"] += 1
            changed = True
            continue

        if clipped_loop != clean_face_loop(face.verts):
            diag["faces_clipped"] += 1
            changed = True

        status, _area2 = classify_face_degeneracy(
            clipped_loop,
            points,
            fatal_area_tol=1e-18,
        )
        if status == "fatal":
            diag["faces_removed"] += 1
            changed = True
            continue

        updated_faces.append(
            FaceRecord(
                fid=face.fid,
                verts=clipped_loop,
                group=getattr(face, "group", "default"),
                group_material=getattr(face, "group_material", "default"),
                material=getattr(face, "material", "unknown"),
            )
        )

    diag["new_vertices_added"] = len(points) - start_n_points
    diag["status"] = "ok" if changed else "no_effect"

    if logger is not None:
        logger.info(
            "[TRIM] facet_fid=%d component_faces=%d clipped=%d removed=%d new_vertices=%d status=%s",
            clipping_facet_fid,
            len(component_face_fids),
            diag["faces_clipped"],
            diag["faces_removed"],
            diag["new_vertices_added"],
            diag["status"],
        )

    return updated_faces, points, changed, diag

def trim_component_from_segment_face_intersection_report(
    faces: List["FaceRecord"],
    points: List[Tuple[float, float, float]],
    plc_report: Dict[str, Any],
    room_center: Tuple[float, float, float],
    *,
    tol: float = 1e-9,
    logger=None,
) -> Tuple[List["FaceRecord"], List[Tuple[float, float, float]], bool, Dict[str, Any]]:
    """
    Convenience wrapper that trims a protruding component using one PLC report.

    Parameters
    ----------
    faces : list[FaceRecord]
        Current face list.
    points : list[(x, y, z)]
        Global mutable point list.
    plc_report : dict
        One PLC report generated by ``detect_segment_facet_intersections_cdt``.
        The report must contain ``facet_fid`` and ``edge_fids``.
    room_center : tuple[float, float, float]
        Reference point used to choose the kept half-space.
    tol : float
        Numerical tolerance for clipping.
    logger : logging.Logger | None
        Optional logger.

    Returns
    -------
    tuple
        (updated_faces, updated_points, changed, diagnostics)

    Purpose
    -------
    This wrapper is especially useful for PLC reports of type
    ``segment_face_interior_intersection`` where the edge's incident faces belong to a
    protruding component that should be clipped back to the clipping facet plane.
    """
    clipping_facet_fid = plc_report.get("facet_fid")
    seed_face_fids = list(plc_report.get("edge_fids") or [])

    if clipping_facet_fid is None or not seed_face_fids:
        diag = {
            "status": "invalid_plc_report",
            "clipping_facet_fid": clipping_facet_fid,
            "seed_face_fids": seed_face_fids,
        }
        return faces, points, False, diag

    return trim_component_against_facet_plane(
        faces,
        points,
        clipping_facet_fid=clipping_facet_fid,
        seed_face_fids=seed_face_fids,
        room_center=room_center,
        tol=tol,
        logger=logger,
    )

def compact_vertices_and_remove_unused(
    faces: List["FaceRecord"],
    points: List[Tuple[float, float, float]],
) -> Tuple[List["FaceRecord"], List[Tuple[float, float, float]], bool, Dict[str, Any]]:
    """
    Remove unused vertices after clipping/repair and remap face indices.

    Parameters
    ----------
    faces : list[FaceRecord]
        Current face list.
    points : list[(x, y, z)]
        Global vertex list.

    Returns
    -------
    tuple
        (updated_faces, updated_points, changed, diagnostics)

    Purpose
    -------
    Local clipping repairs may leave vertices that are no longer referenced by any face.
    This helper removes such dangling vertices and remaps all face vertex indices so the
    geometry remains compact and consistent.
    """
    used = sorted({vid for f in faces for vid in f.verts})
    mapping = {old_vid: new_vid for new_vid, old_vid in enumerate(used, start=1)}
    new_points = [points[old_vid - 1] for old_vid in used]
    changed = len(used) != len(points) or any(old_vid != mapping[old_vid] for old_vid in used)

    new_faces: List[FaceRecord] = []
    for f in faces:
        new_faces.append(
            FaceRecord(
                fid=f.fid,
                verts=[mapping[vid] for vid in f.verts],
                group=getattr(f, "group", "default"),
                group_material=getattr(f, "group_material", "default"),
                material=getattr(f, "material", "unknown"),
            )
        )

    diag = {
        "status": "ok",
        "vertices_before": len(points),
        "vertices_after": len(new_points),
        "removed_unused_vertices": len(points) - len(new_points),
    }
    return new_faces, new_points, changed, diag

def trim_segment_face_intersections_iterative(
    faces: List["FaceRecord"],
    points: List[Tuple[float, float, float]],
    room_center: Tuple[float, float, float],
    *,
    max_iters: int = 20,
    tol: float = 1e-9,
    logger=None,
) -> Tuple[List["FaceRecord"], List[Tuple[float, float, float]], bool, Dict[str, Any]]:
    """
    Iteratively trim components for remaining segment-face interior intersections.

    Parameters
    ----------
    faces : list[FaceRecord]
        Current face list.
    points : list[(x, y, z)]
        Global mutable vertex list.
    room_center : tuple[float, float, float]
        Reference point used to choose the kept side of the clipping plane.
    max_iters : int
        Maximum number of trim attempts.
    tol : float
        Numerical tolerance for clipping.
    logger : logging.Logger | None
        Optional logger.

    Returns
    -------
    tuple
        (updated_faces, updated_points, changed_any, diagnostics)

    Purpose
    -------
    A single trim usually resolves only one offending connected component. This helper
    repeatedly detects remaining `segment_face_interior_intersection` hits, trims one
    component at a time, compacts the vertex list, and revalidates until no further
    supported hits remain or no progress can be made.
    """
    changed_any = False
    actions = []

    for it in range(1, max_iters + 1):
        plc_hits = detect_segment_facet_intersections_cdt(
            faces,
            points,
            warn_planar_tol_m=1e-4,
            fatal_planar_tol_m=1e-3,
            eps=1e-10,
            bbox_pad=1e-9,
            max_reports=2000,
            skip_warped_faces=True,
            logger=logger,
        )

        seg_face_hits = [
            r
            for r in plc_hits
            if r.get("hit_type") in ("segment_face_interior_intersection", "segment_edge_intersection")
        ]
        if not seg_face_hits:
            diag = {
                "status": "ok" if changed_any else "no_supported_hits",
                "iterations": it - 1,
                "applied_repairs": len(actions),
                "actions": actions,
            }
            return faces, points, changed_any, diag

        target = seg_face_hits[0]
        faces2, points2, changed, trim_diag = trim_component_from_segment_face_intersection_report(
            faces,
            points,
            target,
            room_center,
            tol=tol,
            logger=logger,
        )
        if not changed:
            diag = {
                "status": "stalled",
                "iterations": it,
                "applied_repairs": len(actions),
                "last_trim": trim_diag,
                "actions": actions,
            }
            return faces, points, changed_any, diag

        faces2, points2, compact_changed, compact_diag = compact_vertices_and_remove_unused(faces2, points2)
        action = {
            "iteration": it,
            "target_hit": {
                "edge": target.get("edge"),
                "edge_fids": target.get("edge_fids"),
                "facet_fid": target.get("facet_fid"),
                "point": target.get("point"),
            },
            "trim_diag": trim_diag,
            "compact_diag": compact_diag,
        }
        actions.append(action)
        faces, points = faces2, points2
        changed_any = True

        if logger is not None:
            logger.info(
                "[PLC TRIM LOOP] iter=%d trim_status=%s removed_unused_vertices=%d",
                it,
                trim_diag.get("status"),
                compact_diag.get("removed_unused_vertices", 0),
            )

    diag = {
        "status": "max_iters_reached",
        "iterations": max_iters,
        "applied_repairs": len(actions),
        "actions": actions,
    }
    return faces, points, changed_any, diag

# ------ Trimming Helper

def _clip_face_loop_against_plane(
    face_loop: List[int],
    points: List[Tuple[float, float, float]],
    plane_point: Tuple[float, float, float],
    plane_normal: Tuple[float, float, float],
    keep_sign: float,
    *,
    tol: float = 1e-9,
) -> List[int]:
    """
    Clip one polygon against a plane and keep the selected half-space.

    Parameters
    ----------
    face_loop : list[int]
        Ordered 1-based vertex ids of one polygon face.
    points : list[(x, y, z)]
        Global mutable point list. New intersection vertices may be appended.
    plane_point : tuple[float, float, float]
        A point on the clipping plane.
    plane_normal : tuple[float, float, float]
        Unit plane normal.
    keep_sign : float
        The kept side of the plane. Distances with the same sign as ``keep_sign``
        are kept.
    tol : float
        Numerical tolerance used for clipping and vertex reuse.

    Returns
    -------
    list[int]
        The clipped polygon loop. Returns an empty list when the face is completely
        removed by the clip.

    Notes
    -----
    This is a Sutherland-Hodgman style half-space clip performed directly in 3D.
    """
    if len(face_loop) < 3:
        return []

    def is_inside(sd: float) -> bool:
        return sd * keep_sign >= -tol

    out: List[int] = []
    n = len(face_loop)

    for i in range(n):
        a_vid = face_loop[i]
        b_vid = face_loop[(i + 1) % n]
        A = points[a_vid - 1]
        B = points[b_vid - 1]

        da = _signed_distance_to_plane(A, plane_point, plane_normal)
        db = _signed_distance_to_plane(B, plane_point, plane_normal)
        a_inside = is_inside(da)
        b_inside = is_inside(db)

        if a_inside and b_inside:
            if not out or out[-1] != b_vid:
                out.append(b_vid)
        elif a_inside and not b_inside:
            denom = da - db
            if abs(denom) > tol:
                t = da / denom
                X = (
                    A[0] + t * (B[0] - A[0]),
                    A[1] + t * (B[1] - A[1]),
                    A[2] + t * (B[2] - A[2]),
                )
                x_vid = _get_or_create_vertex_id(points, X, tol=tol)
                if not out or out[-1] != x_vid:
                    out.append(x_vid)
        elif (not a_inside) and b_inside:
            denom = da - db
            if abs(denom) > tol:
                t = da / denom
                X = (
                    A[0] + t * (B[0] - A[0]),
                    A[1] + t * (B[1] - A[1]),
                    A[2] + t * (B[2] - A[2]),
                )
                x_vid = _get_or_create_vertex_id(points, X, tol=tol)
                if not out or out[-1] != x_vid:
                    out.append(x_vid)
            if not out or out[-1] != b_vid:
                out.append(b_vid)

    out = clean_face_loop(out)
    if len(out) >= 2 and out[0] == out[-1]:
        out = out[:-1]
    return out

def _find_face_by_fid(faces: List["FaceRecord"], fid: int) -> "FaceRecord | None":
    """Return the face with the requested face id, or ``None`` if it does not exist."""
    for face in faces:
        if face.fid == fid:
            return face
    return None

def _plane_from_face(face: "FaceRecord", points: List[Tuple[float, float, float]]):
    """
    Build a clipping plane from a face using its Newell normal.

    Parameters
    ----------
    face : FaceRecord
        Face that defines the plane.
    points : list[(x, y, z)]
        Global point list.

    Returns
    -------
    tuple[(x, y, z), (nx, ny, nz)] | None
        A point on the plane and a unit normal, or ``None`` if the face is degenerate.
    """
    if len(face.verts) < 3:
        return None

    nrm = newell_normal_from_points(face.verts, points)
    nn = math.sqrt(nrm[0] * nrm[0] + nrm[1] * nrm[1] + nrm[2] * nrm[2])
    if nn <= 1e-18:
        return None

    plane_point = points[face.verts[0] - 1]
    plane_normal = (nrm[0] / nn, nrm[1] / nn, nrm[2] / nn)
    return plane_point, plane_normal


def _signed_distance_to_plane(
    p: Tuple[float, float, float],
    plane_point: Tuple[float, float, float],
    plane_normal: Tuple[float, float, float],
) -> float:
    """Return the signed distance from ``p`` to a plane."""
    return (
        (p[0] - plane_point[0]) * plane_normal[0]
        + (p[1] - plane_point[1]) * plane_normal[1]
        + (p[2] - plane_point[2]) * plane_normal[2]
    )


def collect_face_component_from_seed_faces(
    faces: List["FaceRecord"],
    seed_face_fids: List[int],
    *,
    excluded_face_fids: List[int] | None = None,
) -> List[int]:
    """
    Collect one connected face component starting from seed faces.

    Parameters
    ----------
    faces : list[FaceRecord]
        Current face list.
    seed_face_fids : list[int]
        Starting faces belonging to the component that should be trimmed.
    excluded_face_fids : list[int] | None
        Faces that must not be entered during traversal, e.g. the clipping facet.

    Returns
    -------
    list[int]
        Sorted face ids belonging to the connected component.

    Notes
    -----
    Connectivity is defined through shared undirected edges.
    """
    excluded = set(excluded_face_fids or [])
    valid_fids = {f.fid for f in faces}
    seeds = [fid for fid in seed_face_fids if fid in valid_fids and fid not in excluded]
    if not seeds:
        return []

    edge_to_fids = _build_edge_face_adjacency(faces)
    face_adj: Dict[int, set] = defaultdict(set)
    for fids in edge_to_fids.values():
        for a in fids:
            for b in fids:
                if a != b:
                    face_adj[a].add(b)

    component = set()
    q = deque(seeds)
    while q:
        fid = q.popleft()
        if fid in component or fid in excluded:
            continue
        component.add(fid)
        for nbr in face_adj.get(fid, []):
            if nbr not in component and nbr not in excluded:
                q.append(nbr)

    return sorted(component)
def _build_edge_face_adjacency(faces: List["FaceRecord"]) -> Dict[Tuple[int, int], List[int]]:
    """Build a map from undirected edge to incident face ids."""
    edge_to_fids: Dict[Tuple[int, int], List[int]] = defaultdict(list)
    for face in faces:
        for u, v in face.undirected_edges():
            edge_to_fids[_uedge(u, v)].append(face.fid)
    return edge_to_fids
def _get_or_create_vertex_id(
    points: List[Tuple[float, float, float]],
    xyz: Tuple[float, float, float],
    *,
    tol: float = 1e-9,
) -> int:
    """
    Reuse an existing vertex if the coordinates already exist within tolerance;
    otherwise append a new vertex and return its 1-based id.
    """
    for i, p in enumerate(points, start=1):
        if (
            abs(p[0] - xyz[0]) <= tol
            and abs(p[1] - xyz[1]) <= tol
            and abs(p[2] - xyz[2]) <= tol
        ):
            return i

    points.append(xyz)
    return len(points)

# ------ End of Trimming Helper


# ------ Repair Segment-Face Intersection 

def repair_plc_single_splits_iterative(
    faces: List[FaceRecord],
    points: List[Tuple[float, float, float]],
    room_center: Tuple[float, float, float],
    *,
    logger=None,
    max_iters: int = 20,
    planarity_tol_m: float = 1e-6,
):
    """
    Iteratively repair PLC endpoint_face_interior_touch cases using:
      1) multi-point same-face triangulation repair
      2) single-point triangulation repair

    Strategy
    --------
    Per iteration:
    - detect PLC hits
    - group endpoint_face_interior_touch by touched face
    - if any face has >1 hit, repair that face first with multi-point repair
    - else if any face has exactly 1 hit, repair one single-hit face
    - re-orient and repeat

    Returns
    -------
    Tuple[List[FaceRecord], bool, dict]
        (updated_faces, changed_any, summary)
    """
    summary = {
        "iterations": 0,
        "applied_repairs": 0,
        "stopped_reason": "unknown",
        "remaining_plc_hits": 0,
        "remaining_endpoint_face_hits": 0,
        "remaining_single_hit_candidates": 0,
        "remaining_multi_hit_faces": 0,
    }

    changed_any = False

    for it in range(1, max_iters + 1):
        summary["iterations"] = it

        plc_hits = detect_segment_facet_intersections_cdt(
            faces,
            points,
            warn_planar_tol_m=1e-4,
            fatal_planar_tol_m=1e-3,
            eps=1e-10,
            bbox_pad=1e-9,
            max_reports=2000,
            skip_warped_faces=True,
            logger=logger,
        )

        summary["remaining_plc_hits"] = len(plc_hits)

        if not plc_hits:
            summary["remaining_plc_hits"] = 0
            summary["remaining_endpoint_face_hits"] = 0
            summary["remaining_single_hit_candidates"] = 0
            summary["remaining_multi_hit_faces"] = 0
            summary["stopped_reason"] = "no_plc_hits"
            if logger:
                logger.info("[PLC REPAIR] stable after %d iterations: no PLC hits", it - 1)
            return faces, points, changed_any, summary
        
        endpoint_face_hits = [
            r
            for r in plc_hits
            if r.get("hit_type") in ("endpoint_face_interior_touch", "endpoint_edge_touch")
        ]
        summary["remaining_endpoint_face_hits"] = len(endpoint_face_hits)

        if not endpoint_face_hits:
            summary["remaining_endpoint_face_hits"] = 0
            summary["remaining_single_hit_candidates"] = 0
            summary["remaining_multi_hit_faces"] = 0
            summary["stopped_reason"] = "no_endpoint_face_hits"
            if logger:
                logger.info("[PLC REPAIR] stop: PLC hits remain, but none are endpoint_face_interior_touch")
            return faces, points, changed_any, summary

        hits_by_face = defaultdict(list)
        for r in endpoint_face_hits:
            hits_by_face[r["facet_fid"]].append(r)

        multi_hit_faces = [fid for fid, rs in hits_by_face.items() if len(rs) > 1]
        single_hit_candidates = [rs[0] for fid, rs in hits_by_face.items() if len(rs) == 1]

        summary["remaining_multi_hit_faces"] = len(multi_hit_faces)
        summary["remaining_single_hit_candidates"] = len(single_hit_candidates)

        if logger:
            logger.info(
                "[PLC REPAIR] iter=%d plc_hits=%d endpoint_face_hits=%d multi_hit_faces=%d single_hit_candidates=%d",
                it,
                len(plc_hits),
                len(endpoint_face_hits),
                len(multi_hit_faces),
                len(single_hit_candidates),
            )

        changed = False
        diag = None

        # ---------------------------------------------------------
        # Priority 1: multi-hit same-face repair
        # ---------------------------------------------------------
        if multi_hit_faces:

            chosen_fid = max(multi_hit_faces, key=lambda fid: len(hits_by_face[fid]))

            chosen_reports = hits_by_face[chosen_fid]

            chosen_face = _find_face_by_fid(faces, chosen_fid)

            cls = classify_multi_hit_face_collinear(

                chosen_face,

                chosen_reports,

                points,

                tol_m=0.01,

            )

            if cls["is_collinear"]:

                if logger:

                    logger.info(

                        "[PLC REPAIR] multi-hit face=%d classified as COLLINEAR (max_dev=%.6g)",

                        chosen_fid,

                        cls["max_dev"],

                    )

                faces, points, changed, diag = repair_multi_hit_face_collinear_chain(

                    faces,

                    chosen_reports,

                    points,

                    logger=logger,

                )

            else:

                if logger:

                    logger.info(

                        "CURRENTLY ONLY COLLINEAR multi-hit repair is implemented; face=%d classified as NONCOLLINEAR (max_dev=%.6g); skipping for now",
                        chosen_fid,
                        cls["max_dev"],
                    )
        # ---------------------------------------------------------
        # Priority 2: single-hit repair
        # ---------------------------------------------------------
        elif single_hit_candidates:
            chosen_report = single_hit_candidates[0]

            if logger:
                logger.info(
                    "[PLC REPAIR] chosen single-hit iter=%d facet_fid=%d edge=%s point=(%.6f,%.6f,%.6f)",
                    it,
                    chosen_report["facet_fid"],
                    chosen_report["edge"],
                    chosen_report["point"][0],
                    chosen_report["point"][1],
                    chosen_report["point"][2],
                )

            faces, changed, diag = repair_single_endpoint_face_interior_touch_by_triangulation(
                faces,
                chosen_report,
                points,
                logger=logger,
                planarity_tol_m=planarity_tol_m,
            )

        else:
            summary["stopped_reason"] = "no_candidates"
            if logger:
                logger.info("[PLC REPAIR] stop: no repair candidates")
            return faces, points, changed_any, summary

        if not changed:
            summary["stopped_reason"] = "selected_candidate_not_changed"
            if logger:
                logger.info("[PLC REPAIR] stop: selected candidate produced no topology change; diag=%s", diag)
            return faces, points, changed_any, summary

        changed_any = True
        summary["applied_repairs"] += 1

        if logger:
            logger.info("[PLC REPAIR] applied iter=%d diag=%s", it, diag)

        # re-orient after topology change
        diag_orient = orient_faces_consistently_by_adjacency(faces, logger=logger)
        if logger:
            logger.info("[ORIENT AFTER PLC REPAIR] iter=%d diag=%s", it, diag_orient)

        flip_all_faces_if_majority_inward(
            faces,
            points,
            room_center,
            logger=logger,
        )

    summary["stopped_reason"] = "max_iters_reached"
    if logger:
        logger.warning("[PLC REPAIR] reached max_iters=%d", max_iters)

    return faces, points, changed_any, summary

def repair_multi_endpoint_face_touch_same_face_by_triangulation(
    faces: List[FaceRecord],
    plc_reports: List[Dict[str, Any]],
    points: List[Tuple[float, float, float]],
    *,
    logger=None,
    planarity_tol_m: float = 1e-6,
):
    """
    Repair one face hit by multiple endpoint_face_interior_touch intersections
    by building one split chain across the face and triangulating both sides.

    Intention
    ---------
    This targets the "small room" pattern:
      - many endpoint_face_interior_touch hits
      - same facet_fid
      - points roughly form one ordered chain across the face

    Strategy
    --------
    1. Collect all unique inserted endpoints on the touched face.
    2. Project face and points to 2D.
    3. Fit one dominant chain direction through the inserted points.
    4. Extend that line to the boundary in both directions.
    5. Insert/reuse two boundary points.
    6. Split the face into 2 polygons using:
         boundary_point_A -> inserted_points_sorted -> boundary_point_B
    7. Triangulate both polygons with triangulate_face_cdt_shapely(...).

    Parameters
    ----------
    faces : List[FaceRecord]
        Current face list.
    plc_reports : list[dict]
        PLC reports that must all belong to the same facet_fid.
    points : list[(x,y,z)]
        Global point list.
    logger : logging.Logger | None
        Optional logger.
    planarity_tol_m : float
        Maximum allowed planarity deviation of the touched face.

    Returns
    -------
    tuple[list[FaceRecord], list[(x,y,z)], bool, dict]
        (updated_faces, updated_points, changed, diagnostics)
    """
    diag = {
        "status": "noop",
        "facet_fid": None,
        "n_hits": 0,
        "n_inserted_points": 0,
        "created_boundary_points": 0,
        "n_output_tris": 0,
    }

    if not plc_reports:
        diag["status"] = "no_reports"
        return faces, points, False, diag

    facet_ids = {r["facet_fid"] for r in plc_reports}
    if len(facet_ids) != 1:
        diag["status"] = "reports_not_same_face"
        return faces, points, False, diag

    facet_fid = next(iter(facet_ids))
    diag["facet_fid"] = facet_fid
    diag["n_hits"] = len(plc_reports)

    fid_to_face = {f.fid: f for f in faces}
    touched_face = fid_to_face.get(facet_fid)
    if touched_face is None:
        diag["status"] = "missing_face"
        return faces, points, False, diag

    pstat, pmax_m, prms_m = classify_face_planarity_m(touched_face.verts, points)
    if pstat == "fatal":
        diag["status"] = "face_nonplanar"
        return faces, points, False, diag

    # --------------------------------------------------
    # 1) Extract unique inserted endpoint vids
    # --------------------------------------------------
    inserted_vids = []
    seen = set()

    for r in plc_reports:
        if r.get("hit_type") != "endpoint_face_interior_touch":
            continue

        edge = r["edge"]
        t = r["t_param"]

        if abs(t) <= 1e-9:
            vid = edge[0]
        elif abs(t - 1.0) <= 1e-9:
            vid = edge[1]
        else:
            continue

        if vid not in seen:
            seen.add(vid)
            inserted_vids.append(vid)

    if len(inserted_vids) < 2:
        diag["status"] = "need_at_least_two_points"
        return faces, points, False, diag

    diag["n_inserted_points"] = len(inserted_vids)

    # --------------------------------------------------
    # 2) Project touched face + inserted points to 2D
    # --------------------------------------------------
    poly_ids = clean_face_loop(touched_face.verts)
    poly2d, dropped_axis = project_face_to_2d(poly_ids, points)

    if area2(poly2d) < 0:
        poly_ids.reverse()
        poly2d.reverse()

    chain_pts_2d = [project_vid_to_2d(vid, points, dropped_axis) for vid in inserted_vids]

    # --------------------------------------------------
    # 3) Fit one dominant chain direction and sort points
    # --------------------------------------------------
    c2, d2 = fit_chain_direction_2d(chain_pts_2d)

    proj_vals = []
    for vid in inserted_vids:
        p2 = project_vid_to_2d(vid, points, dropped_axis)
        s = (p2[0] - c2[0]) * d2[0] + (p2[1] - c2[1]) * d2[1]
        proj_vals.append((s, vid))

    proj_vals.sort(key=lambda x: x[0])
    inserted_vids_sorted = [vid for _, vid in proj_vals]

    # --------------------------------------------------
    # 4) Extend fitted line to both boundary sides
    # --------------------------------------------------
    best_neg = None
    best_pos = None
    edge_neg = None
    edge_pos = None

    n = len(poly2d)
    for i in range(n):
        a2 = poly2d[i]
        b2 = poly2d[(i + 1) % n]

        hit = line_segment_intersection_signed(c2, d2, a2, b2, tol=1e-12)
        if hit is None:
            continue

        s, tseg = hit
        if s < 0.0:
            if best_neg is None or s > best_neg[0]:
                best_neg = (s, tseg)
                edge_neg = i
        elif s > 0.0:
            if best_pos is None or s < best_pos[0]:
                best_pos = (s, tseg)
                edge_pos = i

    if best_neg is None or best_pos is None:
        diag["status"] = "failed_boundary_extension"
        return faces, points, False, diag

    # --------------------------------------------------
    # 5) Create/reuse two boundary points
    # --------------------------------------------------
    bneg_vid, points, used_neg_existing = create_or_reuse_boundary_point_on_edge(
        poly_ids, poly2d, edge_neg, best_neg[1], points
    )
    bpos_vid, points, used_pos_existing = create_or_reuse_boundary_point_on_edge(
        poly_ids, poly2d, edge_pos, best_pos[1], points
    )

    diag["created_boundary_points"] = int(not used_neg_existing) + int(not used_pos_existing)

    # refresh polygon references after possible point insertion
    poly_ids = clean_face_loop(touched_face.verts)
    poly2d, dropped_axis = project_face_to_2d(poly_ids, points)
    if area2(poly2d) < 0:
        poly_ids.reverse()
        poly2d.reverse()

    # insert boundary point A if new
    if bneg_vid not in poly_ids:
        poly_ids = insert_vertex_on_polygon_edge(poly_ids, edge_neg, bneg_vid)

    # insert boundary point B if new
    if bpos_vid not in poly_ids:
        poly2d, dropped_axis = project_face_to_2d(poly_ids, points)
        if area2(poly2d) < 0:
            poly_ids.reverse()
            poly2d.reverse()

        p_bpos_2d = project_vid_to_2d(bpos_vid, points, dropped_axis)
        found_edge = None
        for i in range(len(poly_ids)):
            a2 = poly2d[i]
            b2 = poly2d[(i + 1) % len(poly_ids)]
            if point_on_segment_2d(p_bpos_2d, a2, b2, tol=1e-8):
                found_edge = i
                break

        if found_edge is None:
            diag["status"] = "cannot_reinsert_second_boundary_point"
            return faces, points, False, diag

        poly_ids = insert_vertex_on_polygon_edge(poly_ids, found_edge, bpos_vid)

    if bneg_vid not in poly_ids or bpos_vid not in poly_ids:
        diag["status"] = "boundary_points_not_in_loop"
        return faces, points, False, diag

    # --------------------------------------------------
    # 6) Build chain split and 2 polygons
    # --------------------------------------------------
    chain_vids = [bneg_vid] + inserted_vids_sorted + [bpos_vid]

    idx_neg = poly_ids.index(bneg_vid)
    idx_pos = poly_ids.index(bpos_vid)

    boundary_a = boundary_chain(poly_ids, idx_neg, idx_pos)
    boundary_b = boundary_chain(poly_ids, idx_pos, idx_neg)

    # remove duplicated boundary endpoints before concatenation
    poly_a = clean_face_loop(boundary_a + list(reversed(chain_vids[1:-1])))
    poly_b = clean_face_loop(boundary_b + chain_vids[1:-1])

    split_polys = []
    for poly in (poly_a, poly_b):
        if len(poly) < 3:
            continue
        if polygon_area2_newell(poly, points) <= 1e-22:
            continue
        split_polys.append(poly)

    if len(split_polys) != 2:
        diag["status"] = "invalid_split_polys"
        return faces, points, False, diag

    # --------------------------------------------------
    # 7) Triangulate both polygons
    # --------------------------------------------------
    out_tris = []
    for poly in split_polys:
        if len(poly) == 3:
            tris = [poly]
        else:
            tris = triangulate_face_cdt_shapely(poly, points)

        if not tris:
            diag["status"] = "triangulation_failed"
            return faces, points, False, diag

        for tri in tris:
            if len(set(tri)) < 3:
                continue
            if tri_area2(tri[0], tri[1], tri[2], points) <= 1e-22:
                continue
            out_tris.append(tri)

    if not out_tris:
        diag["status"] = "no_output_tris"
        return faces, points, False, diag

    diag["n_output_tris"] = len(out_tris)

    # --------------------------------------------------
    # 8) Replace touched face with new triangles
    # --------------------------------------------------
    next_fid = max((f.fid for f in faces), default=-1) + 1
    new_faces = []

    for f in faces:
        if f.fid != facet_fid:
            new_faces.append(f)
            continue

        for tri in out_tris:
            new_faces.append(
                FaceRecord(
                    fid=next_fid,
                    verts=tri,
                    group=f.group,
                    group_material=f.group_material,
                    material=f.material,
                )
            )
            next_fid += 1

    diag["status"] = "ok"

    if logger:
        logger.info(
            "[PLC MULTI TRI REPAIR] facet_fid=%d hits=%d inserted=%d created_boundary_points=%d output_tris=%d",
            facet_fid,
            len(plc_reports),
            len(inserted_vids_sorted),
            diag["created_boundary_points"],
            diag["n_output_tris"],
        )

    return new_faces, points, True, diag

# Segment Facet Intersection helper math (2D projection, orientation, segment intersection)
# Note: we want to be robust to near-collinear cases, so we use a tolerance-based approach

def point_on_segment_2d(p, a, b, tol=1e-12):
    """
    Check whether a 2D point p lies on segment ab.

    Parameters
    ----------
    p : tuple[float, float]
        Query point.
    a, b : tuple[float, float]
        Segment endpoints.
    tol : float
        Numerical tolerance.

    Returns
    -------
    bool
        True if p lies on the segment within tolerance.
    """
    if abs(orient(a, b, p)) > tol:
        return False

    return (
        min(a[0], b[0]) - tol <= p[0] <= max(a[0], b[0]) + tol and
        min(a[1], b[1]) - tol <= p[1] <= max(a[1], b[1]) + tol
    )

def tri_area2(i, j, k, points):
    a = points[i - 1]
    b = points[j - 1]
    c = points[k - 1]
    ab = sub(b, a)
    ac = sub(c, a)
    cr = cross(ab, ac)
    return dot(cr, cr)


def segments_intersect_2d(a, b, c, d, tol=1e-12):
    """
    General 2D segment intersection test, including touching cases.

    Parameters
    ----------
    a, b : tuple[float, float]
        Endpoints of first segment.
    c, d : tuple[float, float]
        Endpoints of second segment.
    tol : float
        Numerical tolerance.

    Returns
    -------
    bool
        True if the two segments intersect.
    """
    o1 = orient(a, b, c)
    o2 = orient(a, b, d)
    o3 = orient(c, d, a)
    o4 = orient(c, d, b)

    # proper crossing
    if ((o1 > tol and o2 < -tol) or (o1 < -tol and o2 > tol)) and \
       ((o3 > tol and o4 < -tol) or (o3 < -tol and o4 > tol)):
        return True

    # touching / collinear cases
    if abs(o1) <= tol and point_on_segment_2d(c, a, b, tol):
        return True
    if abs(o2) <= tol and point_on_segment_2d(d, a, b, tol):
        return True
    if abs(o3) <= tol and point_on_segment_2d(a, c, d, tol):
        return True
    if abs(o4) <= tol and point_on_segment_2d(b, c, d, tol):
        return True

    return False


def point_in_polygon_2d(poly, p, tol=1e-12):
    """
    Classify a 2D point relative to a simple polygon.

    Parameters
    ----------
    poly : list[tuple[float, float]]
        Polygon vertices in order.
    p : tuple[float, float]
        Query point.
    tol : float
        Numerical tolerance.

    Returns
    -------
    str
        One of:
        - "inside"
        - "boundary"
        - "outside"
    """
    n = len(poly)

    # boundary check first
    for i in range(n):
        a = poly[i]
        b = poly[(i + 1) % n]
        if point_on_segment_2d(p, a, b, tol):
            return "boundary"

    x, y = p
    inside = False

    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]

        crosses = ((y1 > y) != (y2 > y))
        if crosses:
            xinters = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < xinters:
                inside = not inside

    return "inside" if inside else "outside"


def project_point_by_dropped_axis(p3, dropped_axis):
    """
    Project one 3D point to 2D using the same dropped axis as the face projection.

    Parameters
    ----------
    p3 : tuple[float, float, float]
        3D point.
    dropped_axis : str
        One of "x", "y", "z".

    Returns
    -------
    tuple[float, float]
        Projected 2D point.
    """
    if dropped_axis == "z":
        return (p3[0], p3[1])
    elif dropped_axis == "y":
        return (p3[0], p3[2])
    else:
        return (p3[1], p3[2])


def project_face_to_2d(face_ids, points):
    """
    Project a planar polygon to 2D by dropping the dominant normal axis.

    Parameters
    ----------
    face_ids : list[int]
        Ordered 1-based vertex ids of the polygon.
    points : list[tuple[float, float, float]]
        Global point list.

    Returns
    -------
    tuple[list[tuple[float, float]], str]
        (projected_polygon, dropped_axis)
    """
    nrm = newell_normal_from_points(face_ids, points)
    ax, ay, az = abs(nrm[0]), abs(nrm[1]), abs(nrm[2])

    if az >= ax and az >= ay:
        return ([(points[pid - 1][0], points[pid - 1][1]) for pid in face_ids], "z")
    elif ay >= ax and ay >= az:
        return ([(points[pid - 1][0], points[pid - 1][2]) for pid in face_ids], "y")
    else:
        return ([(points[pid - 1][1], points[pid - 1][2]) for pid in face_ids], "x")


def boundary_chain(poly_ids, i, j):
    """
    Return the ordered boundary chain from polygon index i to j inclusive.

    Parameters
    ----------
    poly_ids : list[int]
        Polygon vertex ids in order.
    i, j : int
        Indices into poly_ids.

    Returns
    -------
    list[int]
        Boundary chain from i to j inclusive.
    """
    n = len(poly_ids)
    out = [poly_ids[i]]
    k = i
    while k != j:
        k = (k + 1) % n
        out.append(poly_ids[k])
    return out


def visible_boundary_vertices_from_point(poly2d, p2, tol=1e-12):
    """
    Compute polygon vertices visible from an interior point.

    Parameters
    ----------
    poly2d : list[tuple[float, float]]
        Simple polygon vertices in order.
    p2 : tuple[float, float]
        Interior point.
    tol : float
        Numerical tolerance.

    Returns
    -------
    list[int]
        Indices of visible boundary vertices.
    """
    n = len(poly2d)
    visible = []

    for i in range(n):
        vi = poly2d[i]
        ok = True

        for k in range(n):
            a = poly2d[k]
            b = poly2d[(k + 1) % n]

            # skip edges incident to vertex i
            if k == i or (k + 1) % n == i:
                continue

            if segments_intersect_2d(p2, vi, a, b, tol):
                ok = False
                break

        if ok:
            visible.append(i)

    return visible


def split_face_at_single_interior_vertex(
    face: FaceRecord,
    inserted_vid: int,
    points: List[Tuple[float, float, float]],
    *,
    planarity_tol_m: float = 1e-6,
    boundary_tol_2d: float = 1e-10,
):
    """
    Split one planar polygon face using one inserted interior vertex.

    Intention
    ---------
    This is the preferred single-split repair for one
    `endpoint_face_interior_touch` case.

    Strategy
    --------
    1. Check the touched face is planar enough.
    2. Project the face and inserted point to 2D.
    3. Require the inserted point to lie strictly inside the polygon.
    4. Find visible boundary vertices from the inserted point.
    5. Prefer a 2-polygon split using two non-adjacent visible vertices.
    6. If that fails, fall back to a triangle fan.

    Parameters
    ----------
    face : FaceRecord
        Touched face to split.
    inserted_vid : int
        1-based vertex id of the touching endpoint.
    points : list[tuple[float, float, float]]
        Global point list.
    planarity_tol_m : float
        Maximum allowed planarity deviation for trying polygon split.
    boundary_tol_2d : float
        2D tolerance for point-in-polygon and visibility checks.

    Returns
    -------
    list[list[int]] | None
        Replacement faces as ordered vertex-id loops, or None if split fails.
    """
    if inserted_vid in face.verts:
        return None

    # 1) planarity check
    max_abs, rms, nu, c = planarity_deviation_m(face.verts, points)
    if not math.isfinite(max_abs) or max_abs > planarity_tol_m:
        return None

    # 2) project face to 2D
    poly_ids = clean_face_loop(face.verts)
    poly2d, dropped_axis = project_face_to_2d(poly_ids, points)

    # ensure CCW for consistency
    if area2(poly2d) < 0:
        poly_ids.reverse()
        poly2d.reverse()

    p2 = project_point_by_dropped_axis(points[inserted_vid - 1], dropped_axis)

    # 3) inserted point must be strictly inside, not boundary
    pos = point_in_polygon_2d(poly2d, p2, tol=boundary_tol_2d)
    if pos != "inside":
        return None

    # 4) visible boundary vertices
    visible = visible_boundary_vertices_from_point(poly2d, p2, tol=boundary_tol_2d)
    if len(visible) < 2:
        return None

    # 5) preferred split: choose farthest non-adjacent visible pair
    best_pair = None
    best_score = -1.0
    n = len(poly_ids)

    for a in visible:
        for b in visible:
            if a >= b:
                continue
            if (a + 1) % n == b or (b + 1) % n == a:
                continue  # adjacent pair is weak; prefer real split

            pa = poly2d[a]
            pb = poly2d[b]
            score = (pa[0] - pb[0])**2 + (pa[1] - pb[1])**2
            if score > best_score:
                best_score = score
                best_pair = (a, b)

    if best_pair is not None:
        i, j = best_pair

        chain_ij = boundary_chain(poly_ids, i, j)
        chain_ji = boundary_chain(poly_ids, j, i)

        poly_a = clean_face_loop(chain_ij + [inserted_vid])
        poly_b = clean_face_loop(chain_ji + [inserted_vid])

        out = []
        for poly in (poly_a, poly_b):
            if len(poly) < 3:
                continue
            if polygon_area2_newell(poly, points) <= 1e-22:
                continue
            out.append(poly)

        if len(out) == 2:
            return out

    # 6) fallback: triangle fan
    out = []
    for i in range(len(poly_ids)):
        a = poly_ids[i]
        b = poly_ids[(i + 1) % len(poly_ids)]
        tri = [a, b, inserted_vid]

        if len(set(tri)) < 3:
            continue
        if tri_area2(tri[0], tri[1], tri[2], points) <= 1e-22:
            continue

        out.append(tri)

    return out if out else None


def polygon_area2_newell(face_ids, points):
    """
    Squared area proxy of polygon using Newell normal.

    Parameters
    ----------
    face_ids : list[int]
        Ordered polygon vertex ids.
    points : list[tuple[float, float, float]]
        Global point list.

    Returns
    -------
    float
        Squared norm of Newell normal.
    """
    nrm = newell_normal_from_points(face_ids, points)
    return dot(nrm, nrm)


def repair_single_endpoint_face_interior_touch(
    faces: List[FaceRecord],
    plc_report: Dict[str, Any],
    points: List[Tuple[float, float, float]],
    *,
    logger=None,
    planarity_tol_m: float = 1e-6,
):
    """
    Repair one single `endpoint_face_interior_touch` PLC report.

    Parameters
    ----------
    faces : list[FaceRecord]
        Current face list.
    plc_report : dict
        One classified PLC report containing at least:
          - hit_type
          - edge
          - t_param
          - facet_fid
    points : list[tuple[float, float, float]]
        Global point list.
    logger : logging.Logger | None
        Optional logger.
    planarity_tol_m : float
        Maximum allowed planarity deviation for polygon split.

    Returns
    -------
    tuple[list[FaceRecord], bool, dict]
        (updated_faces, changed, diagnostics)
    """
    diag = {
        "status": "noop",
        "touched_fid": None,
        "inserted_vid": None,
        "n_new_faces": 0,
    }

    if plc_report.get("hit_type") != "endpoint_face_interior_touch":
        diag["status"] = "wrong_type"
        return faces, False, diag

    facet_fid = plc_report["facet_fid"]
    edge = plc_report["edge"]
    t = plc_report["t_param"]

    if abs(t) <= 1e-9:
        inserted_vid = edge[0]
    elif abs(t - 1.0) <= 1e-9:
        inserted_vid = edge[1]
    else:
        diag["status"] = "bad_t_param"
        return faces, False, diag

    diag["touched_fid"] = facet_fid
    diag["inserted_vid"] = inserted_vid

    fid_to_face = {f.fid: f for f in faces}
    touched_face = fid_to_face.get(facet_fid)
    if touched_face is None:
        diag["status"] = "missing_face"
        return faces, False, diag

    split_polys = split_face_at_single_interior_vertex(
        touched_face,
        inserted_vid,
        points,
        planarity_tol_m=planarity_tol_m,
    )

    if not split_polys:
        diag["status"] = "split_failed"
        if logger:
            logger.warning(
                "[SINGLE SPLIT] failed facet_fid=%d inserted_vid=%d verts=%s",
                facet_fid, inserted_vid, touched_face.verts
            )
        return faces, False, diag

    next_fid = max((f.fid for f in faces), default=-1) + 1
    new_faces = []

    for f in faces:
        if f.fid != facet_fid:
            new_faces.append(f)
            continue

        for poly in split_polys:
            new_faces.append(
                FaceRecord(
                    fid=next_fid,
                    verts=poly,
                    group=f.group,
                    group_material=f.group_material,
                    material=f.material,
                )
            )
            next_fid += 1

    diag["status"] = "ok"
    diag["n_new_faces"] = len(split_polys)

    if logger:
        logger.info(
            "[SINGLE SPLIT] repaired facet_fid=%d inserted_vid=%d -> %d new faces",
            facet_fid, inserted_vid, len(split_polys)
        )

    return new_faces, True, diag

# -----------------------------
# Repair Mode for single endpoint-face interior touch
# -----------------------------

def point_segment_distance_2d(p, a, b):
    """
    Distance from 2D point p to segment ab.

    Parameters
    ----------
    p, a, b : tuple[float, float]
        2D points.

    Returns
    -------
    float
        Euclidean distance from p to segment ab.
    """
    abx = b[0] - a[0]
    aby = b[1] - a[1]
    apx = p[0] - a[0]
    apy = p[1] - a[1]

    ab2 = abx * abx + aby * aby
    if ab2 <= 0.0:
        dx = p[0] - a[0]
        dy = p[1] - a[1]
        return math.sqrt(dx * dx + dy * dy)

    t = (apx * abx + apy * aby) / ab2
    t = max(0.0, min(1.0, t))

    qx = a[0] + t * abx
    qy = a[1] + t * aby

    dx = p[0] - qx
    dy = p[1] - qy
    return math.sqrt(dx * dx + dy * dy)


def project_face_and_point_to_2d(face_ids, point_vid, points):
    """
    Project one face and one point to 2D using dominant-axis projection.

    Parameters
    ----------
    face_ids : list[int]
        Ordered 1-based vertex ids of the face.
    point_vid : int
        1-based vertex id of query point.
    points : list[(x,y,z)]
        Global point list.

    Returns
    -------
    tuple[list[(x,y)], (x,y), str]
        (projected face polygon, projected point, dropped_axis)
    """
    nrm = newell_normal_from_points(face_ids, points)
    ax, ay, az = abs(nrm[0]), abs(nrm[1]), abs(nrm[2])

    if az >= ax and az >= ay:
        poly2d = [(points[pid - 1][0], points[pid - 1][1]) for pid in face_ids]
        p2 = (points[point_vid - 1][0], points[point_vid - 1][1])
        return poly2d, p2, "z"
    elif ay >= ax and ay >= az:
        poly2d = [(points[pid - 1][0], points[pid - 1][2]) for pid in face_ids]
        p2 = (points[point_vid - 1][0], points[point_vid - 1][2])
        return poly2d, p2, "y"
    else:
        poly2d = [(points[pid - 1][1], points[pid - 1][2]) for pid in face_ids]
        p2 = (points[point_vid - 1][1], points[point_vid - 1][2])
        return poly2d, p2, "x"


def classify_endpoint_face_touch_repair_mode(
    plc_report,
    faces,
    points,
    *,
    coplanar_tol_m=1e-6,
    min_interior_clearance_m=1e-4,
    min_face_area2=1e-20,
    min_cross_fraction=0.15,
):
    """
    Decide whether one endpoint_face_interior_touch should use
    structural split or local split.

    Intention
    ---------
    This is the decision rule between:
      - structural_split
      - local_split

    It is designed for your OBJ->Gmsh preprocessing pipeline and focuses
    on planar architectural faces.

    Parameters
    ----------
    plc_report : dict
        One PLC report from detect_segment_facet_intersections_cdt(...).
        Must contain:
          - hit_type
          - edge
          - t_param
          - facet_fid
    faces : list[FaceRecord]
        Current face list.
    points : list[(x,y,z)]
        Global point list.
    coplanar_tol_m : float
        Max allowed distance of the opposite endpoint to the touched face plane
        for the edge to be treated as coplanar with the face.
    min_interior_clearance_m : float
        Minimum 2D distance from inserted point to any boundary edge/vertex
        to consider it a real interior point instead of near-boundary noise.
    min_face_area2 : float
        Minimum polygon area proxy from Newell normal squared.
    min_cross_fraction : float
        Minimum fraction of the face bbox span covered by the edge projection
        to count as a meaningful cross-face structural cut.

    Returns
    -------
    tuple[str, dict]
        ("structural_split" | "local_split" | "reject", diagnostics)

    Diagnostics
    -----------
    Returns a dict with reasons and measured quantities so you can log/debug.
    """
    diag = {
        "facet_fid": None,
        "inserted_vid": None,
        "other_vid": None,
        "coplanar": False,
        "face_ok": False,
        "clear_of_boundary": False,
        "cross_fraction": 0.0,
        "decision": "reject",
        "reasons": [],
    }

    if plc_report.get("hit_type") != "endpoint_face_interior_touch":
        diag["reasons"].append("wrong_hit_type")
        return "reject", diag

    facet_fid = plc_report["facet_fid"]
    edge = plc_report["edge"]
    t = plc_report["t_param"]
    diag["facet_fid"] = facet_fid

    fid_to_face = {f.fid: f for f in faces}
    face = fid_to_face.get(facet_fid)
    if face is None:
        diag["reasons"].append("missing_face")
        return "reject", diag

    if abs(t) <= 1e-9:
        inserted_vid = edge[0]
        other_vid = edge[1]
    elif abs(t - 1.0) <= 1e-9:
        inserted_vid = edge[1]
        other_vid = edge[0]
    else:
        diag["reasons"].append("bad_t_param")
        return "reject", diag

    diag["inserted_vid"] = inserted_vid
    diag["other_vid"] = other_vid

    # --------------------------------------------------
    # 1) face must be valid and reasonably planar
    # --------------------------------------------------
    area2_face = polygon_area2_newell(face.verts, points)
    if area2_face <= min_face_area2:
        diag["reasons"].append("face_too_small_or_degenerate")
        return "reject", diag

    pstat, pmax_m, prms_m = classify_face_planarity_m(face.verts, points)
    if pstat == "fatal":
        diag["reasons"].append("face_nonplanar")
        return "reject", diag

    diag["face_ok"] = True

    # --------------------------------------------------
    # 2) coplanarity test for the touching edge vs face plane
    # --------------------------------------------------
    max_abs, rms, nu, c = planarity_deviation_m(face.verts, points)
    qx, qy, qz = points[other_vid - 1]
    dx = qx - c[0]
    dy = qy - c[1]
    dz = qz - c[2]
    q_dist = abs(nu[0] * dx + nu[1] * dy + nu[2] * dz)

    if q_dist <= coplanar_tol_m:
        diag["coplanar"] = True
    else:
        diag["reasons"].append("edge_not_coplanar_with_face")

    # --------------------------------------------------
    # 3) inserted point should be clearly interior,
    #    not just almost on an existing boundary
    # --------------------------------------------------
    poly_ids = clean_face_loop(face.verts)
    poly2d, p2, dropped_axis = project_face_and_point_to_2d(poly_ids, inserted_vid, points)

    if area2(poly2d) < 0:
        poly_ids.reverse()
        poly2d.reverse()

    min_edge_dist = float("inf")
    min_vert_dist = float("inf")
    n = len(poly2d)

    for i in range(n):
        a = poly2d[i]
        b = poly2d[(i + 1) % n]
        de = point_segment_distance_2d(p2, a, b)
        if de < min_edge_dist:
            min_edge_dist = de

        dvx = p2[0] - a[0]
        dvy = p2[1] - a[1]
        dv = math.sqrt(dvx * dvx + dvy * dvy)
        if dv < min_vert_dist:
            min_vert_dist = dv

    if min(min_edge_dist, min_vert_dist) >= min_interior_clearance_m:
        diag["clear_of_boundary"] = True
    else:
        diag["reasons"].append("point_near_existing_boundary")

    # --------------------------------------------------
    # 4) structural-crossing strength:
    #    does the edge projection span a meaningful fraction of face size?
    # --------------------------------------------------
    p_inserted = p2
    p_other = project_face_and_point_to_2d(poly_ids, other_vid, points)[1]

    minx = min(x for x, y in poly2d)
    maxx = max(x for x, y in poly2d)
    miny = min(y for x, y in poly2d)
    maxy = max(y for x, y in poly2d)

    face_span = max(maxx - minx, maxy - miny)
    edge_span = math.sqrt(
        (p_inserted[0] - p_other[0]) ** 2 +
        (p_inserted[1] - p_other[1]) ** 2
    )

    cross_fraction = (edge_span / face_span) if face_span > 0.0 else 0.0
    diag["cross_fraction"] = cross_fraction

    if cross_fraction < min_cross_fraction:
        diag["reasons"].append("edge_does_not_meaningfully_cross_face")

    # --------------------------------------------------
    # Final decision
    # --------------------------------------------------
    if diag["face_ok"] and diag["clear_of_boundary"]:
        diag["decision"] = "structural_split"
        return "structural_split", diag

    if diag["face_ok"]:
        diag["decision"] = "local_split"
        return "local_split", diag

    diag["decision"] = "reject"
    return "reject", diag


def repair_single_endpoint_face_interior_touch_by_triangulation(
    faces: List[FaceRecord],
    plc_report: Dict[str, Any],
    points: List[Tuple[float, float, float]],
    *,
    logger=None,
    planarity_tol_m: float = 1e-6,
):
    """
    Repair one endpoint_face_interior_touch by:
      1) inserting touching point P through polygon split logic
      2) triangulating the resulting polygon pieces with triangulate_face_cdt_shapely(...)

    Intention
    ---------
    This uses your existing CDT triangulation, but only AFTER the touching
    point has been added to the touched face topology.

    Parameters
    ----------
    faces : List[FaceRecord]
        Current face list.
    plc_report : Dict[str, Any]
        One PLC report with:
          - hit_type
          - edge
          - t_param
          - facet_fid
    points : List[(x,y,z)]
        Global point list.
    logger : logging.Logger | None
        Optional logger.
    planarity_tol_m : float
        Maximum allowed face planarity deviation before split attempt.

    Returns
    -------
    Tuple[List[FaceRecord], bool, Dict[str, Any]]
        (updated_faces, changed, diagnostics)
    """
    diag = {
        "status": "noop",
        "touched_fid": None,
        "inserted_vid": None,
        "n_split_polys": 0,
        "n_output_tris": 0,
    }

    if plc_report.get("hit_type") != "endpoint_face_interior_touch":
        diag["status"] = "wrong_type"
        return faces, False, diag

    facet_fid = plc_report["facet_fid"]
    edge = plc_report["edge"]
    t = plc_report["t_param"]

    if abs(t) <= 1e-9:
        inserted_vid = edge[0]
    elif abs(t - 1.0) <= 1e-9:
        inserted_vid = edge[1]
    else:
        diag["status"] = "bad_t_param"
        return faces, False, diag

    diag["touched_fid"] = facet_fid
    diag["inserted_vid"] = inserted_vid

    fid_to_face = {f.fid: f for f in faces}
    touched_face = fid_to_face.get(facet_fid)
    if touched_face is None:
        diag["status"] = "missing_face"
        return faces, False, diag

    # First: split the touched face so inserted_vid becomes part of topology
    split_polys = split_face_at_single_interior_vertex(
        touched_face,
        inserted_vid,
        points,
        planarity_tol_m=planarity_tol_m,
    )

    if not split_polys:
        diag["status"] = "split_failed"
        return faces, False, diag

    diag["n_split_polys"] = len(split_polys)

    # Then: triangulate each resulting polygon using your existing CDT function
    out_tris = []
    for poly in split_polys:
        if len(poly) < 3:
            continue

        if len(poly) == 3:
            tris = [poly]
        else:
            tris = triangulate_face_cdt_shapely(poly, points)

        if not tris:
            diag["status"] = "triangulation_failed"
            if logger:
                logger.warning(
                    "[PLC TRI REPAIR] triangulation failed facet_fid=%d poly=%s",
                    facet_fid, poly
                )
            return faces, False, diag

        for tri in tris:
            if len(set(tri)) < 3:
                continue
            if tri_area2(tri[0], tri[1], tri[2], points) <= 1e-22:
                continue
            out_tris.append(tri)

    if not out_tris:
        diag["status"] = "no_output_tris"
        return faces, False, diag

    diag["n_output_tris"] = len(out_tris)

    next_fid = max((f.fid for f in faces), default=-1) + 1
    new_faces = []

    for f in faces:
        if f.fid != facet_fid:
            new_faces.append(f)
            continue

        for tri in out_tris:
            new_faces.append(
                FaceRecord(
                    fid=next_fid,
                    verts=tri,
                    group=f.group,
                    group_material=f.group_material,
                    material=f.material,
                )
            )
            next_fid += 1

    diag["status"] = "ok"

    if logger:
        logger.info(
            "[PLC TRI REPAIR] repaired facet_fid=%d inserted_vid=%d split_polys=%d output_tris=%d",
            facet_fid,
            inserted_vid,
            diag["n_split_polys"],
            diag["n_output_tris"],
        )

    return new_faces, True, diag

# Helpers for Multi Point-Face Intersection Classification and Repair
def insert_vertex_on_polygon_edge(poly_ids, edge_index, new_vid):
    """
    Insert a vertex into a polygon loop on a specific edge.

    Intention
    ---------
    Used when a new vertex lies on an existing polygon boundary edge.
    The vertex must be inserted into the polygon vertex order so that
    the polygon boundary remains correct.

    Parameters
    ----------
    poly_ids : list[int]
        Polygon vertex ids in order (cyclic).
    edge_index : int
        Index i meaning the edge is:
            poly_ids[i] -> poly_ids[(i+1) % n]
    new_vid : int
        Vertex id to insert on that edge.

    Returns
    -------
    list[int]
        Updated polygon vertex list with the new vertex inserted.
    """
    n = len(poly_ids)

    if n < 2:
        return poly_ids

    return (
        poly_ids[: edge_index + 1]
        + [new_vid]
        + poly_ids[edge_index + 1 :]
    )
    
def project_vid_to_2d(vid, points, dropped_axis):
    """
    Project one vertex id to 2D using the same dropped axis.

    Parameters
    ----------
    vid : int
        1-based vertex id.
    points : list[(x,y,z)]
        Global point list.
    dropped_axis : str
        One of "x", "y", "z".

    Returns
    -------
    tuple[float, float]
        Projected 2D point.
    """
    x, y, z = points[vid - 1]
    if dropped_axis == "z":
        return (x, y)
    elif dropped_axis == "y":
        return (x, z)
    else:
        return (y, z)

def fit_chain_direction_2d(chain_pts_2d):
    """
    Fit dominant 2D direction through a set of points using PCA.

    Parameters
    ----------
    chain_pts_2d : list[(x,y)]
        2D points.

    Returns
    -------
    tuple[(float,float), (float,float)]
        (centroid, unit_direction)
    """
    arr = np.asarray(chain_pts_2d, dtype=float)
    c = arr.mean(axis=0)

    if len(arr) == 1:
        return (float(c[0]), float(c[1])), (1.0, 0.0)

    if len(arr) == 2:
        d = arr[1] - arr[0]
        n = np.linalg.norm(d)
        if n <= 0.0:
            return (float(c[0]), float(c[1])), (1.0, 0.0)
        d /= n
        return (float(c[0]), float(c[1])), (float(d[0]), float(d[1]))

    centered = arr - c
    cov = centered.T @ centered
    vals, vecs = np.linalg.eigh(cov)
    d = vecs[:, np.argmax(vals)]
    n = np.linalg.norm(d)
    if n <= 0.0:
        return (float(c[0]), float(c[1])), (1.0, 0.0)
    d /= n
    return (float(c[0]), float(c[1])), (float(d[0]), float(d[1]))

def line_segment_intersection_signed(p0, d, a, b, tol=1e-12):
    """
    Intersect infinite line p = p0 + s*d with segment a + t*(b-a).

    Parameters
    ----------
    p0 : tuple[float, float]
        Point on the line.
    d : tuple[float, float]
        Line direction.
    a, b : tuple[float, float]
        Segment endpoints.
    tol : float
        Numerical tolerance.

    Returns
    -------
    tuple[float, float] | None
        (s, t) where:
          - s is signed parameter on the infinite line
          - t is segment parameter in [0,1]
        Returns None if no segment intersection.
    """
    ex = b[0] - a[0]
    ey = b[1] - a[1]

    den = d[0] * ey - d[1] * ex
    if abs(den) <= tol:
        return None

    apx = a[0] - p0[0]
    apy = a[1] - p0[1]

    s = (apx * ey - apy * ex) / den
    t = (apx * d[1] - apy * d[0]) / den

    if t < -tol or t > 1.0 + tol:
        return None

    return (s, t)

def create_or_reuse_boundary_point_on_edge(
    poly_ids,
    poly2d,
    edge_index,
    tseg,
    points,
    *,
    merge_tol_2d=1e-8,
):
    """
    Create or reuse a boundary point on one polygon edge.

    Parameters
    ----------
    poly_ids : list[int]
        Polygon vertex ids in order.
    poly2d : list[(x,y)]
        Matching projected polygon vertices.
    edge_index : int
        Edge index i means poly_ids[i] -> poly_ids[i+1].
    tseg : float
        Segment parameter on the edge.
    points : list[(x,y,z)]
        Global point list.
    merge_tol_2d : float
        Reuse endpoint if hit is within this 2D tolerance.

    Returns
    -------
    tuple[int, list[(x,y,z)], bool]
        (boundary_vid, updated_points, used_existing_vertex)
    """
    n = len(poly_ids)

    a_vid = poly_ids[edge_index]
    b_vid = poly_ids[(edge_index + 1) % n]

    a2 = poly2d[edge_index]
    b2 = poly2d[(edge_index + 1) % n]

    hit2 = (
        a2[0] + tseg * (b2[0] - a2[0]),
        a2[1] + tseg * (b2[1] - a2[1]),
    )

    da = math.sqrt((hit2[0] - a2[0]) ** 2 + (hit2[1] - a2[1]) ** 2)
    db = math.sqrt((hit2[0] - b2[0]) ** 2 + (hit2[1] - b2[1]) ** 2)

    if da <= merge_tol_2d:
        return a_vid, points, True
    if db <= merge_tol_2d:
        return b_vid, points, True

    a3 = points[a_vid - 1]
    b3 = points[b_vid - 1]
    new_p3 = (
        a3[0] + tseg * (b3[0] - a3[0]),
        a3[1] + tseg * (b3[1] - a3[1]),
        a3[2] + tseg * (b3[2] - a3[2]),
    )

    points = points + [new_p3]
    return len(points), points, False

# ---------------------------------------
# Remove Intersection problem with offset
# ---------------------------------------

def dist3(a, b):
    """
    Euclidean distance between two 3D points.

    Parameters
    ----------
    a, b : tuple[float, float, float]
        3D points.

    Returns
    -------
    float
        Distance between a and b.
    """
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    dz = a[2] - b[2]
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def get_touching_endpoint_vid_from_plc_report(plc_report, *, t_eps=1e-9):
    """
    Return the touching endpoint vertex id from a PLC report.

    Parameters
    ----------
    plc_report : dict
        One PLC report from detect_segment_facet_intersections_cdt(...).
        Expected keys:
            - "edge": tuple[int, int]
            - "t_param": float
    t_eps : float
        Tolerance for deciding whether the hit is at the start or end.

    Returns
    -------
    int | None
        Touching endpoint vertex id, or None if not an endpoint hit.
    """
    u, v = plc_report["edge"]
    t = plc_report["t_param"]

    if abs(t) <= t_eps:
        return u
    if abs(t - 1.0) <= t_eps:
        return v
    return None


def get_other_endpoint_vid_from_plc_report(plc_report, *, t_eps=1e-9):
    """
    Return the non-touching endpoint vertex id from a PLC report.

    Parameters
    ----------
    plc_report : dict
        One PLC report from detect_segment_facet_intersections_cdt(...).
    t_eps : float
        Tolerance for deciding whether the hit is at the start or end.

    Returns
    -------
    int | None
        Other endpoint vertex id, or None if not an endpoint hit.
    """
    u, v = plc_report["edge"]
    t = plc_report["t_param"]

    if abs(t) <= t_eps:
        return v
    if abs(t - 1.0) <= t_eps:
        return u
    return None


def compute_face_unit_normal(face_verts, points, *, eps=1e-30):
    """
    Compute a unit normal for one face using Newell's method.

    Parameters
    ----------
    face_verts : list[int]
        Ordered face vertex ids.
    points : list[(x, y, z)]
        Global point list.
    eps : float
        Degeneracy threshold.

    Returns
    -------
    tuple[float, float, float] | None
        Unit normal if valid, otherwise None.
    """
    nx, ny, nz = newell_normal_from_points(face_verts, points)
    nlen = math.sqrt(nx * nx + ny * ny + nz * nz)

    if nlen <= eps:
        return None

    return (nx / nlen, ny / nlen, nz / nlen)


def offset_point_along_vector(point, direction, distance):
    """
    Move a 3D point by a signed distance along a direction vector.

    Parameters
    ----------
    point : tuple[float, float, float]
        Original point.
    direction : tuple[float, float, float]
        Direction vector (assumed normalized).
    distance : float
        Signed offset distance in meters.

    Returns
    -------
    tuple[float, float, float]
        Shifted point.
    """
    return (
        point[0] + direction[0] * distance,
        point[1] + direction[1] * distance,
        point[2] + direction[2] * distance,
    )


def move_touching_endpoint_off_face(
    faces,
    points,
    plc_report,
    *,
    offset_m=0.01,
    logger=None,
    t_eps=1e-9,
):
    """
    Resolve one endpoint_face_interior_touch by moving the touching endpoint
    along the face normal in the direction that SHORTENS the edge.

    Intuition
    ---------
    Two candidate moves are tested:
        P_plus  = P + offset * n
        P_minus = P - offset * n

    The direction that produces the shorter edge to the other endpoint is chosen.
    This usually moves the point to the same side of the face as the other endpoint.

    Important
    ---------
    This is a geometric workaround, not a topological repair.

    Parameters
    ----------
    faces : list[FaceRecord]
        Current face list.
    points : list[(x,y,z)]
        Global point list. Updated in place.
    plc_report : dict
        One PLC report from detect_segment_facet_intersections_cdt(...).
        Required keys:
            - "hit_type"
            - "edge"
            - "facet_fid"
            - "t_param"
    offset_m : float
        Offset distance in meters. Default 0.01 m = 1 cm.
    logger : logging.Logger | None
        Optional logger.
    t_eps : float
        Endpoint classification tolerance.

    Returns
    -------
    tuple[list[(x,y,z)], bool, dict]
        (updated_points, changed, diagnostics)
    """
    diag = {
        "status": "noop",
        "touched_vid": None,
        "other_vid": None,
        "facet_fid": plc_report.get("facet_fid"),
        "old_point": None,
        "new_point": None,
        "normal": None,
        "offset_m": offset_m,
        "len_plus": None,
        "len_minus": None,
        "chosen_direction": None,
    }

    if plc_report.get("hit_type") != "endpoint_face_interior_touch":
        diag["status"] = "wrong_hit_type"
        return points, False, diag

    touched_vid = get_touching_endpoint_vid_from_plc_report(plc_report, t_eps=t_eps)
    other_vid = get_other_endpoint_vid_from_plc_report(plc_report, t_eps=t_eps)

    if touched_vid is None or other_vid is None:
        diag["status"] = "not_an_endpoint_hit"
        return points, False, diag

    diag["touched_vid"] = touched_vid
    diag["other_vid"] = other_vid

    facet_fid = plc_report["facet_fid"]
    fid_to_face = {f.fid: f for f in faces}
    touched_face = fid_to_face.get(facet_fid)

    if touched_face is None:
        diag["status"] = "missing_facet_face"
        return points, False, diag

    normal = compute_face_unit_normal(touched_face.verts, points)
    if normal is None:
        diag["status"] = "invalid_face_normal"
        return points, False, diag

    old_point = points[touched_vid - 1]
    other_point = points[other_vid - 1]

    p_plus = offset_point_along_vector(old_point, normal, +offset_m)
    p_minus = offset_point_along_vector(old_point, normal, -offset_m)

    len_plus = dist3(p_plus, other_point)
    len_minus = dist3(p_minus, other_point)

    diag["old_point"] = old_point
    diag["normal"] = normal
    diag["len_plus"] = len_plus
    diag["len_minus"] = len_minus

    if len_plus < len_minus:
        new_point = p_plus
        chosen = "+normal"
    else:
        new_point = p_minus
        chosen = "-normal"

    points[touched_vid - 1] = new_point

    diag["status"] = "ok"
    diag["new_point"] = new_point
    diag["chosen_direction"] = chosen

    if logger:
        logger.info(
            "[PLC OFFSET] moved vid=%d away from facet_fid=%d by %.6f m "
            "using shorter-edge rule other_vid=%d "
            "len(+n)=%.6f len(-n)=%.6f chosen=%s "
            "old=(%.6f,%.6f,%.6f) new=(%.6f,%.6f,%.6f) normal=(%.6f,%.6f,%.6f)",
            touched_vid,
            facet_fid,
            offset_m,
            other_vid,
            len_plus,
            len_minus,
            chosen,
            old_point[0], old_point[1], old_point[2],
            new_point[0], new_point[1], new_point[2],
            normal[0], normal[1], normal[2],
        )

    return points, True, diag

def repair_plc_by_offset_iterative(
    faces,
    points,
    *,
    logger=None,
    max_iters=20,
    offset_m=0.1,
):
    """
    Iteratively remove endpoint_face_interior_touch intersections by offsetting
    the touching endpoint away from the touched face.

    Strategy
    --------
    - detect PLC intersections
    - select endpoint_face_interior_touch cases
    - move one touching endpoint by offset_m along the touched face normal
    - re-run detection
    - repeat until stable or max_iters reached

    Parameters
    ----------
    faces : list[FaceRecord]
        Current face list.
    points : list[(x,y,z)]
        Global point list. Updated in place.
    logger : logging.Logger | None
        Optional logger.
    max_iters : int
        Maximum number of offset-repair iterations.
    offset_m : float
        Offset distance in meters. Default 0.01 m = 1 cm.

    Returns
    -------
    tuple[list[(x,y,z)], bool, dict]
        (updated_points, changed_any, summary)

    Summary keys
    ------------
    - iterations
    - applied_repairs
    - stopped_reason
    - remaining_plc_hits
    - remaining_endpoint_face_hits
    """
    summary = {
        "iterations": 0,
        "applied_repairs": 0,
        "stopped_reason": "unknown",
        "remaining_plc_hits": 0,
        "remaining_endpoint_face_hits": 0,
    }

    changed_any = False

    for it in range(1, max_iters + 1):
        summary["iterations"] = it

        plc_hits = detect_segment_facet_intersections_cdt(
            faces,
            points,
            warn_planar_tol_m=1e-4,
            fatal_planar_tol_m=1e-3,
            eps=1e-10,
            bbox_pad=1e-9,
            max_reports=2000,
            skip_warped_faces=True,
            logger=logger,
        )

        summary["remaining_plc_hits"] = len(plc_hits)

        if not plc_hits:
            summary["remaining_endpoint_face_hits"] = 0
            summary["stopped_reason"] = "no_plc_hits"
            if logger:
                logger.info("[PLC OFFSET] stable after %d iterations: no PLC hits", it - 1)
            return points, changed_any, summary

        endpoint_face_hits = [
            r for r in plc_hits
            if r.get("hit_type") == "endpoint_face_interior_touch"
        ]
        summary["remaining_endpoint_face_hits"] = len(endpoint_face_hits)

        if not endpoint_face_hits:
            summary["stopped_reason"] = "no_endpoint_face_interior_touch"
            if logger:
                logger.info("[PLC OFFSET] stop: PLC hits remain, but none are endpoint_face_interior_touch")
            return points, changed_any, summary

        # Apply one repair at a time, then re-detect.
        target = endpoint_face_hits[0]

        points, changed, diag = move_touching_endpoint_off_face(
            faces,
            points,
            target,
            offset_m=offset_m,
            logger=logger,
        )

        if not changed:
            summary["stopped_reason"] = "selected_offset_not_applied"
            if logger:
                logger.info("[PLC OFFSET] stop: selected report was not changed; diag=%s", diag)
            return points, changed_any, summary

        changed_any = True
        summary["applied_repairs"] += 1

        if logger:
            logger.info("[PLC OFFSET] applied iter=%d diag=%s", it, diag)

    summary["stopped_reason"] = "max_iters_reached"
    if logger:
        logger.warning("[PLC OFFSET] reached max_iters=%d", max_iters)

    return points, changed_any, summary

# -------- REPAIR MULTI HIT POINT-FACE INTERSECTION BY SPLITTING WITH NEW VERTEX --------
def _find_face_by_fid(faces: List["FaceRecord"], fid: int):

    for f in faces:

        if f.fid == fid:

            return f

    return None

def _norm(v):

    return math.sqrt(sum(x * x for x in v))

def _sub(a, b):

    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])

def _dot(a, b):

    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]

def _cross(a, b):

    return (

        a[1]*b[2] - a[2]*b[1],

        a[2]*b[0] - a[0]*b[2],

        a[0]*b[1] - a[1]*b[0],

    )

def _unit(v):

    n = _norm(v)

    if n <= 1e-30:

        return (0.0, 0.0, 0.0)

    return (v[0]/n, v[1]/n, v[2]/n)

def _distance(a, b):

    return _norm(_sub(a, b))

def _face_plane_basis(face, points):

    """

    Return centroid + orthonormal basis (u,v,n) for face plane.

    """

    n = newell_normal_from_points(face.verts, points)

    n = _unit(n)

    c = polygon_centroid(face.verts, points)

    # choose tangent axis

    ref = (1.0, 0.0, 0.0)

    if abs(_dot(ref, n)) > 0.9:

        ref = (0.0, 1.0, 0.0)

    u = _unit(_cross(ref, n))

    v = _unit(_cross(n, u))

    return c, u, v, n

def _project_to_face_2d(p, c, u, v):

    """

    Project 3D point to local face 2D coordinates.

    """

    d = _sub(p, c)

    return (_dot(d, u), _dot(d, v))

def _point_from_2d(xy, c, u, v):

    """

    Convert local 2D back to 3D point.

    """

    return (

        c[0] + xy[0]*u[0] + xy[1]*v[0],

        c[1] + xy[0]*u[1] + xy[1]*v[1],

        c[2] + xy[0]*u[2] + xy[1]*v[2],

    )

def polygon_centroid(

    loop_vids: List[int],

    points: List[Tuple[float, float, float]],

) -> Tuple[float, float, float]:

    """

    Compute the centroid of a polygon from its vertex coordinates.

    Parameters

    ----------

    loop_vids : list[int]

        Ordered 1-based vertex ids of the polygon.

    points : list[(x, y, z)]

        Global vertex list.

    Returns

    -------

    tuple[float, float, float]

        Approximate centroid of the polygon.

    Notes

    -----

    - Uses arithmetic mean of polygon vertices.

    - Stable and sufficient for:

        * face-plane reference point

        * orientation tests

        * local projection basis origin

    - Does not require triangulation.

    """

    if not loop_vids:

        raise ValueError("polygon_centroid(): empty vertex loop")

    sx = sy = sz = 0.0

    n = len(loop_vids)

    for vid in loop_vids:

        p = points[vid - 1]   # 1-based ids

        sx += p[0]

        sy += p[1]

        sz += p[2]

    return (sx / n, sy / n, sz / n)

def _get_or_create_vertex(points, p, tol=1e-9):

    for i, q in enumerate(points, start=1):

        if _distance(p, q) <= tol:

            return i

    points.append(p)

    return len(points)

# ----------------------------------------------------------

# 1. Classify multi-hit same-face collinearity

# ----------------------------------------------------------

def classify_multi_hit_face_collinear(

    face: "FaceRecord",

    reports: List[Dict[str, Any]],

    points: List[Tuple[float, float, float]],

    *,

    tol_m: float = 1e-4,

):

    """

    Determine whether touch points on one face are approximately collinear.

    Returns

    -------

    dict:

        {

          "is_collinear": bool,

          "ordered_points_2d": [...],

          "ordered_points_3d": [...],

          "max_dev": float

        }

    """

    if len(reports) < 2:

        return {

            "is_collinear": False,

            "reason": "need_at_least_2_points",

        }

    c, u, v, n = _face_plane_basis(face, points)

    pts3 = [r["point"] for r in reports]

    pts2 = [_project_to_face_2d(p, c, u, v) for p in pts3]

    # choose farthest pair

    best_i = 0

    best_j = 1

    best_d = -1.0

    for i in range(len(pts2)):

        for j in range(i + 1, len(pts2)):

            d = math.dist(pts2[i], pts2[j])

            if d > best_d:

                best_d = d

                best_i, best_j = i, j

    a = pts2[best_i]

    b = pts2[best_j]

    dx = b[0] - a[0]

    dy = b[1] - a[1]

    L = math.sqrt(dx*dx + dy*dy)

    if L <= 1e-12:

        return {

            "is_collinear": False,

            "reason": "degenerate_points",

        }

    # perpendicular distances

    max_dev = 0.0

    params = []

    for p in pts2:

        px = p[0] - a[0]

        py = p[1] - a[1]

        t = (px*dx + py*dy) / (L*L)

        params.append(t)

        perp = abs(px*dy - py*dx) / L

        max_dev = max(max_dev, perp)

    ordered = sorted(zip(params, pts2, pts3), key=lambda x: x[0])
    logger.info("IM HERE 2")
    logger.info("max_dev: %f", max_dev)
    logger.info("tol_m: %f", tol_m)

    return {

        "is_collinear": max_dev <= 0.01,

        "max_dev": max_dev,

        "ordered_points_2d": [x[1] for x in ordered],

        "ordered_points_3d": [x[2] for x in ordered],

    }

# ----------------------------------------------------------

# 2. Structured connection repair

# ----------------------------------------------------------

def repair_multi_hit_face_collinear_chain(

    faces: List["FaceRecord"],

    reports: List[Dict[str, Any]],

    points: List[Tuple[float, float, float]],

    *,

    logger=None,

):

    """

    Replace one touched face by structured split following collinear chain.

    Strategy:

    - take touched face

    - insert ordered touch vertices

    - connect chain to nearest two boundary vertices

    - split into two polygons

    Returns

    -------

    faces, points, changed, diag

    """

    facet_fid = reports[0]["facet_fid"]

    face = _find_face_by_fid(faces, facet_fid)

    if face is None:

        return faces, points, False, {"status": "face_not_found"}

    cls = classify_multi_hit_face_collinear(face, reports, points)
    logger.info("im heree")
    logger.info("cls=%s", cls)
    if not cls["is_collinear"]:

        return faces, points, False, {"status": "not_collinear"}

    chain_vids = []

    for p in cls["ordered_points_3d"]:

        vid = _get_or_create_vertex(points, p)

        chain_vids.append(vid)

    # choose nearest boundary vertices to chain ends

    face_pts = [points[v - 1] for v in face.verts]

    start_vid = min(

        face.verts,

        key=lambda vid: _distance(points[vid - 1], points[chain_vids[0] - 1])

    )

    end_vid = min(

        face.verts,

        key=lambda vid: _distance(points[vid - 1], points[chain_vids[-1] - 1])

    )

    split_chain = [start_vid] + chain_vids + [end_vid]

    # build two loops along original boundary

    verts = face.verts

    i0 = verts.index(start_vid)

    i1 = verts.index(end_vid)

    if i0 <= i1:

        path1 = verts[i0:i1 + 1]

        path2 = verts[i1:] + verts[:i0 + 1]

    else:

        path1 = verts[i0:] + verts[:i1 + 1]

        path2 = verts[i1:i0 + 1]

    new_loop1 = clean_face_loop(path1 + list(reversed(split_chain[1:-1])))

    new_loop2 = clean_face_loop(path2 + split_chain[1:-1])

    if len(new_loop1) < 3 or len(new_loop2) < 3:

        return faces, points, False, {"status": "bad_split"}

    # replace face

    new_faces = []

    for f in faces:

        if f.fid != facet_fid:

            new_faces.append(f)

        else:

            new_faces.append(FaceRecord(

                fid=f.fid,

                verts=new_loop1,

                group=f.group,

                group_material=f.group_material,

                material=f.material,

            ))

            new_faces.append(FaceRecord(

                fid=max(ff.fid for ff in faces) + 1,

                verts=new_loop2,

                group=f.group,

                group_material=f.group_material,

                material=f.material,

            ))

    diag = {

        "status": "ok",

        "repair_type": "collinear_chain_split",

        "facet_fid": facet_fid,

        "n_chain_points": len(chain_vids),

    }

    if logger:

        logger.info("[PLC REPAIR] structured collinear split face=%d", facet_fid)

    return new_faces, points, True, diag

def orient_faces_consistently_by_adjacency(
    faces: "List[FaceRecord]",
    logger=None,
) -> Dict[str, Any]:
    """
    Make polygon winding globally consistent across shared edges.
    Guarantee: for every manifold shared edge (used by exactly 2 faces),
    the edge direction is opposite in the two faces.
    Returns diagnostics:
      {
        "components": int,
        "flipped_faces": int,
        "boundary_edges": int,
        "nonmanifold_edges": int
      }
    """

    def uedge(a: int, b: int) -> Tuple[int, int]:
        return (a, b) if a < b else (b, a)

    # For each face, we need to know its directed edges.
    # We'll store per undirected edge the directed form as it appears in the face.
    # Example: if face uses edge as (a->b) we store dir=(a,b).
    edge_to_uses: Dict[Tuple[int, int], List[Tuple[int, Tuple[int, int]]]] = defaultdict(list)

    for fi, f in enumerate(faces):
        vs = f.verts
        n = len(vs)
        if n < 2:
            continue
        for i in range(n):
            a = vs[i]
            b = vs[(i + 1) % n]
            edge_to_uses[uedge(a, b)].append((fi, (a, b)))

    boundary_edges = 0
    nonmanifold_edges = 0
    for e, uses in edge_to_uses.items():
        if len(uses) == 1:
            boundary_edges += 1
        elif len(uses) > 2:
            nonmanifold_edges += 1

    if logger:
        logger.info(
            "[ORIENT] edges=%d boundary=%d nonmanifold=%d",
            len(edge_to_uses), boundary_edges, nonmanifold_edges
        )

    # Build face adjacency graph via manifold edges (exactly 2 incident faces)
    face_adj: Dict[int, List[Tuple[int, Tuple[int,int], Tuple[int,int]]]] = defaultdict(list)
    # entry: face_adj[fa].append((fb, undirected_edge, (fa_dir), (fb_dir))) but we can keep dirs separately.

    for e, uses in edge_to_uses.items():
        if len(uses) != 2:
            continue  # skip boundary and nonmanifold for propagation (can't enforce)
        (f0, dir0), (f1, dir1) = uses
        face_adj[f0].append((f1, e, dir0, dir1))
        face_adj[f1].append((f0, e, dir1, dir0))

    # BFS over connected components
    visited = [False] * len(faces)
    flipped = [False] * len(faces)  # whether we have flipped face fi relative to its original
    flipped_count = 0
    components = 0

    def flip_face(fi: int):
        nonlocal flipped_count
        faces[fi].verts.reverse()
        flipped[fi] = not flipped[fi]
        flipped_count += 1

    for seed in range(len(faces)):
        if visited[seed]:
            continue

        # If isolated face (no manifold adjacency), still counts as a component
        components += 1
        visited[seed] = True
        q = deque([seed])

        while q:
            fa = q.popleft()
            for (fb, e, dir_a, dir_b) in face_adj.get(fa, []):
                if not visited[fb]:
                    # We want edge direction opposite between faces.
                    # If fa uses e as (u->v), then fb must use (v->u).
                    # Our stored dir_* are directed pairs as they appear in the *current* face ordering.
                    # BUT note: if we already flipped fa earlier, dir_a from the map is stale.
                    # So we must recompute the current directed edge in each face on the fly.
                    #
                    # To do that, we find the direction of e in the current loop of fa and fb.

                    def current_edge_dir(face_verts: List[int], undirected_edge: Tuple[int,int]) -> Optional[Tuple[int,int]]:
                        u, v = undirected_edge
                        n = len(face_verts)
                        for i in range(n):
                            a = face_verts[i]
                            b = face_verts[(i + 1) % n]
                            if (a == u and b == v) or (a == v and b == u):
                                return (a, b)
                        return None

                    da = current_edge_dir(faces[fa].verts, e)
                    db = current_edge_dir(faces[fb].verts, e)

                    if da is None or db is None:
                        # should not happen unless face loops changed strangely
                        if logger:
                            logger.warning("[ORIENT] missing edge %s in fa=%d or fb=%d", e, fa, fb)
                        visited[fb] = True
                        q.append(fb)
                        continue

                    # If same direction, flip neighbor to make it opposite
                    if da == db:
                        flip_face(fb)
                        if logger:
                            logger.debug("[ORIENT] flipped face fid=%d to fix shared edge %s", faces[fb].fid, e)

                    visited[fb] = True
                    q.append(fb)
                else:
                    # already visited; we could optionally verify consistency
                    pass

    return {
        "components": components,
        "flipped_faces": flipped_count,
        "boundary_edges": boundary_edges,
        "nonmanifold_edges": nonmanifold_edges,
    }
