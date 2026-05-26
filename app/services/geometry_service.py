import logging
import os
import zipfile

import rhino3dm
from flask_smorest import abort

import config
from app.db import db
from app.factory.geometry_converter_factory.GeometryConversionFactory import (
    GeometryConversionFactory,
)
from app.models import File, Geometry, Task
from app.types import Status, TaskType

# Create logger for this module
logger = logging.getLogger(__name__)


def get_geometry_by_id(geometry_id):
    results = Geometry.query.filter_by(id=geometry_id).first()
    return results


def start_geometry_check_task(file_upload_id):
    """
    This function is a wrapper over 3dm mapper. It creates a task and geometry given a file upload id.
    Then calls the map_to_3dm function to map the given geometry file format to a rhino model.

    :param file_upload_id: represents an id related to the uploaded file
    :return: Geometry: returns an object of Geometry model corresponding to the uploaded file
    """
    try:
        task = Task(taskType=TaskType.GeometryCheck, status=Status.Created)
        db.session.add(task)
        db.session.commit()
        geometry = Geometry(inputModelUploadId=file_upload_id, taskId=task.id)

        db.session.add(geometry)
        db.session.commit()

        result = map_to_3dm_and_geo(geometry.id)
        if not result:
            task.status = Status.Error
            task.message = "An error is encountered during the geometry processing!"
            db.session.commit()
            abort(500, task.message)

        task.status = Status.Completed

        db.session.commit()

    except Exception as ex:
        db.session.rollback()
        task.status = Status.Error
        task.message = "An error is encountered during the geometry processing!"
        db.session.commit()
        logger.error(f"{task.message}: {ex}")
        abort(400, message=f"Can not start the geometry task! Error: {ex}")

    return geometry


def get_geometry_result(task_id):
    return Geometry.query.filter_by(taskId=task_id).first()


def map_to_3dm_and_geo(geometry_id):
    geometry = Geometry.query.filter_by(id=geometry_id).first()
    file = File.query.filter_by(id=geometry.inputModelUploadId).first()
    task = Task.query.filter_by(id=geometry.taskId).first()

    directory = config.DefaultConfig.UPLOAD_FOLDER
    file_name, file_extension = os.path.splitext(os.path.basename(file.fileName))

    obj_path = os.path.join(directory, file.fileName)
    rhino3dm_path = os.path.join(directory, f"{file_name}.3dm")
    zip_file_path = os.path.join(directory, f"{file_name}.zip")
    geo_path = os.path.join(directory, f"{file_name}.geo")

    try:
        task.status = Status.InProgress
        db.session.commit()
    except Exception as ex:
        db.session.rollback()
        logger.error(f"Can not update task status! Error: {ex}")

    # Use the new process method to handle both cleaning and conversion
    conversion_factory = GeometryConversionFactory()

    conversion_strategy = conversion_factory.create_strategy(file_extension)

    if not conversion_strategy.generate_3dm(obj_path, rhino3dm_path):
        return False

    if not os.path.exists(rhino3dm_path):
        logger.error("Can not find created a rhino file")
        return False

    try:
        file3dm = File(fileName=f"{file_name}.3dm")
        db.session.add(file3dm)
        db.session.commit()

        geometry.outputModelId = file3dm.id

        # Create a zip file from 3dm
        with zipfile.ZipFile(zip_file_path, "w") as zipf:
            zipf.write(rhino3dm_path, arcname=f"{file_name}.3dm")

        db.session.commit()
    except Exception as ex:
        db.session.rollback()
        logger.error(f"Can not create a rhino file: {ex}")
        return False

    if config.FeatureToggle.is_enabled("enable_geo_conversion"):
        try:
            if not obj_to_gmsh_geo_precise(obj_path, geo_path, rhino3dm_path):
                logger.error("Can not generate a geo file")
                return False

            file_geo = File(fileName=f"{file_name}.geo")
            db.session.add(file_geo)
            db.session.commit()

        except Exception as ex:
            db.session.rollback()
            logger.error(f"Can not attach a geo file: {ex}")
            return False

    return True


def convert_3dm_to_geo(
    rhino_file_path, geo_file_path, volume_name="RoomVolume", map_materials=True
):  # noqa: C901
    """
    Converts a Rhino 3DM file to a Gmsh GEO file with proper material mapping.

    Args:
        rhino_file_path: Path to the Rhino 3dm file
        geo_file_path: Path to output the geo file
        volume_name: Name for the Physical Volume (default: "RoomVolume")
        map_materials: Whether to map materials from the 3dm file (default: True)

    Returns:
        bool: True if successful, False otherwise
    """
    """
    Converts a Rhino 3DM file to a Gmsh GEO file with proper material mapping.

    Args:
        rhino_file_path: Path to the Rhino 3dm file
        geo_file_path: Path to output the geo file
        volume_name: Name for the Physical Volume (default: "RoomVolume")
        map_materials: Whether to map materials from the 3dm file (default: True)

    Returns:
        bool: True if successful, False otherwise
    """
    model = rhino3dm.File3dm.Read(rhino_file_path)

    # Structures to hold .geo elements
    points = {}
    edges = set()  # Just collect unique edges first
    line_loops = {}
    plane_surfaces = {}
    physical_surfaces = {}

    # Helper tracking
    coord_to_point_index = {}
    face_to_edges = {}  # Maps face index to its edges

    # Material mapping for later use if map_materials is True
    material_name_to_ids = {}
    if map_materials:
        material_to_id = {}
        for obj in model.Objects:
            if isinstance(obj.Geometry, rhino3dm.Mesh):
                material_name = obj.Geometry.GetUserString("material_name")
                if material_name:
                    material_to_id[f"{obj.Attributes.Id}"] = material_name

        # Reverse the mapping to be from material name to list of IDs
        for id, material_name in material_to_id.items():
            if material_name not in material_name_to_ids:
                material_name_to_ids[material_name] = []
            material_name_to_ids[material_name].append(id)

    point_index = 1
    surface_index = 1

    # Maps to store material/layer assignments
    object_to_material = {}
    material_to_surfaces = {}
    obj_id_to_surfaces = {}  # Track surfaces by object ID for material mapping

    # First pass: Identify materials/layers
    for obj in model.Objects:
        if not isinstance(obj.Geometry, rhino3dm.Mesh):
            continue

        # Material assignment logic - try to use these strategies in order:
        # 1. Material index (if available)
        # 2. Layer index (if available)
        # 3. Default to M_1
        if obj.Attributes.MaterialIndex > 0:
            material_id = f"M_{obj.Attributes.MaterialIndex}"
        elif obj.Attributes.LayerIndex > 0:
            material_id = f"M_{obj.Attributes.LayerIndex}"
        else:
            material_id = "M_1"

        object_to_material[obj.Attributes.Id] = material_id

        if material_id not in material_to_surfaces:
            material_to_surfaces[material_id] = []

        # Initialize tracking for this object's surfaces
        obj_id_to_surfaces[obj.Attributes.Id] = []

    # Second pass: Process geometry
    for obj in model.Objects:
        if not isinstance(obj.Geometry, rhino3dm.Mesh):
            continue

        mesh = obj.Geometry
        mesh.Faces.ConvertTrianglesToQuads(0.5, 0)
        mesh.Vertices.CombineIdentical(True, True)
        vertices = mesh.Vertices
        faces = mesh.Faces

        vertex_map = {}  # Maps mesh vertex index to Gmsh point index

        for i, vertex in enumerate(vertices):

            def format_coord(value):
                return f"{round(value, 6):.6f}"

            rounded_x = format_coord(vertex.X)
            rounded_y = format_coord(vertex.Y)
            rounded_z = format_coord(vertex.Z)

            coord = (rounded_x, rounded_y, rounded_z)
            if coord not in coord_to_point_index:
                points[point_index] = (
                    f"Point({point_index}) = {{ {rounded_x}, {rounded_y}, {rounded_z}, 1.0 }};\n"
                )
                coord_to_point_index[coord] = point_index
                point_index += 1
            vertex_map[i] = coord_to_point_index[coord]

        # Collect surfaces and edges per object
        object_surface_indices = []

        for i in range(faces.Count):
            face = faces[i]

            # Get face indices based on face type (triangle or quad)
            face_indices = (
                [face[0], face[1], face[2], face[3]]
                if len(face) == 4
                else [face[0], face[1], face[2]] if len(face) == 3 else None
            )
            if not face_indices:
                continue  # Skip non-triangle/quad faces

            # Collect the edges for this face
            face_edges = []
            face_vertices = []

            # First collect all vertices in order
            for j in range(len(face_indices)):
                vertex_idx = vertex_map[face_indices[j]]
                face_vertices.append(vertex_idx)

            # Then create edges from consecutive vertices
            for j in range(len(face_vertices)):
                a = face_vertices[j]
                b = face_vertices[(j + 1) % len(face_vertices)]

                # Prevent self-referential edges
                if a == b:
                    continue

                # Store the edge with direction for line loops
                face_edges.append((a, b))

                # Also store unique edges for line creation
                edge = tuple(sorted([a, b]))
                edges.add(edge)

            # Store the face edges for later line loop creation
            face_to_edges[surface_index] = face_edges

            # Add to material surface list
            material_id = object_to_material[obj.Attributes.Id]
            material_to_surfaces[material_id].append(surface_index)

            # Also track by object ID for material mapping
            obj_id_to_surfaces[obj.Attributes.Id].append(surface_index)

            object_surface_indices.append(surface_index)
            surface_index += 1

    # Create lines in a predictable order after collecting all edges
    lines = {}
    edge_to_line_index = {}
    physical_lines = []

    line_index = 1
    for edge in sorted(edges):  # Sort edges for consistent ordering
        a, b = edge
        # Skip self-referential lines
        if a == b:
            continue
        lines[line_index] = f"Line({line_index}) = {{ {a}, {b} }};\n"
        edge_to_line_index[edge] = line_index
        physical_lines.append(line_index)
        line_index += 1

    # Now create line loops using the line indices
    for face_idx, face_edges in face_to_edges.items():
        # Skip faces with no edges or less than 3 edges
        if not face_edges or len(face_edges) < 3:
            continue

        # Extract ordered vertices from face edges
        edge_vertices = []
        for a, b in face_edges:
            if not edge_vertices:
                edge_vertices.extend([a, b])
            else:
                # Ensure the next edge continues from the last vertex
                if edge_vertices[-1] == a:
                    edge_vertices.append(b)
                elif edge_vertices[-1] == b:
                    edge_vertices.append(a)
                else:
                    # If not connected, try to insert at the beginning
                    if edge_vertices[0] == a:
                        edge_vertices.insert(0, b)
                    elif edge_vertices[0] == b:
                        edge_vertices.insert(0, a)
                    else:
                        print(
                            f"Warning: Disconnected edge ({a},{b}) in face {face_idx}"
                        )

        # Ensure the loop is closed
        if len(edge_vertices) > 1 and edge_vertices[0] != edge_vertices[-1]:
            face_edges.append((edge_vertices[-1], edge_vertices[0]))

        # Create line loop with correct line directions
        line_loop_indices = []
        for i in range(len(edge_vertices) - 1):
            a = edge_vertices[i]
            b = edge_vertices[i + 1]

            # Skip self-referential edges
            if a == b:
                continue

            sorted_edge = tuple(sorted([a, b]))
            if sorted_edge not in edge_to_line_index:
                continue

            line_idx = edge_to_line_index[sorted_edge]

            # Check if direction matches
            if (a, b) != sorted_edge:
                line_idx = -line_idx  # Negative for reverse direction

            line_loop_indices.append(line_idx)

        # Skip if we don't have enough lines to form a loop
        if len(line_loop_indices) < 3:
            continue

        # Format line loop with correct spacing to match example
        line_loops[face_idx] = (
            f"Line Loop({face_idx}) = {{ {', '.join(map(str, line_loop_indices))} }};\n"
        )
        plane_surfaces[face_idx] = f"Plane Surface({face_idx}) = {{ {face_idx} }};\n"

    # Create physical surfaces groups
    if map_materials and material_name_to_ids:
        # If mapping materials, create physical surfaces based on material names
        for obj_id, surfaces in obj_id_to_surfaces.items():
            if surfaces:
                physical_surfaces[obj_id] = (
                    f"Physical Surface(\"{obj_id}\") = {{ {', '.join(map(str, surfaces))} }};\n"
                )
    else:
        # Otherwise use the material/layer based groups
        for material_id, surface_list in material_to_surfaces.items():
            if surface_list:
                physical_surfaces[material_id] = (
                    f"Physical Surface(\"{material_id}\") = {{ {', '.join(map(str, surface_list))} }};\n"
                )

    # Write to .geo file
    with open(geo_file_path, "w") as geo_file:
        # Write points first
        for idx in sorted(points):
            geo_file.write(points[idx])
        geo_file.write("\n")

        # Write lines
        for idx in sorted(lines):
            geo_file.write(lines[idx])
        geo_file.write("\n")

        # Write line loops
        for idx in sorted(line_loops):
            geo_file.write(line_loops[idx])
        geo_file.write("\n")

        # Write plane surfaces
        for idx in sorted(plane_surfaces):
            geo_file.write(plane_surfaces[idx])
        geo_file.write("\n")

        # Write Surface Loop and Volume with custom volume name
        surface_ids = sorted(plane_surfaces.keys())
        geo_file.write(f"Surface Loop(1) = {{ {', '.join(map(str, surface_ids))} }};\n")

        # Write Physical Surface definitions
        for ps in physical_surfaces.values():
            geo_file.write(ps)

        geo_file.write("Volume( 1 ) = { 1 };\n")
        geo_file.write(f'Physical Volume("{volume_name}") = {{ 1 }};\n')

        # Add Physical Line group
        geo_file.write(
            f'Physical Line ("default") = {{{", ".join(map(str, physical_lines))}}};\n'
        )

        # Write mesh parameters at the end
        geo_file.write("Mesh.Algorithm = 6;\n")
        geo_file.write(
            "Mesh.Algorithm3D = 1; // Delaunay3D, works for boundary layer insertion.\n"
        )
        geo_file.write(
            "Mesh.Optimize = 1; // Gmsh smoother, works with boundary layers (netgen version does not).\n"
        )
        geo_file.write("Mesh.CharacteristicLengthFromPoints = 1;\n")
        geo_file.write('// Recombine Surface "*";\n')
        geo_file.write("Mesh.RemeshAlgorithm = 1; // automatic\n")

    print(f"Converted {rhino_file_path} to {geo_file_path}")
    return os.path.exists(geo_file_path)

def obj_to_gmsh_geo_precise(obj_file, geo_file, rhino3dm_path, volume_name="RoomVolume", tol=1e-8):
    """
    Parse OBJ preserving groups, deduplicate vertices, merge triangle pairs into quads,
    create Lines with consistent orientation and Line Loops with signed line indices,
    and write a Gmsh .geo with Physical Surface groups.
    """

    # Obtain material indices from rhino
    model = rhino3dm.File3dm.Read(rhino3dm_path)

    # Material mapping for later use if map_materials is True
    material_name_to_ids = {}
    material_to_id = {}
    for obj in model.Objects:
        if isinstance(obj.Geometry, rhino3dm.Mesh):
            material_name = obj.Geometry.GetUserString("material_name")
            if material_name:
                material_to_id[f"{obj.Attributes.Id}"] = material_name

    # Reverse the mapping to be from material name to list of IDs
    for id, material_name in material_to_id.items():
        if material_name not in material_name_to_ids:
            material_name_to_ids[material_name] = []
        material_name_to_ids[material_name].append(id)

    # --- Parse OBJ ---
    vertices = []          # original vertex coordinates (1-based in OBJ)
    faces = []             # list of faces: list of vertex indices (1-based)
    face_groups = []       # group name for each face
    current_group = "default"

    with open(obj_file, "r") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if line.startswith('v '):
                parts = line.split()
                x, y, z = map(float, parts[1:4])
                # Convert from SketchUp (Y-up, left-handed) to Gmsh (right-handed)
                # Flip the Z axis to correct mirroring
                coords = (x, -z, y)
                #coords = (float(parts[1]), float(parts[2]), float(parts[3]))
                vertices.append(coords)
            elif line.startswith('g '):
                parts = line.split()[1:]  # skip 'g'
                # If first token starts with 'Mesh', skip it
                parts = [p for p in parts if not p.startswith("Mesh") and not p.startswith("Model")]
                current_group = parts[0] if parts else "default"
            elif line.startswith('f '):
                parts = line.split()[1:]
                # face vertex indices (OBJ format may include v/vt/vn)
                idxs = [int(p.split('/')[0]) for p in parts]
                faces.append(idxs)
                face_groups.append(current_group)

    # --- Deduplicate vertices (preserve order) ---
    unique_vertices = []
    orig_to_unique = {}  # map from original index (1-based) -> unique index (1-based)
    for i, v in enumerate(vertices, start=1):
        # find existing within tolerance
        found = None
        for j, uv in enumerate(unique_vertices, start=1):
            if abs(uv[0] - v[0]) < tol and abs(uv[1] - v[1]) < tol and abs(uv[2] - v[2]) < tol:
                found = j
                break
        if found is None:
            unique_vertices.append(v)
            orig_to_unique[i] = len(unique_vertices)
        else:
            orig_to_unique[i] = found
            
    # remap faces to unique vertex indices
    faces_mapped = [[orig_to_unique[i] for i in face] for face in faces]
    
    # --- Sort vertices deterministically (like Meshkit) --- 
    unique_vertices_sorted = sorted(
        enumerate(unique_vertices, start=1),
        key=lambda kv: (round(kv[1][0], 8), 
                        round(kv[1][1], 8),
                        round(kv[1][2], 8)) 
        ) 
    index_map = {old: new for new, (old, _) in enumerate(unique_vertices_sorted, start=1)} 
    unique_vertices = [v for _, v in unique_vertices_sorted] 
    faces_mapped = [[index_map[i] for i in face] for face in faces_mapped]


    # --- Merge pairs of triangles within same group into quads when possible ---
    nfaces = len(faces_mapped)
    merged_flag = [False] * nfaces
    merged_faces = []      # list of faces (each is 3 or 4 vertex indices, in CCW order)
    merged_groups = []

    # helper: get coords by unique index (1-based)
    def coords(idx):
        return unique_vertices[idx - 1]

    for i in range(nfaces):
        if merged_flag[i]:
            continue
        fi = faces_mapped[i]
        gi = face_groups[i]
        if len(fi) == 3:
            # try to find a partner triangle in same group sharing 2 vertices
            partner = None
            for j in range(i + 1, nfaces):
                if merged_flag[j]:
                    continue
                if face_groups[j] != gi:
                    continue
                fj = faces_mapped[j]
                if len(fj) != 3:
                    continue
                shared = set(fi) & set(fj)
                if len(shared) == 2:
                    partner = j
                    break
            if partner is not None:
                # build quad from union of vertices (4 vertices)
                union = list(dict.fromkeys(fi + faces_mapped[partner]))  # preserve order somewhat
                if len(union) == 4:
                    # order the 4 vertices into a planar loop consistently
                    pts = [coords(idx) for idx in union]
                    # compute plane normal using first triangle
                    v0 = pts[0]
                    v1 = pts[1]
                    v2 = pts[2]
                    nx = (v1[1] - v0[1]) * (v2[2] - v0[2]) - (v1[2] - v0[2]) * (v2[1] - v0[1])
                    ny = (v1[2] - v0[2]) * (v2[0] - v0[0]) - (v1[0] - v0[0]) * (v2[2] - v0[2])
                    nz = (v1[0] - v0[0]) * (v2[1] - v0[1]) - (v1[1] - v0[1]) * (v2[0] - v0[0])
                    an = (abs(nx), abs(ny), abs(nz))
                    # choose projection plane by largest normal component
                    if an[2] >= an[0] and an[2] >= an[1]:
                        # project to XY
                        proj = lambda p: (p[0], p[1])
                    elif an[1] >= an[0] and an[1] >= an[2]:
                        # project to XZ
                        proj = lambda p: (p[0], p[2])
                    else:
                        # project to YZ
                        proj = lambda p: (p[1], p[2])

                    uv = [proj(coords(idx)) for idx in union]
                    cx = sum(pt[0] for pt in uv) / 4.0
                    cy = sum(pt[1] for pt in uv) / 4.0
                    angles = [math.atan2(pt[1] - cy, pt[0] - cx) for pt in uv]
                    # sort union vertices by angle
                    union_ordered = [x for _, x in sorted(zip(angles, union))]
                    merged_faces.append(union_ordered)
                    merged_groups.append(gi)
                    merged_flag[i] = True
                    merged_flag[partner] = True
                    continue
                # if union not 4, fallthrough to keep triangle
            # no partner found => keep triangle
            merged_faces.append(fi)
            merged_groups.append(gi)
            merged_flag[i] = True
        else:
            # non-triangle face: keep as-is (maybe quad)
            merged_faces.append(fi)
            merged_groups.append(gi)
            merged_flag[i] = True

    # There may be faces leftover (if any not processed): ensure all covered
    for k in range(nfaces):
        if not merged_flag[k]:
            merged_faces.append(faces_mapped[k])
            merged_groups.append(face_groups[k])
            
    tag_to_surfaces = {}
    for sid, tag in enumerate(merged_groups, start=1):
        tag_to_surfaces.setdefault(tag, []).append(sid)
 
    # # --- Orientation normalization (ensure CCW) --- 
    # def is_ccw(face): 
    #     pts = [unique_vertices[i - 1] for i in face] 
    #     v1, v2, v3 = pts[:3] 
    #     nx = (v2[1]-v1[1])*(v3[2]-v1[2]) - (v2[2]-v1[2])*(v3[1]-v1[1]) 
    #     ny = (v2[2]-v1[2])*(v3[0]-v1[0]) - (v2[0]-v1[0])*(v3[2]-v1[2]) 
    #     nz = (v2[0]-v1[0])*(v3[1]-v1[1]) - (v2[1]-v1[1])*(v3[0]-v1[0]) 
    #     return nz >= 0 
    
    # for face in merged_faces: 
    #     if not is_ccw(face): 
    #         face.reverse()
    
    room_center = tuple(
        sum(v[i] for v in unique_vertices) / len(unique_vertices)
        for i in range(3)
    )

    
    def is_outward_facing(face):
        pts = [unique_vertices[i - 1] for i in face]
        v1, v2, v3 = pts[:3]
        # Face normal
        nx = (v2[1]-v1[1])*(v3[2]-v1[2]) - (v2[2]-v1[2])*(v3[1]-v1[1])
        ny = (v2[2]-v1[2])*(v3[0]-v1[0]) - (v2[0]-v1[0])*(v3[2]-v1[2])
        nz = (v2[0]-v1[0])*(v3[1]-v1[1]) - (v2[1]-v1[1])*(v3[0]-v1[0])
        normal = (nx, ny, nz)
        # Face centroid
        cx, cy, cz = tuple(sum(p[i] for p in pts) / len(pts) for i in range(3))
        # Vector from centroid to room center
        to_center = (
            room_center[0] - cx,
            room_center[1] - cy,
            room_center[2] - cz
        )
        # Dot product: if negative, normal points outward
        dot = sum(normal[i] * to_center[i] for i in range(3))
        return dot < 0
    
    for face in merged_faces:
        if not is_outward_facing(face):
            face.reverse()



    # --- Build unique edges (lines) with stable orientation ---
    edge_to_line = {}       # key = (min,max) -> line_id
    line_orientation = {}   # line_id -> (a,b) orientation used when created
    next_line_id = 1

    # collect edges from merged faces in consistent order
    face_line_loops = []  # list of lists of signed line indices (to write)
    for face in merged_faces:
        n = len(face)
        loop_line_ids = []
        for idx in range(n):
            a = face[idx]
            b = face[(idx + 1) % n]
            key = (a, b) if a < b else (b, a)
            if key not in edge_to_line:
                edge_to_line[key] = next_line_id
                # store orientation as the first encountered direction (a,b)
                if key == (a, b):
                    line_orientation[next_line_id] = (a, b)
                else:
                    line_orientation[next_line_id] = (b, a)
                next_line_id += 1
            lid = edge_to_line[key]
            # determine sign: +if orientation matches (a,b), - otherwise
            ori = line_orientation[lid]
            if ori == (a, b):
                loop_line_ids.append(lid)
            else:
                loop_line_ids.append(-lid)
        face_line_loops.append(loop_line_ids)

    # --- Now write the GEO file ---
    with open(geo_file, "w") as g:
        # Points
        for i, v in enumerate(unique_vertices, start=1):
            g.write(f"Point({i}) = {{ {v[0]}, {v[1]}, {v[2]}, 1.0 }};\n")
        g.write("\n")

        # Lines (must write using stored orientation endpoints)
        # We need to output unique edge list, using the stored orientation endpoints
        # Build a mapping of line_id -> endpoints
        line_id_to_endpoints = {}
        for key, lid in edge_to_line.items():
            # endpoints should be line_orientation[lid]
            a, b = line_orientation[lid]
            line_id_to_endpoints[lid] = (a, b)

        # Write lines in increasing id order
        for lid in range(1, next_line_id):
            a, b = line_id_to_endpoints[lid]
            g.write(f"Line({lid}) = {{ {a}, {b} }};\n")
        g.write("\n")

        # Line Loops
        for sid, loop in enumerate(face_line_loops, start=1):
            loop_str = ", ".join(str(x) for x in loop)
            g.write(f"Line Loop({sid}) = {{ {loop_str} }};\n")
        g.write("\n")

        # Plane surfaces
        for sid, loop in enumerate(face_line_loops, start=1):
            g.write(f"Plane Surface({sid}) = {{ {sid} }};\n")
        g.write("\n")

        # Surface Loop and Volume
        total_surfaces = len(face_line_loops)
        surf_list = ", ".join(str(i) for i in range(1, total_surfaces + 1))
        g.write(f"Surface Loop(1) = {{ {surf_list} }};\n")

        # Physical Surface groups by OBJ group name
        # unique_groups = []
        # for grp in merged_groups:
        #     if grp not in unique_groups:
        #         unique_groups.append(grp)
        # # for grp in unique_groups:
        # #     surf_ids = [str(i + 1) for i, gname in enumerate(merged_groups) if gname == grp]
        # #     if surf_ids:
        # #         g.write(f'Physical Surface("{grp}") = {{ {", ".join(surf_ids)} }};\n')

        ii = 1
        for grp in material_to_id:
            g.write(f'Physical Surface("{grp}") = {{ { str(ii) } }};\n')
            ii = ii + 1

        g.write("Volume(1) = { 1 };\n")
        g.write(f'Physical Volume("{volume_name}") = {{ 1 }};\n')

        # Physical Line (all lines)
        lines_all = ", ".join(str(i) for i in range(1, next_line_id))
        g.write(f'Physical Line("default") = {{ {lines_all} }};\n')

        g.write('Mesh.Algorithm = 6;\n')
        g.write('Mesh.Algorithm3D = 1; // Delaunay3D, works for boundary layer insertion.\n')
        g.write('Mesh.Optimize = 1; // Gmsh smoother, works with boundary layers (netgen version does not).\n')
        g.write('Mesh.CharacteristicLengthFromPoints = 1;\n')
        g.write('// Recombine Surface "*";\n')

    print(f"Wrote {geo_file}: {len(unique_vertices)} points, {next_line_id-1} lines, {len(face_line_loops)} surfaces.")
    return True