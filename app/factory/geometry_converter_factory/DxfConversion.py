import logging
import os

import ezdxf
import numpy as np
import rhino3dm

from app.factory.geometry_converter_factory.GeometryConversionStrategy import GeometryConversionStrategy


class DxfConversion(GeometryConversionStrategy):
    # Create logger for this module
    logger = logging.getLogger(__name__)

    def generate_3dm(self, dxf_file_path, rhino_path):
        """
        This method converts a DXF file to 3DM format.
        The original DXF file is preserved.

        :param dxf_file_path: Path to the original DXF file
        :param rhino_path: Path to save the converted 3DM file
        :return: Path to the converted 3DM file if successful, otherwise None
        """
        # Validate input file exists
        if not os.path.exists(dxf_file_path):
            self.logger.error(f"DXF file not found: {dxf_file_path}")
            return None

        # Ensure output directory exists
        output_dir = os.path.dirname(rhino_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        try:
            # Analyze the reference 3DM file structure if provided
            reference_structure = self._analyze_reference_structure()

            # Pass the reference structure to guide the conversion process
            return self._convert_dxf_to_3dm(dxf_file_path, rhino_path, reference_structure)
        except Exception as ex:
            self.logger.error(f"Error processing DXF to 3DM: {ex}")
            return None

    def _analyze_reference_structure(self):
        """
        Analyze a reference 3DM file to guide the conversion process.

        :return: Dictionary with reference structure information
        """
        # This method can be expanded to analyze any reference 3DM files
        # For now, we'll return a static structure based on our analysis
        return {
            "units": "meters",
            "coordinate_format": "fixed_point_2_decimal",
            "mesh_count": 6,
            "materials": ["M_3", "M_18", "M_2"],
            "coordinate_ranges": {
                "x": [33.3, 33.3 * 1.1],  # Example range based on reference file
                "y": [33.3, 33.3 * 1.1],
                "z": [33.3, 33.3 * 1.1],
            },
        }

    def _convert_dxf_to_3dm(self, dxf_file_path, rhino_path, reference_structure=None):
        """
        Converts a DXF file to 3DM format.

        :param dxf_file_path: Path to the DXF file
        :param rhino_path: Path to save the converted 3DM file
        :param reference_structure: Optional structure information to guide conversion
        :return: Path to the 3DM file
        """
        # Create a new 3dm file
        model = rhino3dm.File3dm()
        dxf = None

        try:
            # Load the DXF file with careful error handling
            try:
                dxf = ezdxf.readfile(dxf_file_path)
            except IOError as e:
                self.logger.error(f"Cannot open DXF file: {e}")
                raise ValueError(f"Cannot open DXF file: {e}")
            except ezdxf.DXFStructureError as e:
                self.logger.error(f"Invalid or corrupted DXF file: {e}")
                raise ValueError(f"Invalid or corrupted DXF file: {e}")

            # Set document properties from DXF if available
            if hasattr(dxf, "header"):
                # Try to set some basic document properties
                try:
                    if "$FINGNAME" in dxf.header:
                        model.Notes = f"Converted from: {dxf.header['$FINGNAME']}"

                    # Add any other relevant metadata
                except Exception as e:
                    self.logger.warning(f"Error setting document properties: {e}")

            # Define a 90-degree rotation matrix around the X-axis (similar to OBJ conversion)
            rotation_matrix = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]])

            # First pass: Process blocks and store them for later reference
            self.logger.info("Processing block definitions")
            block_entities = {}

            if hasattr(dxf, "blocks"):
                for block in dxf.blocks:
                    # Skip special blocks like *Model_Space
                    if block.name.startswith("*"):
                        continue

                    # Store entities for this block
                    block_entities[block.name] = list(block)
                    self.logger.info(f"Stored block '{block.name}' with {len(block_entities[block.name])} entities")

            # Get the modelspace
            msp = dxf.modelspace()

            # Keep track of stats for reporting
            entity_counts = {}

            # Process DXF entities in batches to improve memory efficiency
            batch_size = 1000  # Adjust based on your typical file size
            entity_batch = []

            # For very large files, this prevents loading everything into memory at once
            for entity in msp:
                entity_type = entity.dxftype()
                entity_counts[entity_type] = entity_counts.get(entity_type, 0) + 1

                entity_batch.append(entity)

                # Process in batches
                if len(entity_batch) >= batch_size:
                    self._process_entity_batch(entity_batch, model, rotation_matrix, block_entities)
                    entity_batch = []  # Clear batch after processing

            # Process any remaining entities
            if entity_batch:
                self._process_entity_batch(entity_batch, model, rotation_matrix, block_entities)

            # Log processing statistics
            self.logger.info(f"Processed DXF entities: {entity_counts}")

            # Save the 3dm file
            model.Write(rhino_path)
            return rhino_path

        finally:
            # Clean up resources
            if dxf is not None:
                dxf = None  # Help garbage collection

    def _process_entity_batch(self, entities, model, rotation_matrix, block_entities=None):
        """
        Process a batch of DXF entities to improve memory efficiency.

        :param entities: List of DXF entities
        :param model: 3DM model
        :param rotation_matrix: Rotation matrix
        :param block_entities: Dictionary of block entities for INSERT handling
        """
        if block_entities is None:
            block_entities = {}

        for entity in entities:
            try:
                entity_type = entity.dxftype()

                # Handle different entity types
                if entity_type == "LINE":
                    self._add_line_to_model(entity, model, rotation_matrix)
                elif entity_type == "CIRCLE":
                    self._add_circle_to_model(entity, model, rotation_matrix)
                elif entity_type == "ARC":
                    self._add_arc_to_model(entity, model, rotation_matrix)
                elif entity_type in ("POLYLINE", "LWPOLYLINE"):
                    self._add_polyline_to_model(entity, model, rotation_matrix)
                elif entity_type == "3DFACE":
                    self._add_3dface_to_model(entity, model, rotation_matrix)
                elif entity_type == "MESH":
                    self._add_mesh_to_model(entity, model, rotation_matrix)
                elif entity_type == "POINT":
                    # Add point handling
                    point = self._rotate_point(entity.dxf.location, rotation_matrix)
                    model.Objects.AddPoint(rhino3dm.Point3d(point[0], point[1], point[2]))
                elif entity_type == "ELLIPSE":
                    # Basic ellipse support
                    self._handle_ellipse(entity, model, rotation_matrix)
                elif entity_type == "SPLINE":
                    # Basic spline support
                    self._handle_spline(entity, model, rotation_matrix)
                elif entity_type == "INSERT":
                    # Handle block insertions
                    self._add_insert_to_model(entity, model, rotation_matrix, block_entities)
                # Additional entity types can be added as needed

            except Exception as e:
                # Log error but continue processing other entities
                self.logger.warning(f"Error processing {entity.dxftype()} entity: {e}")

    def _add_insert_to_model(self, entity, model, rotation_matrix, block_entities):
        """
        Handle INSERT entity by instantiating the referenced block.

        :param entity: DXF INSERT entity
        :param model: 3DM model
        :param rotation_matrix: Rotation matrix
        :param block_entities: Dictionary of block entities
        """
        try:
            # Get block name
            block_name = entity.dxf.name

            # Check if we have this block
            if block_name not in block_entities:
                self.logger.warning(f"Block '{block_name}' referenced by INSERT not found")
                return

            # Get transformation parameters
            position = self._rotate_point(entity.dxf.insert, rotation_matrix)

            # Get scaling factors (default to 1 if not present)
            scale_x = getattr(entity.dxf, "xscale", 1.0)
            scale_y = getattr(entity.dxf, "yscale", 1.0)
            scale_z = getattr(entity.dxf, "zscale", 1.0)

            # Get rotation angle (default to 0 if not present)
            rotation_z = getattr(entity.dxf, "rotation", 0.0)

            # Get entities from the block
            block_entity_list = block_entities[block_name]

            # Process each entity in the block
            for block_entity in block_entity_list:
                try:
                    # Skip non-graphical entities
                    if not hasattr(block_entity, "dxftype"):
                        continue

                    # Create a copy of the entity with transformation applied
                    entity_type = block_entity.dxftype()

                    # Apply transformations based on entity type
                    if entity_type == "3DFACE":
                        self._add_transformed_3dface(
                            block_entity,
                            model,
                            rotation_matrix,
                            position,
                            (scale_x, scale_y, scale_z),
                            rotation_z,
                        )
                    elif entity_type == "LINE":
                        self._add_transformed_line(
                            block_entity,
                            model,
                            rotation_matrix,
                            position,
                            (scale_x, scale_y, scale_z),
                            rotation_z,
                        )
                    # Add more entity types as needed

                except Exception as e:
                    self.logger.warning(f"Error processing block entity {block_entity.dxftype()}: {e}")

        except Exception as e:
            self.logger.warning(f"Error processing INSERT entity: {e}")

    def _add_transformed_3dface(self, entity, model, rotation_matrix, position, scale, rotation_z):
        """
        Add a transformed 3DFACE entity from a block to the model.

        :param entity: DXF 3DFACE entity from a block
        :param model: 3DM model
        :param rotation_matrix: Global rotation matrix
        :param position: Position of the INSERT
        :param scale: Scale factors (x, y, z)
        :param rotation_z: Rotation angle around Z axis in degrees
        """
        # Create a mesh to represent the 3DFACE
        mesh = rhino3dm.Mesh()

        # Get the four vertices of the 3DFACE
        p1 = self._transform_point(entity.dxf.vtx0, rotation_matrix, position, scale, rotation_z)
        p2 = self._transform_point(entity.dxf.vtx1, rotation_matrix, position, scale, rotation_z)
        p3 = self._transform_point(entity.dxf.vtx2, rotation_matrix, position, scale, rotation_z)
        p4 = self._transform_point(entity.dxf.vtx3, rotation_matrix, position, scale, rotation_z)

        # Add vertices to the mesh
        mesh.Vertices.Add(p1[0], p1[1], p1[2])
        mesh.Vertices.Add(p2[0], p2[1], p2[2])
        mesh.Vertices.Add(p3[0], p3[1], p3[2])

        # Check if this is a triangular or quadrilateral face
        if not np.array_equal(entity.dxf.vtx2, entity.dxf.vtx3):
            mesh.Vertices.Add(p4[0], p4[1], p4[2])
            mesh.Faces.AddFace(0, 1, 2, 3)
        else:
            mesh.Faces.AddFace(0, 1, 2)

        # Get material info if available
        material_name = self._get_entity_material(entity)
        if material_name:
            mesh.SetUserString("material_name", material_name)

        model.Objects.AddMesh(mesh)

    def _get_entity_material(self, entity):
        """
        Get material name from entity if available.

        :param entity: DXF entity
        :return: Material name or None
        """
        # Check common attributes where material information might be stored
        if hasattr(entity, "dxf") and hasattr(entity.dxf, "layer"):
            return entity.dxf.layer
        return None

    def _add_transformed_line(self, entity, model, rotation_matrix, position, scale, rotation_z):
        """
        Add a transformed LINE entity from a block to the model.

        :param entity: DXF LINE entity from a block
        :param model: 3DM model
        :param rotation_matrix: Global rotation matrix
        :param position: Position of the INSERT
        :param scale: Scale factors (x, y, z)
        :param rotation_z: Rotation angle around Z axis in degrees
        """
        # Get the start and end points of the line
        start_point = self._transform_point(entity.dxf.start, rotation_matrix, position, scale, rotation_z)
        end_point = self._transform_point(entity.dxf.end, rotation_matrix, position, scale, rotation_z)

        # Create a line object
        line = rhino3dm.Line(
            rhino3dm.Point3d(start_point[0], start_point[1], start_point[2]),
            rhino3dm.Point3d(end_point[0], end_point[1], end_point[2]),
        )

        model.Objects.AddLine(line)

    def _transform_point(self, point, rotation_matrix, position, scale, rotation_z):
        """
        Apply a full transformation to a point including:
        - Scaling
        - Z-axis rotation
        - Translation
        - Global rotation matrix

        :param point: Original point
        :param rotation_matrix: Global rotation matrix
        :param position: Translation offset
        :param scale: Scale factors (x, y, z)
        :param rotation_z: Rotation angle around Z axis in degrees
        :return: Transformed point as numpy array
        """
        # Convert point to proper format
        point_array = self._point_to_array(point)

        # Apply scaling
        scaled_point = np.array(
            [
                point_array[0] * scale[0],
                point_array[1] * scale[1],
                point_array[2] * scale[2],
            ]
        )

        # Apply Z rotation if needed
        if rotation_z != 0:
            rad_angle = np.radians(rotation_z)
            cos_angle = np.cos(rad_angle)
            sin_angle = np.sin(rad_angle)

            # Create rotation matrix for Z axis
            z_rotation = np.array([[cos_angle, -sin_angle, 0], [sin_angle, cos_angle, 0], [0, 0, 1]])

            scaled_point = np.dot(z_rotation, scaled_point)

        # Apply translation (adding the INSERT position)
        translated_point = scaled_point + np.array([position[0], position[1], position[2]])

        # Apply global rotation matrix
        transformed = np.dot(rotation_matrix, translated_point)

        # Apply any additional transformations needed to match the expected output format
        # For example, scaling to match units, rounding to specific decimal places, etc.
        normalized = [
            round(transformed[0] * 100) / 100,  # Scale and round X
            round(transformed[1] * 100) / 100,  # Scale and round Y
            round(transformed[2] * 100) / 100,  # Scale and round Z
        ]

        return normalized

    def _point_to_array(self, point):
        """
        Convert a point in any format to a numpy array.

        :param point: Point in any format
        :return: Numpy array [x, y, z]
        """
        # Handle different point formats
        if hasattr(point, "x") and hasattr(point, "y") and hasattr(point, "z"):
            # It's likely a Vector or Point object with x, y, z attributes
            return np.array([point.x, point.y, point.z])
        elif hasattr(point, "x") and hasattr(point, "y"):
            # It's a 2D point object
            return np.array([point.x, point.y, 0])
        elif isinstance(point, (list, tuple)):
            # It's a list or tuple
            if len(point) == 2:  # 2D point
                return np.array([point[0], point[1], 0])
            else:  # 3D point
                return np.array([point[0], point[1], point[2]])
        else:
            # Try to convert to numpy array
            try:
                point_array = np.array(point)
                if point_array.size == 2:
                    return np.append(point_array, 0)  # Add z=0 for 2D points
                return point_array
            except:  # noqa: E722
                # Last resort fallback
                self.logger.warning(f"Could not parse point format: {type(point)}")
                return np.array([0, 0, 0])  # Return origin as fallback

    def _handle_ellipse(self, entity, model, rotation_matrix):
        """
        Handle ELLIPSE entity - basic implementation.

        :param entity: DXF ELLIPSE entity
        :param model: 3DM model
        :param rotation_matrix: Rotation matrix
        """
        try:
            # Get ellipse parameters
            center = self._rotate_point(entity.dxf.center, rotation_matrix)
            major_axis = np.array(entity.dxf.major_axis)

            # Calculate the major radius (length of major axis)
            major_radius = np.linalg.norm(major_axis)

            # Use a simplified circle if the conversion is too complex
            plane = rhino3dm.Plane(
                rhino3dm.Point3d(center[0], center[1], center[2]),
                rhino3dm.Vector3d(0, 0, 1),
            )

            circle = rhino3dm.Circle(plane, major_radius)
            model.Objects.AddCircle(circle)

        except Exception as e:
            self.logger.warning(f"Error processing ellipse: {e}")

    def _handle_spline(self, entity, model, rotation_matrix):
        """
        Handle SPLINE entity - basic implementation.

        :param entity: DXF SPLINE entity
        :param model: 3DM model
        :param rotation_matrix: Rotation matrix
        """
        try:
            # Get control points
            control_points = []
            for point in entity.control_points:
                rotated_point = self._rotate_point(point, rotation_matrix)
                control_points.append(rhino3dm.Point3d(rotated_point[0], rotated_point[1], rotated_point[2]))

            # If we have at least 2 control points, create a polyline as a simple representation
            if len(control_points) >= 2:
                # For simplicity, convert to polyline (a more accurate NURBS conversion would be complex)
                polyline = rhino3dm.Polyline()
                for point in control_points:
                    polyline.Add(point.X, point.Y, point.Z)

                model.Objects.AddPolyline(polyline)
        except Exception as e:
            self.logger.warning(f"Error processing spline: {e}")

    def _rotate_point(self, point, rotation_matrix):
        """
        Rotate a point using the rotation matrix.

        :param point: Point coordinates (can be tuple, list, Vector, etc.)
        :param rotation_matrix: Rotation matrix
        :return: Rotated point as numpy array
        """
        # Handle different point formats
        if hasattr(point, "x") and hasattr(point, "y") and hasattr(point, "z"):
            # It's likely a Vector or Point object with x, y, z attributes
            point_array = np.array([point.x, point.y, point.z])
        elif hasattr(point, "x") and hasattr(point, "y"):
            # It's a 2D point object
            point_array = np.array([point.x, point.y, 0])
        elif isinstance(point, (list, tuple)):
            # It's a list or tuple
            if len(point) == 2:  # 2D point
                point_array = np.array([point[0], point[1], 0])
            else:  # 3D point
                point_array = np.array([point[0], point[1], point[2]])
        else:
            # Unknown format, try to convert to numpy array and handle
            try:
                point_array = np.array(point)
                if point_array.size == 2:
                    point_array = np.append(point_array, 0)  # Add z=0 for 2D points
            except:  # noqa: E722
                # Last resort fallback
                self.logger.warning(f"Could not parse point format: {type(point)}")
                return np.array([0, 0, 0])  # Return origin as fallback

        # Apply rotation
        return np.dot(rotation_matrix, point_array)

    def _add_line_to_model(self, entity, model, rotation_matrix):
        """
        Add a LINE entity to the 3DM model.

        :param entity: DXF LINE entity
        :param model: 3DM model
        :param rotation_matrix: Rotation matrix
        """
        start_point = self._rotate_point(entity.dxf.start, rotation_matrix)
        end_point = self._rotate_point(entity.dxf.end, rotation_matrix)

        line = rhino3dm.Line(
            rhino3dm.Point3d(start_point[0], start_point[1], start_point[2]),
            rhino3dm.Point3d(end_point[0], end_point[1], end_point[2]),
        )

        model.Objects.AddLine(line)

    def _add_circle_to_model(self, entity, model, rotation_matrix):
        """
        Add a CIRCLE entity to the 3DM model.

        :param entity: DXF CIRCLE entity
        :param model: 3DM model
        :param rotation_matrix: Rotation matrix
        """
        center = self._rotate_point(entity.dxf.center, rotation_matrix)
        radius = entity.dxf.radius

        # Create a circle using a plane and radius
        plane = rhino3dm.Plane(
            rhino3dm.Point3d(center[0], center[1], center[2]),
            rhino3dm.Vector3d(0, 0, 1),  # Normal vector for the plane
        )

        circle = rhino3dm.Circle(plane, radius)
        model.Objects.AddCircle(circle)

    def _add_arc_to_model(self, entity, model, rotation_matrix):
        """
        Add an ARC entity to the 3DM model.

        :param entity: DXF ARC entity
        :param model: 3DM model
        :param rotation_matrix: Rotation matrix
        """
        center = self._rotate_point(entity.dxf.center, rotation_matrix)
        radius = entity.dxf.radius
        start_angle = entity.dxf.start_angle * (np.pi / 180.0)  # Convert to radians
        end_angle = entity.dxf.end_angle * (np.pi / 180.0)  # Convert to radians

        # Handle angle progression (DXF uses CCW, ensure proper mapping)
        if end_angle < start_angle:
            end_angle += 2 * np.pi

        # Create points for start, end and middle of the arc
        start_point = np.array(
            [
                center[0] + radius * np.cos(start_angle),
                center[1] + radius * np.sin(start_angle),
                center[2],
            ]
        )

        end_point = np.array(
            [
                center[0] + radius * np.cos(end_angle),
                center[1] + radius * np.sin(end_angle),
                center[2],
            ]
        )

        # Calculate a point in the middle of the arc for reliable arc creation
        mid_angle = (start_angle + end_angle) / 2
        mid_point = np.array(
            [
                center[0] + radius * np.cos(mid_angle),
                center[1] + radius * np.sin(mid_angle),
                center[2],
            ]
        )

        # Create the arc using 3 points
        arc = rhino3dm.Arc(
            rhino3dm.Point3d(start_point[0], start_point[1], start_point[2]),
            rhino3dm.Point3d(mid_point[0], mid_point[1], mid_point[2]),
            rhino3dm.Point3d(end_point[0], end_point[1], end_point[2]),
        )

        model.Objects.AddArc(arc)

    def _add_polyline_to_model(self, entity, model, rotation_matrix):
        """
        Add a POLYLINE or LWPOLYLINE entity to the 3DM model.

        :param entity: DXF POLYLINE or LWPOLYLINE entity
        :param model: 3DM model
        :param rotation_matrix: Rotation matrix
        """
        # For LWPOLYLINE with bulges (curved segments), we need special handling
        if entity.dxftype() == "LWPOLYLINE" and any(bulge != 0 for _, _, _, bulge, _ in entity.lwpoints):
            self._add_lwpolyline_with_bulges(entity, model, rotation_matrix)
            return

        # Create a polyline for straight segments
        polyline = rhino3dm.Polyline()

        # Get vertices based on entity type
        if entity.dxftype() == "LWPOLYLINE":
            # LWPOLYLINE has points as a sequence of (x, y) coordinates
            vertices = list(entity.vertices())
            for vertex in vertices:
                point = self._rotate_point((vertex[0], vertex[1]), rotation_matrix)
                polyline.Add(point[0], point[1], point[2])

            # Close the polyline if it's closed
            if entity.closed:  # Using the property directly for clarity
                polyline.Add(polyline[0])
        else:  # Regular POLYLINE
            for vertex in entity.vertices:
                point = self._rotate_point(
                    (
                        vertex.dxf.location.x,
                        vertex.dxf.location.y,
                        vertex.dxf.location.z,
                    ),
                    rotation_matrix,
                )
                polyline.Add(point[0], point[1], point[2])

            # Close the polyline if it's closed
            if entity.is_closed:
                polyline.Add(polyline[0])

        # Add the polyline to the model if it has at least 2 points
        if polyline.Count > 1:
            model.Objects.AddPolyline(polyline)

    def _add_lwpolyline_with_bulges(self, entity, model, rotation_matrix):
        """
        Add an LWPOLYLINE with bulges (curved segments) to the 3DM model.

        :param entity: DXF LWPOLYLINE entity
        :param model: 3DM model
        :param rotation_matrix: Rotation matrix
        """
        # Get all points with their bulges
        points = list(entity.lwpoints)
        count = len(points)

        if count < 2:
            return

        # Process each segment
        for i in range(count):
            # Get current point and next point (accounting for closed polylines)
            curr_idx = i
            next_idx = (i + 1) % count if entity.closed else (i + 1)

            # If we're at the last point and the polyline is not closed, break
            if next_idx >= count:
                break

            # Extract points and bulge
            x1, y1, _, bulge, _ = points[curr_idx]
            x2, y2, _, _, _ = points[next_idx]

            p1 = self._rotate_point((x1, y1), rotation_matrix)
            p2 = self._rotate_point((x2, y2), rotation_matrix)

            # Create a straight line if bulge is zero
            if bulge == 0:
                line = rhino3dm.Line(
                    rhino3dm.Point3d(p1[0], p1[1], p1[2]),
                    rhino3dm.Point3d(p2[0], p2[1], p2[2]),
                )
                model.Objects.AddLine(line)
            else:
                # Convert bulge to arc parameters
                # Bulge is the tangent of 1/4 of the included angle
                # angle = 4 * np.arctan(bulge)

                # Calculate center and radius
                dx, dy = x2 - x1, y2 - y1
                dist = np.sqrt(dx * dx + dy * dy)

                if abs(dist) < 1e-10:
                    continue  # Skip degenerate segments

                # Calculate perpendicular distance from chord to arc center
                h = (bulge * dist) / 2

                # Calculate center of arc
                cx = (x1 + x2) / 2 - h * (dy / dist)
                cy = (y1 + y2) / 2 + h * (dx / dist)

                # Calculate radius
                radius = np.sqrt((dist / 2) ** 2 + h**2)

                # Convert to 3D points and center
                # center = self._rotate_point((cx, cy), rotation_matrix)

                # Calculate start and end angles
                start_angle = np.arctan2(y1 - cy, x1 - cx)
                end_angle = np.arctan2(y2 - cy, x2 - cx)

                # Ensure angles are properly ordered based on bulge sign
                if bulge < 0:
                    # Swap for clockwise
                    start_angle, end_angle = end_angle, start_angle  # Fixed swap syntax

                # Calculate a middle point for the arc
                mid_angle = (start_angle + end_angle) / 2
                if bulge < 0 and end_angle > start_angle:
                    mid_angle -= np.pi
                elif bulge > 0 and start_angle > end_angle:
                    mid_angle += np.pi

                mx = cx + radius * np.cos(mid_angle)
                my = cy + radius * np.sin(mid_angle)
                mid_point = self._rotate_point((mx, my), rotation_matrix)

                # Create the arc
                arc = rhino3dm.Arc(
                    rhino3dm.Point3d(p1[0], p1[1], p1[2]),
                    rhino3dm.Point3d(mid_point[0], mid_point[1], mid_point[2]),
                    rhino3dm.Point3d(p2[0], p2[1], p2[2]),
                )
                model.Objects.AddArc(arc)
