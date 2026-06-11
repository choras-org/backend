import logging
import os

import numpy as np
import rhino3dm
from shapely.geometry import Polygon
from shapely import constrained_delaunay_triangles

from app.factory.geometry_converter_factory.GeometryConversionStrategy import (
    GeometryConversionStrategy,
)


class ObjConversion(GeometryConversionStrategy):
    logger = logging.getLogger(__name__)

    def generate_3dm(self, obj_file_path, rhino_path):
        dir_path, file_name = os.path.split(obj_file_path)
        base_name, ext = os.path.splitext(file_name)
        obj_clean_path = os.path.join(dir_path, f"{base_name}_clean{ext}")

        try:
            self._clean_obj_file(obj_file_path, obj_clean_path)
            return self._convert_obj_to_3dm_with_cdt(obj_clean_path, rhino_path)
        except Exception as ex:
            self.logger.error(f"Error processing OBJ to 3DM: {ex}", exc_info=True)
            return None

    def _clean_obj_file(self, obj_file_path, obj_clean_path):
        with open(obj_file_path, "r") as infile, open(obj_clean_path, "w") as outfile:
            current_material = None
            custom_material_counter = 1

            for line in infile:
                if line.startswith("usemtl"):
                    current_material = line.strip()
                    outfile.write(line)

                elif line.startswith("f "):
                    if current_material:
                        outfile.write(current_material + "\n")
                    else:
                        current_material = f"usemtl M_{custom_material_counter}"
                        outfile.write(current_material + "\n")
                        custom_material_counter += 1

                    outfile.write(line)

                else:
                    outfile.write(line)

    def _convert_obj_to_3dm_with_cdt(self, obj_clean_path, rhino_path):
        vertices, faces = self._parse_obj(obj_clean_path)

        model = rhino3dm.File3dm()
        rotation_matrix = np.array([
            [1, 0, 0],
            [0, 0, -1],
            [0, 1, 0],
        ])

        for face_index, face_data in enumerate(faces):
            face_indices = face_data["indices"]
            material_name = face_data["material"]

            polygon_vertices_3d = [vertices[i] for i in face_indices]

            triangles = self._triangulate_face_cdt(
                polygon_vertices_3d,
                face_indices,
            )

            rhino_mesh = rhino3dm.Mesh()

            local_vertex_map = {}

            def add_vertex(global_index):
                if global_index in local_vertex_map:
                    return local_vertex_map[global_index]

                rotated = np.dot(rotation_matrix, vertices[global_index])

                local_index = len(rhino_mesh.Vertices)
                rhino_mesh.Vertices.Add(
                    float(rotated[0]),
                    float(rotated[1]),
                    float(rotated[2]),
                )

                local_vertex_map[global_index] = local_index
                return local_index

            for tri in triangles:
                a = add_vertex(tri[0])
                b = add_vertex(tri[1])
                c = add_vertex(tri[2])

                if len({a, b, c}) == 3:
                    rhino_mesh.Faces.AddFace(a, b, c)

            rhino_mesh.SetUserString("material_name", material_name or "")
            rhino_mesh.SetUserString("source_face_index", str(face_index))

            model.Objects.AddMesh(rhino_mesh)

        model.Write(rhino_path)
        return rhino_path

    def _parse_obj(self, obj_path):
        vertices = []
        faces = []
        current_material = None

        with open(obj_path, "r") as f:
            for line in f:
                line = line.strip()

                if not line or line.startswith("#"):
                    continue

                if line.startswith("v "):
                    parts = line.split()
                    vertices.append(np.array([
                        float(parts[1]),
                        float(parts[2]),
                        float(parts[3]),
                    ]))

                elif line.startswith("usemtl "):
                    current_material = line.split(maxsplit=1)[1]

                elif line.startswith("f "):
                    parts = line.split()[1:]
                    indices = []

                    for part in parts:
                        # Supports:
                        # f v
                        # f v/vt
                        # f v//vn
                        # f v/vt/vn
                        vertex_index = int(part.split("/")[0])

                        if vertex_index < 0:
                            vertex_index = len(vertices) + vertex_index
                        else:
                            vertex_index -= 1

                        indices.append(vertex_index)

                    faces.append({
                        "indices": indices,
                        "material": current_material,
                    })

        return vertices, faces

    def _triangulate_face_cdt(self, polygon_vertices_3d, original_indices):
        if len(original_indices) == 3:
            return [original_indices]

        if len(original_indices) == 4:
            return [
                [original_indices[0], original_indices[1], original_indices[2]],
                [original_indices[0], original_indices[2], original_indices[3]],
            ]

        points_3d = np.array(polygon_vertices_3d)

        origin, basis_u, basis_v = self._best_fit_plane_basis(points_3d)

        points_2d = []
        coord_to_global_index = {}

        for global_index, point_3d in zip(original_indices, points_3d):
            relative = point_3d - origin
            x = float(np.dot(relative, basis_u))
            y = float(np.dot(relative, basis_v))

            key = self._coord_key(x, y)
            points_2d.append((x, y))
            coord_to_global_index[key] = global_index

        polygon = Polygon(points_2d)

        if not polygon.is_valid:
            polygon = polygon.buffer(0)

        if polygon.is_empty:
            self.logger.warning("CDT failed because polygon is empty. Falling back to fan triangulation.")
            return self._fan_triangulate(original_indices)

        result = constrained_delaunay_triangles(polygon)

        triangles = []

        for geom in result.geoms:
            coords = list(geom.exterior.coords)[:-1]

            if len(coords) != 3:
                continue

            tri = []

            for x, y in coords:
                key = self._coord_key(x, y)

                if key not in coord_to_global_index:
                    nearest_index = self._nearest_original_vertex(
                        x,
                        y,
                        points_2d,
                        original_indices,
                    )
                    tri.append(nearest_index)
                else:
                    tri.append(coord_to_global_index[key])

            if len(set(tri)) == 3:
                triangles.append(tri)

        if not triangles:
            self.logger.warning("CDT produced no triangles. Falling back to fan triangulation.")
            return self._fan_triangulate(original_indices)

        return triangles

    def _best_fit_plane_basis(self, points_3d):
        origin = points_3d.mean(axis=0)
        centered = points_3d - origin

        _, _, vh = np.linalg.svd(centered)

        basis_u = vh[0]
        basis_v = vh[1]

        return origin, basis_u, basis_v

    def _coord_key(self, x, y, precision=9):
        return (round(float(x), precision), round(float(y), precision))

    def _nearest_original_vertex(self, x, y, points_2d, original_indices):
        target = np.array([x, y])
        points = np.array(points_2d)

        distances = np.linalg.norm(points - target, axis=1)
        nearest_local_index = int(np.argmin(distances))

        return original_indices[nearest_local_index]

    def _fan_triangulate(self, indices):
        triangles = []

        for i in range(1, len(indices) - 1):
            triangles.append([
                indices[0],
                indices[i],
                indices[i + 1],
            ])

        return triangles