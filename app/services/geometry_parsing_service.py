import rhino3dm
import logging
from typing import List, Tuple, Dict
from app.utils.geometry_utils import FaceRecord
import logging
logger = logging.getLogger(__name__)

def extract_rhino_materials(rhino3dm_path: str) -> List[str]:
    """
    Extract material IDs from a Rhino .3dm file.
    # -----------------------------
    # 1) Rhino materials
    # -----------------------------
    # Read the Rhino .3dm file and extract material names assigned to each mesh object.
    # These material names are stored as user strings on the geometry and are mapped
    # by object ID so they can later be associated with the corresponding OBJ faces.
    
    Parameters
    ----------
    rhino3dm_path : str
        Path to the Rhino .3dm file.

    Returns
    -------
    list[str]
        List of material IDs found in the file.
    """
    model = rhino3dm.File3dm.Read(rhino3dm_path)
    material_to_id = {}
    for obj in model.Objects:
        if isinstance(obj.Geometry, rhino3dm.Mesh):
            material_name = obj.Geometry.GetUserString("material_name")
            if material_name:
                material_to_id[f"{obj.Attributes.Id}"] = material_name

    material_id_array = list(material_to_id.keys())
    return material_id_array

def parse_obj_file(obj_file: str) -> Tuple[List[Tuple[float, float, float]], List[List[int]], List[str], List[str]]:
    """
    Parse an OBJ file to extract vertices, faces, groups, and materials.

    Parameters
    ----------
    obj_file : str
        Path to the OBJ file.

    Returns
    -------
    tuple
        (vertices, raw_faces, face_groups, face_group_materials)
        - vertices: list of (x, y, z) tuples
        - raw_faces: list of face vertex indices
        - face_groups: list of group names for each face
        - face_group_materials: list of material names for each face
    """
    vertices = []
    raw_faces = []
    face_groups = []
    face_group_materials = []
    current_group = "default"
    current_group_material = "default"

    with open(obj_file, "r") as f:
        created_by_sketchup = False
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if (line.startswith("#") and "SketchUp" in line):
                created_by_sketchup = True
            if line.startswith("v "):
                parts = line.split()
                x, y, z = map(float, parts[1:4])
                # SketchUp (Y-up, left-handed) -> Gmsh (right-handed), flip Z
                vertices.append((x, -z, y))
            elif line.startswith("g "):
                parts = line.split()[1:]
                parts = [p for p in parts if not p.startswith("Mesh") and not p.startswith("Model")]
                current_group = parts[0] if parts else "default"
            elif line.startswith("usemtl "):
                parts = line.split()[1:]
                logger.info(f"Material directive: {parts[0]}")
                current_group_material = parts[0] if parts else "default"
            elif line.startswith("f "):
                parts = line.split()[1:]
                idxs = [int(p.split("/")[0]) for p in parts]
                raw_faces.append(idxs)
                face_groups.append(current_group)
                face_group_materials.append(current_group_material)

    return vertices, raw_faces, face_groups, face_group_materials

def deduplicate_vertices(vertices: List[Tuple[float, float, float]], tol: float = 1e-2) -> Tuple[List[Tuple[float, float, float]], Dict[int, int]]:
    """
    Deduplicate vertices within a tolerance and create a mapping from original indices to unique indices.

    Parameters
    ----------
    vertices : list[tuple[float, float, float]]
        List of vertex coordinates.
    tol : float
        Tolerance for considering vertices as duplicates.

    Returns
    -------
    tuple
        (unique_vertices, orig_to_unique)
        - unique_vertices: list of unique vertex coordinates
        - orig_to_unique: dict mapping original 1-based indices to unique 1-based indices
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

    logger.info("03. Deduplicated vertices:")
    logger.info(f"    unique_vertices: {len(unique_vertices)}")
    
    return unique_vertices, orig_to_unique

def clean_face_loop(verts: List[int]) -> List[int]:
    """
    Remove:
      • consecutive duplicates (..., a, a, ...)
      • closing duplicate (first == last)
    Keeps polygon order intact.
    """

    if not verts:
        return verts

    cleaned = [verts[0]]

    # Remove consecutive duplicates
    for v in verts[1:]:
        if v != cleaned[-1]:
            cleaned.append(v)

    # Remove closing duplicate
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1]:
        cleaned.pop()

    return cleaned

def process_and_instantiate_faces(
    raw_faces: List[List[int]],
    face_groups: List[str],
    face_group_materials: List[str],
    material_id_array: List[str],
    orig_to_unique: Dict[int, int],
) -> List[FaceRecord]:
    """
    Process raw faces by mapping vertex indices to unique indices, cleaning face loops,
    and creating FaceRecord objects for each face.

    Parameters
    ----------
    raw_faces : List[List[int]]
        List of raw face vertex indices.
    face_groups : List[str]
        List of group names for each face.
    face_group_materials : List[str]
        List of material names for each face.
    material_id_array : List[str]
        List of material IDs corresponding to each face.
    orig_to_unique : Dict[int, int]
        Mapping from original vertex indices to unique vertex indices.

    Returns
    -------
    List[FaceRecord]
        List of FaceRecord objects representing the processed faces.
    """
    

    faces = []
    face_id = 0

    for raw_face, grp, grp_mat, mat in zip(raw_faces, face_groups, face_group_materials, material_id_array):
        mapped = [orig_to_unique[i] for i in raw_face]
        mapped = clean_face_loop(mapped)

        sub_faces = [mapped]
            
        if not sub_faces:
            logger.error("[FACE] face_id=%d produced 0 sub_faces (mapped=%s)", face_id, mapped)
        for verts in sub_faces:
            faces.append(FaceRecord(fid=face_id, verts=verts, group=grp, group_material=grp_mat, material=mat))
            face_id += 1
    return faces
