import numpy as np

from app.services.geometry_service import _orient_faces_outward

# Floor plan of an L-shaped room. Walls 2 and 3 form the inner corner,
# which is where the old code went wrong.
L_PLAN = [(0, 0), (2, 0), (2, 1), (1, 1), (1, 2), (0, 2)]
# Floor plan of a small cuboid floating inside the room, like a hanging reflector.
CUBOID_PLAN = [(0.3, 0.3), (0.6, 0.3), (0.6, 0.6), (0.3, 0.6)]


def prism(plan, z0, z1, top=True):
    """
    Build the walls, floor and (optionally) ceiling of a shape with a given floor plan.

    Parameters
    ----------
    plan : list of (float, float)
        Corners of the floor plan, going round counter-clockwise.
    z0, z1 : float
        Height of the floor and of the ceiling.
    top : bool, optional
        Whether to add the ceiling. Default is True.

    Returns
    -------
    list of list of (float, float, float)
        One list of corner points per face, ordered so that the face normal
        points out of the shape.
    """
    n = len(plan)
    faces = [
        [
            (*plan[i], z0),
            (*plan[(i + 1) % n], z0),
            (*plan[(i + 1) % n], z1),
            (*plan[i], z1),
        ]
        for i in range(n)
    ]
    faces.append([(x, y, z0) for x, y in reversed(plan)])
    if top:
        faces.append([(x, y, z1) for x, y in plan])
    return faces


def area_vector(pts):
    """
    Compute the face normal, scaled by the face area.

    Parameters
    ----------
    pts : list of (float, float, float)
        Corner points of the face, in order.

    Returns
    -------
    numpy.ndarray
        Vector of length 3.
    """
    p = np.asarray(pts, dtype=float)
    return np.cross(p[1:-1] - p[0], p[2:] - p[0]).sum(axis=0) / 2


def run(coord_faces, scrambled):
    """
    Scramble some faces, run the orientation fix and report the result.

    The faces are first turned into the form the backend uses: one vertex
    list, and each face as 1-based indices into it.

    Parameters
    ----------
    coord_faces : list of list of (float, float, float)
        Correctly oriented faces, as corner points.
    scrambled : set of int
        Indices of the faces to reverse before running the fix.

    Returns
    -------
    list of numpy.ndarray
        The area-scaled normal of every face after the fix.
    """
    vertices, index = [], {}
    faces = []
    for k, f in enumerate(coord_faces):
        for p in f:
            if p not in index:
                vertices.append(p)
                index[p] = len(vertices)
        idx = [index[p] for p in f]
        faces.append(idx[::-1] if k in scrambled else idx)
    _orient_faces_outward(faces, vertices)
    return [area_vector([vertices[i - 1] for i in f]) for f in faces]


def test_l_room_with_obstacle():
    room = prism(L_PLAN, 0, 3)
    cuboid = prism(CUBOID_PLAN, 1, 1.5)
    # Room faces should point out of the room. The cuboid is an obstacle, so
    # its faces should point into the cuboid.
    expected = [area_vector(f) for f in room] + [-area_vector(f) for f in cuboid]
    # Turn around both inner-corner walls, the floor and one side of the cuboid.
    scrambled = {2, 3, 6, len(room) + 1}

    result = run(room + cuboid, scrambled)

    for k, (got, want) in enumerate(zip(result, expected)):
        assert got @ want > 0, f"face {k} points the wrong way"


def test_u_obstacle_in_u_room():
    # A U-shaped room with a U-shaped obstacle that wraps around the end of the
    # gap between the room's arms. The average of the obstacle's vertices lies
    # in that gap, which is outside the room.
    u_room = [(0, 0), (3, 0), (3, 3), (2, 3), (2, 1), (1, 1), (1, 3), (0, 3)]
    u_obstacle = [
        (0.5, 0.5),
        (2.5, 0.5),
        (2.5, 2.5),
        (2.2, 2.5),
        (2.2, 0.8),
        (0.8, 0.8),
        (0.8, 2.5),
        (0.5, 2.5),
    ]
    room = prism(u_room, 0, 3)
    obstacle = prism(u_obstacle, 1, 2)
    expected = [area_vector(f) for f in room] + [-area_vector(f) for f in obstacle]

    result = run(room + obstacle, scrambled={0, len(room)})

    for k, (got, want) in enumerate(zip(result, expected)):
        assert got @ want > 0, f"face {k} points the wrong way"


def test_open_l_room_wound_inward():
    room = prism(L_PLAN, 0, 3, top=False)
    expected = [area_vector(f) for f in room]
    # A room without a ceiling, where every face points the wrong way
    # except one inner-corner wall.
    scrambled = set(range(len(room))) - {3}

    result = run(room, scrambled)

    for k, (got, want) in enumerate(zip(result, expected)):
        assert got @ want > 0, f"face {k} points the wrong way"
