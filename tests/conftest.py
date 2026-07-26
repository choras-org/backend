import json
import os

import pytest

from config import DefaultConfig

_MOCK_METHODS_CONFIG = [
    {
        "simulationType": "DG",
        "containerImage": "dg_image:latest",
        "envVars": {"CUDA_VISIBLE_DEVICES": "0"},
        "label": "Discontinuous Galerkin method",
        "settings": "dg_setting.json",
        "entryFile": "DGinterface.py",
        "repositoryURL": "https://github.com/Building-acoustics-TU-Eindhoven/edg-acoustics/",
        "documentationURL": "https://dg-roomacoustics.readthedocs.io/en/latest/",
    },
    {
        "simulationType": "DE",
        "containerImage": "de_image:latest",
        "envVars": {},
        "label": "Diffusion Equation method",
        "settings": "de_setting.json",
        "entryFile": "DEinterface.py",
        "repositoryURL": "https://github.com/Building-acoustics-TU-Eindhoven/acousticDE/",
        "documentationURL": "https://building-acoustics-tu-eindhoven.github.io/acousticDE/index.html",
    },
    {
        "simulationType": "MyNewMethod",
        "containerImage": "mynew_image:latest",
        "envVars": {},
        "label": "My New Method",
        "entryFile": "MyNewMethodInterface.py",
        "settings": "my_new_setting.json",
        "repositoryURL": "",
        "documentationURL": "",
    },
    {
        "simulationType": "PA",
        "containerImage": "pa_image:latest",
        "envVars": {},
        "label": "Pyromacoustics Method",
        "entryFile": "pyroomacoustics_interface.py",
        "settings": "examples.json",
        "repositoryURL": "",
        "documentationURL": "",
    },
]


@pytest.fixture
def simulation_backend_files(tmp_path, monkeypatch):
    """Point DefaultConfig at mock simulation-backend files in a temp dir.

    Skips creation if real files are already present on disk (local dev with a
    real simulation-backend checkout). Apply explicitly via
    @pytest.mark.usefixtures for unittest.TestCase subclasses.
    """
    if os.path.exists(DefaultConfig.METHODS_CONFIG_PATH) and os.path.isdir(
        DefaultConfig.SETTINGS_FILE_FOLDER
    ):
        return

    settings_dir = tmp_path / "example_settings"
    settings_dir.mkdir()

    config_file = tmp_path / "methods-config.json"
    config_file.write_text(json.dumps(_MOCK_METHODS_CONFIG))

    for entry in _MOCK_METHODS_CONFIG:
        if entry.get("settings"):
            (settings_dir / entry["settings"]).touch()

    monkeypatch.setattr(DefaultConfig, "METHODS_CONFIG_PATH", str(config_file))
    monkeypatch.setattr(DefaultConfig, "SETTINGS_FILE_FOLDER", str(settings_dir))
