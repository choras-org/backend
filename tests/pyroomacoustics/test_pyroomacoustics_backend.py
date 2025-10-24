"""Test the pyroomacoustics simulation backend.
"""
import pytest
import numpy as np
import numpy.testing as npt
import os
import json
import simulation_backend.pyroomacoustics_interface as pra_interface
import tempfile
from pathlib import Path
import shutil


def default_data_path():
    """Get the path to the default data folder."""
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)))


def load_default_input_data():
    """Load the example input data."""
    with open(os.path.join(
            default_data_path(),
            "test_input_pyroomacoustics.json"), 'r') as f:
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
        default_data_path(), "test_room_pyroomacoustics.geo")

    with tempfile.TemporaryDirectory() as tmpdirname:
        tmp_path = Path(tmpdirname) / "temp_input.json"
        shutil.copy(geo_file, Path(tmpdirname))
        input_tmp['geo_path'] = os.path.join(
            tmpdirname, "test_room_pyroomacoustics.geo")
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
        os.path.join(directory, "test_room_pyroomacoustics.geo"))


def test_get_receiver(default_input_data):
    """Test the get_receiver function."""
    receiver = pra_interface.get_receiver_positions(default_input_data)

    assert receiver is not None
    npt.assert_array_equal(receiver, np.array([[1.0, 1.0, 1.5]]))


def test_get_source_positions(default_input_data):
    """Test the get_source_positions function."""
    sources = pra_interface.get_source_positions(default_input_data)

    assert sources is not None
    npt.assert_array_equal(sources, np.array([2.0, 2.0, 1.5]))


def test_export_rir_to_input(create_temporary_input_file):
    """Test the export_rir_to_input function."""
    rir = np.array([0.0, 0.1, 0.2, 0.3, 0.4, 0.5], dtype=float)
    pra_interface.export_rir_to_input(create_temporary_input_file, rir)

    with open(create_temporary_input_file, 'r') as f:
        data = json.load(f)

    npt.assert_array_equal(
        data['results'][0]['responses'][0]['receiverResults'], rir)


def test_run_simulation(create_temporary_input_file):
    """Run the full simulation pipeline."""
    pra_interface.pyroomacoustics_method(create_temporary_input_file)

    with open(create_temporary_input_file, 'r') as f:
        data = json.load(f)

    rir = np.array(data['results'][0]['responses'][0]['receiverResults'])

    assert rir is not None
    assert len(rir) > 0
    assert isinstance(rir, np.ndarray)
    assert np.any(np.abs(rir) >= 1e-6)
