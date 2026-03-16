import os
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from pathlib import Path

# ── adjust this import to match your actual module path ──────────────────────
from app.services.executors.local_executor import LocalExecutor

# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_docker_client():
    """Returns a fully mocked docker client."""
    with patch("app.services.executors.local_executor.docker.from_env") as mock_from_env:
        client = MagicMock()
        mock_from_env.return_value = client
        yield client


@pytest.fixture
def container_with_mounts():
    """Returns a fake container object with a realistic Mounts structure."""
    container = MagicMock()
    container.attrs = {
        "Mounts": [
            {
                "Source": "/host/uploads",
                "Destination": "/app/uploads",
            }
        ]
    }
    return container


@pytest.fixture
def method_config():
    return {
        "container_image": "my-sim-image:latest",
        "container_name": "sim_container",
        "command": "python run.py",
    }


@pytest.fixture
def sim_config():
    return {
        "env": {
            "JSON_PATH": "/app/uploads/input.json",
        }
    }


# =============================================================================
# Tests: LocalExecutor.execute - Error/Edge Cases
# =============================================================================

class TestLocalExecutorExecuteEdgeCases:
    @patch("app.services.executors.local_executor.get_host_path_for_container_path", return_value="/host/uploads")
    def test_docker_image_not_found(self, mock_resolve, mock_docker_client, method_config, sim_config):
        """Should raise an error error if Docker image does not exist locally."""
        mock_docker_client.containers.run.side_effect = Exception("No such image: my-sim-image:latest")
        executor = LocalExecutor()
        with pytest.raises(Exception, match="No such image"):
            executor.execute(method_config, sim_config)

    @patch("app.services.executors.local_executor.get_host_path_for_container_path", return_value="/host/uploads")
    def test_docker_socket_not_available(self, mock_resolve):
        """Should raise an error error if Docker daemon is down (docker.from_env fails)."""
        with patch("app.services.executors.local_executor.docker.from_env", side_effect=Exception("Docker daemon not available")):
            executor = LocalExecutor()
            with pytest.raises(Exception, match="Docker daemon not available"):
                executor.execute({"container_image": "img", "container_name": "name", "command": None}, {"env": {"JSON_PATH": "/app/uploads/input.json"}})

    @patch("app.services.executors.local_executor.get_host_path_for_container_path", return_value="/host/uploads")
    def test_json_path_missing(self, mock_resolve, mock_docker_client, method_config, sim_config):
        """Should raise an error error if JSON_PATH is missing from sim_config['env']."""
        bad_sim_config = {"env": {}}  # No JSON_PATH
        executor = LocalExecutor()
        with pytest.raises(Exception):
            executor.execute(method_config, bad_sim_config)

    @patch("app.services.executors.local_executor.get_host_path_for_container_path")
    def test_no_matching_mount(self, mock_resolve, mock_docker_client, method_config, sim_config):
        """Should raise an error if no mount covers the container path."""
        mock_resolve.side_effect = RuntimeError("No mount found covering container path")
        executor = LocalExecutor()
        with pytest.raises(RuntimeError, match="No mount found covering container path"):
            executor.execute(method_config, sim_config)

    @patch("app.services.executors.local_executor.get_host_path_for_container_path", return_value="/host/uploads")
    def test_container_exits_nonzero_obj_missing(self, mock_resolve, mock_docker_client, method_config, sim_config):
        """If the .obj file is missing, container exits non-zero but execute() still returns container object (silent bad day)."""
        fake_container = MagicMock()
        fake_container.wait.return_value = {"StatusCode": 1}  # Simulate failure
        mock_docker_client.containers.run.return_value = fake_container
        executor = LocalExecutor()
        job_id, container = executor.execute(method_config, sim_config)
        assert job_id in executor._jobs
        assert container is fake_container
        # No error is raised here, but you could check logs or container.wait().

    @patch("app.services.executors.local_executor.get_host_path_for_container_path", return_value="/host/uploads")
    def test_duplicate_container_name_conflict(self, mock_resolve, mock_docker_client, method_config, sim_config):
        """Should raise an error error if Docker raises a conflict on duplicate container_name."""
        mock_docker_client.containers.run.side_effect = Exception("Conflict. The container is already in use.")
        executor = LocalExecutor()
        with pytest.raises(Exception, match="already in use"):
            executor.execute(method_config, sim_config)