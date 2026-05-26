import os
import shutil
import pytest
import tempfile
from pathlib import Path
from simulation_backend.DGinterface import dg_method
import json
import gmsh
import numpy as np


def default_data_path():
    """Get the path to the default data folder."""
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)))


def load_default_input_data():
    """Load the example input data."""
    with open(os.path.join(
            default_data_path(),
            "test_input_edg_acoustics.json"), 'r') as f:
        data = json.load(f)

    return data


@pytest.fixture
def default_input_data():
    """Fixture to load the example input data."""
    return load_default_input_data()


@pytest.fixture
def create_temporary_input_file():
    """Fixture to create a temporary input JSON file which can be reused to
    write results to."""
    input_tmp = load_default_input_data()
    geo_file = os.path.join(
        default_data_path(), "test_room_edg_acoustics.geo")
    msh_file = os.path.join(
        default_data_path(), "test_room_edg_acoustics.msh")

    with tempfile.TemporaryDirectory() as tmpdirname:
        tmp_path = Path(tmpdirname) / "temp_input.json"
        shutil.copy(geo_file, Path(tmpdirname))
        shutil.copy(msh_file, Path(tmpdirname))
        input_tmp['geo_path'] = os.path.join(
            tmpdirname, "test_room_edg_acoustics.geo")
        input_tmp['msh_path'] = os.path.join(
            tmpdirname, "test_room_edg_acoustics.msh")
        with open(tmp_path, 'w') as f:
            json.dump(input_tmp, f)

        yield str(tmp_path)

    return str(tmp_path)


def test_create_tmp_file(create_temporary_input_file):


    """Test the creation of a temporary input file.
    """
    directory = os.path.dirname(create_temporary_input_file)

    assert os.path.exists(create_temporary_input_file)
    assert os.path.exists(
        os.path.join(directory, "test_room_edg_acoustics.geo"))
    assert os.path.exists(
        os.path.join(directory, "test_room_edg_acoustics.msh"))


def test_edg_acoustics(create_temporary_input_file):
    """
    Test the edg acoustics simulation method.
    """

    gmsh.initialize()
    dg_method(create_temporary_input_file)
    gmsh.finalize()

    with open(create_temporary_input_file, 'r') as f:
         data = json.load(f)

    rir = np.array(data['results'][0]['responses'][0]['receiverResults'])

    assert rir is not None
    assert len(rir) > 0
    assert isinstance(rir, np.ndarray)
    assert np.any(np.abs(rir) >= 1e-6)
