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
# Tests: LocalExecutor.execute
# =============================================================================

class TestLocalExecutorExecute:

    @patch("app.services.executors.local_executor.get_host_path_for_container_path")
    def test_returns_job_id_and_container(
        self, mock_resolve, mock_docker_client, method_config, sim_config
    ):
        """execute() should return a (job_id, container) tuple."""
        mock_resolve.return_value = "/host/uploads"
        fake_container = MagicMock()
        mock_docker_client.containers.run.return_value = fake_container

        executor = LocalExecutor()
        job_id, container = executor.execute(method_config, sim_config)

        assert isinstance(job_id, str)
        assert len(job_id) == 36  # UUID4 format
        assert container is fake_container

    @patch("app.services.executors.local_executor.get_host_path_for_container_path")
    def test_stores_job_in_internal_dict(
        self, mock_resolve, mock_docker_client, method_config, sim_config
    ):
        """execute() should store the container in _jobs keyed by job_id."""
        mock_resolve.return_value = "/host/uploads"
        fake_container = MagicMock()
        mock_docker_client.containers.run.return_value = fake_container

        executor = LocalExecutor()
        job_id, _ = executor.execute(method_config, sim_config)

        assert job_id in executor._jobs
        assert executor._jobs[job_id] is fake_container

    @patch("app.services.executors.local_executor.get_host_path_for_container_path")
    def test_passes_correct_image_and_env(
        self, mock_resolve, mock_docker_client, method_config, sim_config
    ):
        """execute() should pass the image and env vars to containers.run()."""
        mock_resolve.return_value = "/host/uploads"
        mock_docker_client.containers.run.return_value = MagicMock()

        executor = LocalExecutor()
        executor.execute(method_config, sim_config)

        call_kwargs = mock_docker_client.containers.run.call_args
        assert call_kwargs.kwargs["image"] == "my-sim-image:latest"
        assert call_kwargs.kwargs["environment"] == sim_config["env"]

    @patch("app.services.executors.local_executor.get_host_path_for_container_path")
    def test_volume_mount_uses_resolved_host_path(
        self, mock_resolve, mock_docker_client, method_config, sim_config
    ):
        """execute() should mount the resolved host path into the container."""
        mock_resolve.return_value = "/host/uploads"
        mock_docker_client.containers.run.return_value = MagicMock()

        executor = LocalExecutor()
        executor.execute(method_config, sim_config)

        call_kwargs = mock_docker_client.containers.run.call_args.kwargs
        volumes = call_kwargs["volumes"]
        assert "/host/uploads" in volumes
        assert volumes["/host/uploads"]["bind"] == "/app/uploads"
        assert volumes["/host/uploads"]["mode"] == "rw"

    @patch("app.services.executors.local_executor.get_host_path_for_container_path")
    def test_container_runs_detached(
        self, mock_resolve, mock_docker_client, method_config, sim_config
    ):
        """execute() should always run containers in detached mode."""
        mock_resolve.return_value = "/host/uploads"
        mock_docker_client.containers.run.return_value = MagicMock()

        executor = LocalExecutor()
        executor.execute(method_config, sim_config)

        call_kwargs = mock_docker_client.containers.run.call_args.kwargs
        assert call_kwargs["detach"] is True

    @patch("app.services.executors.local_executor.get_host_path_for_container_path")
    def test_raises_on_docker_run_failure(
        self, mock_resolve, mock_docker_client, method_config, sim_config
    ):
        """execute() should raise if containers.run() throws."""
        mock_resolve.return_value = "/host/uploads"
        mock_docker_client.containers.run.side_effect = Exception("Image not found")

        executor = LocalExecutor()
        with pytest.raises(Exception, match="Image not found"):
            executor.execute(method_config, sim_config)

    @patch("app.services.executors.local_executor.get_host_path_for_container_path")
    def test_each_execution_gets_unique_job_id(
        self, mock_resolve, mock_docker_client, method_config, sim_config
    ):
        """Multiple execute() calls should produce unique job IDs."""
        mock_resolve.return_value = "/host/uploads"
        mock_docker_client.containers.run.return_value = MagicMock()

        executor = LocalExecutor()
        job_id_1, _ = executor.execute(method_config, sim_config)
        job_id_2, _ = executor.execute(method_config, sim_config)

        assert job_id_1 != job_id_2

    @patch("app.services.executors.local_executor.get_host_path_for_container_path")
    def test_uses_container_name_from_method_config(
        self, mock_resolve, mock_docker_client, method_config, sim_config
    ):
        """execute() should pass container_name from method_config."""
        mock_resolve.return_value = "/host/uploads"
        mock_docker_client.containers.run.return_value = MagicMock()

        executor = LocalExecutor()
        executor.execute(method_config, sim_config)

        call_kwargs = mock_docker_client.containers.run.call_args.kwargs
        assert call_kwargs["name"] == "sim_container"

