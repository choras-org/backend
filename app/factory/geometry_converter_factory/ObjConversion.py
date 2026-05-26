import logging
import os

import numpy as np
import rhino3dm
import trimesh

from app.factory.geometry_converter_factory.GeometryConversionStrategy import (
    GeometryConversionStrategy,
)


class ObjConversion(GeometryConversionStrategy):
    # Create logger for this module
    logger = logging.getLogger(__name__)

    def generate_3dm(self, obj_file_path, rhino_path):
        """
        This method combines cleaning and converting an OBJ file to 3DM format.
        It first cleans the OBJ file and then converts it to the 3DM format.

        :param obj_file_path: Path to the original OBJ file
        :param rhino_path: Path to save the converted 3DM file
        :return: Path to the converted 3DM file if successful, otherwise None
        """
        # Extract the directory path and file name
        dir_path, file_name = os.path.split(obj_file_path)

        # Generate the cleaned file path by appending '_clean' before the extension
        base_name, ext = os.path.splitext(file_name)
        obj_clean_path = os.path.join(dir_path, f"{base_name}_clean{ext}")

        try:
            # Clean the OBJ file
            self._clean_obj_file(obj_file_path, obj_clean_path)

            # Convert the cleaned OBJ file to 3DM
            return self._convert_obj_to_3dm(obj_clean_path, rhino_path)

        except Exception as ex:
            self.logger.error(f"Error processing OBJ to 3DM: {ex}")
            return None

    def _clean_obj_file(self, obj_file_path, obj_clean_path):
        with open(obj_file_path, "r") as infile, open(obj_clean_path, "w") as outfile:
            lines = infile.readlines()
            current_material = None
            custom_material_counter = 1

            for line in lines:
                if line.startswith("usemtl"):
                    current_material = line.strip()
                elif line.startswith("f"):
                    if current_material:
                        outfile.write(current_material + "\n")
                    else:
                        custom_material = f"usemtl M_{custom_material_counter}\n"
                        outfile.write(custom_material)
                        current_material = custom_material.strip()
                        custom_material_counter += 1
                    outfile.write(line)
                else:
                    outfile.write(line)

    def _convert_obj_to_3dm(self, obj_clean_path, rhino_path):
        # Load the OBJ file using trimesh
        scene = trimesh.load(
            obj_clean_path,
            group_material=False,
            skip_materials=False,
            maintain_order=True,
            Process=False,
        )

        # Create a new 3dm file
        model = rhino3dm.File3dm()

        # Parse OBJ materials
        material_map = _parse_obj_materials(obj_clean_path)

        # Check if the loaded object is a scene with multiple geometries
        if isinstance(scene, trimesh.Scene):
            meshes = scene.dump(False)
            meshes.reverse()
        else:
            meshes = [scene]

        # Define a 90-degree rotation matrix around the X-axis
        rotation_matrix = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]])

        for mesh_index, mesh in enumerate(meshes):
            vertices = mesh.vertices
            faces = mesh.faces

            rhino_mesh = rhino3dm.Mesh()

            for vertex in vertices:
                rotated_vertex = np.dot(rotation_matrix, vertex)
                rhino_mesh.Vertices.Add(
                    rotated_vertex[0], rotated_vertex[1], rotated_vertex[2]
                )

            for face_index, face in enumerate(faces):
                if len(face) == 3:  # Triangular face
                    rhino_mesh.Faces.AddFace(face[0], face[1], face[2])
                elif len(face) == 4:  # Quad face
                    rhino_mesh.Faces.AddFace(face[0], face[1], face[2], face[3])

            rhino_mesh.SetUserString("material_name", str(material_map[mesh_index]))
            model.Objects.AddMesh(rhino_mesh)

        # Save the 3dm file
        model.Write(rhino_path)
        return rhino_path


def _parse_obj_materials(obj_path):
    material_map = {}
    face_index = 0

    with open(obj_path, "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith("usemtl"):
                material_map[face_index] = line.split()[1]
                face_index += 1
    return material_map
