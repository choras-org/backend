from collections import defaultdict
import json
import logging
from typing import List, Dict, Any, Tuple
from app.utils.geometry_utils import FaceRecord, _uedge

logger = logging.getLogger(__name__)

def export_processed_topology_to_gmsh_geo(
    faces: List[FaceRecord],
    unique_vertices: List[Tuple[float, float, float]],
    geo_file: str,
    volume_name: str = "RoomVolume",
) -> Tuple[int, int]:
    """
    Export processed topology to Gmsh GEO file.

    Parameters
    ----------
    faces : List[FaceRecord]
        List of processed FaceRecord objects.
    unique_vertices : List[Tuple[float, float, float]]
        List of unique vertex coordinates.
    geo_file : str
        Path to the output GEO file.
    volume_name : str
        Name for the physical volume.

    Returns
    -------
    Tuple[int, int]
        (num_lines, num_surfaces)
    """
    # -----------------------------
    # Build unique edges (Lines) + signed loops
    # -----------------------------
    edge_to_line: Dict = {}
    line_orientation: Dict = {}
    next_line_id = 1
    face_line_loops: List[List[int]] = []

    for face in faces:
        loop_line_ids = []
        n = len(face.verts)
        for i in range(n):
            a = face.verts[i]
            b = face.verts[(i + 1) % n]
            key = _uedge(a, b)
            if key not in edge_to_line:
                edge_to_line[key] = next_line_id
                line_orientation[next_line_id] = (a, b)
                next_line_id += 1
            lid = edge_to_line[key]
            ori = line_orientation[lid]
            loop_line_ids.append(lid if ori == (a, b) else -lid)
        face_line_loops.append(loop_line_ids)
        
    # Physical surface groups: material -> list of 0-based face indices
    physical_surfaces_dict: Dict = {}
    for idx, face in enumerate(faces):
        physical_surfaces_dict.setdefault(face.material, []).append(idx)

    logger.info("Physical surfaces: %s", {
        mat: len(ids) for mat, ids in physical_surfaces_dict.items()
    })

    # -----------------------------
    # Write GEO
    # -----------------------------
    with open(geo_file, "w") as g:
        # Points
        for i, v in enumerate(unique_vertices, start=1):
            g.write(f"Point({i}) = {{ {v[0]}, {v[1]}, {v[2]}, 1.0 }};\n")
        g.write("\n")

        # Lines
        for lid in range(1, next_line_id):
            a, b = line_orientation[lid]
            g.write(f"Line({lid}) = {{ {a}, {b} }};\n")
        g.write("\n")

        # Line Loops
        for sid, (loop, face) in enumerate(zip(face_line_loops, faces), start=1):
            loop_str = ", ".join(str(x) for x in loop)

            # g.write(f"// fid={face.fid} group={face.group} material={face.material}\n")
            g.write(f"Line Loop({sid}) = {{ {loop_str} }};\n")
        g.write("\n")

        # Plane Surfaces
        for sid in range(1, len(face_line_loops) + 1):
            g.write(f"Plane Surface({sid}) = {{ {sid} }};\n")
        g.write("\n")

        # Surface Loop + Volume
        total_surfaces = len(face_line_loops)
        surf_list = ", ".join(str(i) for i in range(1, total_surfaces + 1))
        g.write(f"Surface Loop(1) = {{ {surf_list} }};\n")
        g.write("Volume(1) = { 1 };\n")
        g.write(f'Physical Volume("{volume_name}") = {{ 1 }};\n')

        # Physical Surfaces
        for mat, surface_indices in physical_surfaces_dict.items():
            gmsh_ids = ", ".join(str(i + 1) for i in surface_indices)
            g.write(f'Physical Surface("{mat}") = {{ {gmsh_ids} }};\n')

        # Physical Lines
        lines_all = ", ".join(str(i) for i in range(1, next_line_id))
        g.write(f'Physical Line("default") = {{ {lines_all} }};\n')

        # Mesh options
        g.write('Mesh.Algorithm = 6;\n')
        g.write('Mesh.Algorithm3D = 1; // Delaunay3D\n')
        g.write('Mesh.Optimize = 1;\n')
        g.write('Mesh.CharacteristicLengthFromPoints = 1;\n')

    return next_line_id - 1, len(face_line_loops)

def export_processed_topology_to_obj(
    obj_output_path: str,
    unique_vertices: list,
    faces: "List[FaceRecord]",
) -> bool:
    """
    Export the processed topology to an OBJ file.
    Args:
        obj_output_path : destination path
        unique_vertices : list of (x, y, z) tuples, 0-based (vertex id i -> index i-1)
        faces           : list of FaceRecord (each carries verts, group, material)
    """
    try:
        # Group faces by group first, then by group_material
        faces_by_group_and_material: dict = defaultdict(lambda: defaultdict(list))
        for face in faces:
            faces_by_group_and_material[face.group][face.group_material].append(face)

        with open(obj_output_path, "w") as f:
            f.write("# Processed topology from geometry conversion\n\n")

            # Vertices
            for x, y, z in unique_vertices:
                # previously we flipped z, now flip back for OBJ export
                f.write(f"v {x} {z} {-y}\n")

            f.write("\n")

            # Faces grouped by group, then by group_material
            for group in sorted(faces_by_group_and_material.keys()):
                f.write(f"\ng {group}\n")
                for group_material in sorted(faces_by_group_and_material[group].keys()):
                    f.write(f"usemtl {group_material}\n")
                    for face in faces_by_group_and_material[group][group_material]:
                        f.write("f " + " ".join(f"{v}//1" for v in face.verts) + "\n")
        return True

    except Exception as ex:
        logger.error("Failed to export processed topology to OBJ: %s", ex)
        return False

def export_faces_to_json(faces, filepath):
    """
    Export FaceRecord list to JSON for debugging.

    Parameters
    ----------
    faces : list[FaceRecord]
    filepath : str
    """
    data = []

    for f in faces:
        data.append({
            "fid": f.fid,
            "verts": f.verts,
            "group": getattr(f, "group", None),
            "group_material": getattr(f, "group_material", None),
            "material": getattr(f, "material", None),
        })

    with open(filepath, "w") as fp:
        json.dump(data, fp, indent=2)

    print(f"[DEBUG] Exported {len(faces)} faces → {filepath}")
