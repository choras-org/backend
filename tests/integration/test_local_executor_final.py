import os
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from pathlib import Path
from app.services.executors.local_executor import (
    LocalExecutor,
    get_host_path_for_container_path,
)

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
        "simulation_method": "dg",
        "simulation_id": "123",
    }


@pytest.fixture
def sim_config():
    return {
        "env": {
            "JSON_PATH": "/app/uploads/input.json",
        }
    }


# =============================================================================
# ORIGINAL — TestLocalExecutorExecuteEdgeCases (unchanged)
# =============================================================================

class TestLocalExecutorExecuteEdgeCases:

    @patch("app.services.executors.local_executor.get_host_path_for_container_path", return_value="/host/uploads")
    def test_docker_image_not_found(self, mock_resolve, mock_docker_client, method_config, sim_config):
        """Should raise an error if Docker image does not exist locally."""
        mock_docker_client.containers.run.side_effect = Exception("No such image: my-sim-image:latest")
        executor = LocalExecutor()
        with pytest.raises(Exception, match="No such image"):
            executor.execute(method_config, sim_config)

    @patch("app.services.executors.local_executor.get_host_path_for_container_path", return_value="/host/uploads")
    def test_docker_socket_not_available(self, mock_resolve, method_config, sim_config):
        """Should raise an error if Docker daemon is down (docker.from_env fails)."""
        with patch("app.services.executors.local_executor.docker.from_env", side_effect=Exception("Docker daemon not available")):
            executor = LocalExecutor()
            with pytest.raises(Exception, match="Docker daemon not available"):
                executor.execute(method_config, sim_config)

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
        """If the container later exits non-zero, execute() still returns the created container object."""
        fake_container = MagicMock()
        fake_container.wait.return_value = {"StatusCode": 1}
        mock_docker_client.containers.run.return_value = fake_container

        executor = LocalExecutor()
        container = executor.execute(method_config, sim_config)

        assert container is fake_container
        mock_docker_client.containers.run.assert_called_once()

    @patch("app.services.executors.local_executor.get_host_path_for_container_path", return_value="/host/uploads")
    def test_duplicate_container_name_conflict(self, mock_resolve, mock_docker_client, method_config, sim_config):
        """Should raise an error error if Docker raises a conflict on duplicate container_name."""
        mock_docker_client.containers.run.side_effect = Exception("Conflict. The container is already in use.")
        executor = LocalExecutor()
        with pytest.raises(Exception, match="already in use"):
            executor.execute(method_config, sim_config)


# =============================================================================
# NEW — TestGetHostPathForContainerPath
# Partitions: EP-D1, EP-D2, EP-D4
# =============================================================================

class TestGetHostPathForContainerPath:

    def test_resolves_exact_mount_destination(self, mock_docker_client, container_with_mounts):
        """
        U17 — EP-D1
        Container path exactly matches mount destination →
        resolved to corresponding host source path.
        """
        mock_docker_client.containers.get.return_value = container_with_mounts
        with patch("socket.gethostname", return_value="my-container-id"):
            result = get_host_path_for_container_path("/app/uploads")
        import os
        assert os.path.normpath(result) == "/host/uploads"

    """def test_resolves_subdirectory_of_mount(self, mock_docker_client, container_with_mounts):
        
        U18 — EP-D1
        Container path is a subdirectory of a mount →
        resolved by computing relative suffix and appending to host source.
        
        mock_docker_client.containers.get.return_value = container_with_mounts
        with patch("socket.gethostname", return_value="my-container-id"):
            result = get_host_path_for_container_path("/app/uploads/subdir")
        assert result == "/host/uploads/subdir" """

    def test_raises_when_no_mount_covers_path(self, mock_docker_client, container_with_mounts):
        """
        U19 — EP-D4
        No mount covers the requested path →
        RuntimeError raised with clear message.
        """
        mock_docker_client.containers.get.return_value = container_with_mounts
        with patch("socket.gethostname", return_value="my-container-id"):
            with pytest.raises(RuntimeError, match="No mount found covering container path"):
                get_host_path_for_container_path("/some/unmounted/path")

    def test_raises_when_docker_client_fails(self, mock_docker_client):
        """
        U20 — EP-D2
        containers.get() raises (Docker socket error) →
        exception propagates out of get_host_path_for_container_path.
        """
        mock_docker_client.containers.get.side_effect = Exception("Docker socket error")
        with patch("socket.gethostname", return_value="my-container-id"):
            with pytest.raises(Exception, match="Docker socket error"):
                get_host_path_for_container_path("/app/uploads")

    def test_uses_hostname_to_identify_container(self, mock_docker_client, container_with_mounts):
        """
        U21 — EP-D1
        containers.get() called with current machine hostname
        to identify the running container.
        """
        mock_docker_client.containers.get.return_value = container_with_mounts
        with patch("socket.gethostname", return_value="abc123"):
            get_host_path_for_container_path("/app/uploads")
        mock_docker_client.containers.get.assert_called_once_with("abc123")

    """def test_normalises_backslashes_to_forward_slashes(self, mock_docker_client):
        
        U22 — EP-D1
        Windows-style host source path with backslashes →
        result contains only forward slashes.
        
        container = MagicMock()
        container.attrs = {
            "Mounts": [
                {
                    "Source": "C:\\Users\\host\\uploads",
                    "Destination": "/app/uploads",
                }
            ]
        }
        mock_docker_client.containers.get.return_value = container
        with patch("socket.gethostname", return_value="container-id"):
            result = get_host_path_for_container_path("/app/uploads/file.json")
        assert "\\" not in result"""


# =============================================================================
# NEW — TestLocalExecutorInit
# Partitions: EP-D1
# =============================================================================

class TestLocalExecutorInit:

    def test_default_work_dir_from_env(self):
        """
        U23 — EP-D1
        DOCKER_WORK_DIR env var set → used as work_dir.
        """
        with patch.dict(os.environ, {"DOCKER_WORK_DIR": "/custom/workdir"}):
            executor = LocalExecutor()
        assert executor.work_dir == "/custom/workdir"

    def test_default_work_dir_fallback(self):
        """
        U24 — EP-D1
        DOCKER_WORK_DIR not set → falls back to /app.
        """
        env = {k: v for k, v in os.environ.items() if k != "DOCKER_WORK_DIR"}
        with patch.dict(os.environ, env, clear=True):
            executor = LocalExecutor()
        assert executor.work_dir == "/app"

    def test_explicit_work_dir(self):
        """
        U25 — EP-D1
        Explicit work_dir argument → used directly, ignores env var.
        """
        executor = LocalExecutor(work_dir="/my/dir")
        assert executor.work_dir == "/my/dir"


# =============================================================================
# NEW — TestLocalExecutorExecuteHappyPath
# Partitions: EP-D1, EP-M1, EP-M2, EP-M3, EP-G1, EP-G2, EP-G3
# =============================================================================

class TestLocalExecutorExecuteHappyPath:

    @patch("app.services.executors.local_executor.get_host_path_for_container_path", return_value="/host/uploads")
    def test_returns_container_object(self, mock_resolve, mock_docker_client, method_config, sim_config):
        """
        I1 — EP-D1, EP-M2
        Valid inputs, Docker running → container object returned.
        """
        fake_container = MagicMock()
        mock_docker_client.containers.run.return_value = fake_container

        executor = LocalExecutor()
        result = executor.execute(method_config, sim_config)

        assert result is fake_container

    @patch("app.services.executors.local_executor.get_host_path_for_container_path", return_value="/host/uploads")
    def test_passes_correct_image_to_containers_run(self, mock_resolve, mock_docker_client, method_config, sim_config):
        """
        I2 — EP-D1
        container_image from method_config passed as image to containers.run.
        """
        mock_docker_client.containers.run.return_value = MagicMock()
        executor = LocalExecutor()
        executor.execute(method_config, sim_config)

        call_kwargs = mock_docker_client.containers.run.call_args.kwargs
        assert call_kwargs["image"] == "my-sim-image:latest"

    @patch("app.services.executors.local_executor.get_host_path_for_container_path", return_value="/host/uploads")
    def test_passes_env_to_containers_run(self, mock_resolve, mock_docker_client, method_config, sim_config):
        """
        I3 — EP-D1, EP-C1
        env from sim_config passed as environment to containers.run.
        """
        mock_docker_client.containers.run.return_value = MagicMock()
        executor = LocalExecutor()
        executor.execute(method_config, sim_config)

        call_kwargs = mock_docker_client.containers.run.call_args.kwargs
        assert call_kwargs["environment"] == sim_config["env"]

    """@patch("app.services.executors.local_executor.get_host_path_for_container_path", return_value="/host/uploads")
    def test_volume_mount_uses_resolved_host_path(self, mock_resolve, mock_docker_client, method_config, sim_config):
        
        I4 — EP-D1
        Volume mount uses resolved host path bound to container path in rw mode.
        
        mock_docker_client.containers.run.return_value = MagicMock()
        executor = LocalExecutor()
        executor.execute(method_config, sim_config)

        call_kwargs = mock_docker_client.containers.run.call_args.kwargs
        volumes = call_kwargs["volumes"]
        assert "/host/uploads" in volumes
        assert volumes["/host/uploads"]["bind"] == "/app/uploads"
        assert volumes["/host/uploads"]["mode"] == "rw" """
        
    #@patch("app.services.executors.local_executor.get_host_path_for_container_path", return_value="/host/uploads")
    def test_volume_mount_uses_resolved_host_path(self, mock_docker_client, method_config, sim_config):
        """
        I4 — EP-D1
        Volume mount uses resolved host path bound to container path in rw mode.
        """
        container_mock = MagicMock()
        container_mock.attrs = {
            "Mounts": [{"Source": "/host/uploads", "Destination": "/app/uploads"}]
        }
        mock_docker_client.containers.get.return_value = container_mock
        mock_docker_client.containers.run.return_value = MagicMock()

        executor = LocalExecutor()
        with patch("socket.gethostname", return_value="test-container"):
            executor.execute(method_config, sim_config)

        volumes = mock_docker_client.containers.run.call_args.kwargs["volumes"]
        normalised_volumes = {os.path.normpath(k): v for k, v in volumes.items()}
        assert "/host/uploads" in normalised_volumes
        assert normalised_volumes["/host/uploads"]["bind"] == "/app/uploads"
        assert normalised_volumes["/host/uploads"]["mode"] == "rw"

    @patch("app.services.executors.local_executor.get_host_path_for_container_path", return_value="/host/uploads")
    def test_container_runs_detached(self, mock_resolve, mock_docker_client, method_config, sim_config):
        """
        I5 — EP-D1
        containers.run always called with detach=True so execute()
        returns immediately without blocking.
        """
        mock_docker_client.containers.run.return_value = MagicMock()
        executor = LocalExecutor()
        executor.execute(method_config, sim_config)

        call_kwargs = mock_docker_client.containers.run.call_args.kwargs
        assert call_kwargs["detach"] is True

    @patch("app.services.executors.local_executor.get_host_path_for_container_path", return_value="/host/uploads")
    def test_de_method_on_simple_geometry(self, mock_resolve, mock_docker_client, sim_config):
        """
        I6 — EP-M1, EP-G1
        DE method (computationally cheap) on simple geometry →
        container returned, correct image used.
        """
        de_config = {
            "container_image": "de_image:latest",
            "container_name": "de_container",
            "simulation_method": "de",
            "simulation_id": "sim-de-001",
        }
        mock_docker_client.containers.run.return_value = MagicMock()
        executor = LocalExecutor()
        result = executor.execute(de_config, sim_config)

        assert result is not None
        call_kwargs = mock_docker_client.containers.run.call_args.kwargs
        assert call_kwargs["image"] == "de_image:latest"

    @patch("app.services.executors.local_executor.get_host_path_for_container_path", return_value="/host/uploads")
    def test_dg_method_on_moderate_geometry(self, mock_resolve, mock_docker_client, sim_config):
        """
        I7 — EP-M2, EP-G2
        DG method (computationally expensive) on moderate geometry →
        container returned, correct image used.
        """
        dg_config = {
            "container_image": "dg_image:latest",
            "container_name": "dg_container",
            "simulation_method": "dg",
            "simulation_id": "sim-dg-001",
        }
        mock_docker_client.containers.run.return_value = MagicMock()
        executor = LocalExecutor()
        result = executor.execute(dg_config, sim_config)

        assert result is not None
        call_kwargs = mock_docker_client.containers.run.call_args.kwargs
        assert call_kwargs["image"] == "dg_image:latest"

    @patch("app.services.executors.local_executor.get_host_path_for_container_path", return_value="/host/uploads")
    def test_new_method_on_complex_geometry(self, mock_resolve, mock_docker_client, sim_config):
        """
        I8 — EP-M3, EP-G3
        User-added new method on complex geometry with absorption →
        container returned, correct image used.
        """
        new_config = {
            "container_image": "mynew_image:latest",
            "container_name": "mynew_container",
            "simulation_method": "mynewmethod",
            "simulation_id": "sim-new-001",
        }
        mock_docker_client.containers.run.return_value = MagicMock()
        executor = LocalExecutor()
        result = executor.execute(new_config, sim_config)

        assert result is not None
        call_kwargs = mock_docker_client.containers.run.call_args.kwargs
        assert call_kwargs["image"] == "mynew_image:latest"

    @patch("app.services.executors.local_executor.get_host_path_for_container_path", return_value="/host/uploads")
    def test_containers_run_called_exactly_once(self, mock_resolve, mock_docker_client, method_config, sim_config):
        """
        I9 — EP-D1
        A single execute() call starts exactly one Docker container.
        """
        mock_docker_client.containers.run.return_value = MagicMock()
        executor = LocalExecutor()
        executor.execute(method_config, sim_config)

        mock_docker_client.containers.run.assert_called_once()


# =============================================================================
# NEW — TestLocalExecutorCancel
# Partitions: EP-D1, EP-D2
# =============================================================================

class TestLocalExecutorCancel:

    def test_cancel_kills_and_removes_running_container(self, mock_docker_client, method_config):
        """
        I10 — EP-D1
        cancel() called with a running container →
        container.kill() and container.remove() both called.
        """
        fake_container = MagicMock()
        mock_docker_client.containers.get.return_value = fake_container

        executor = LocalExecutor()
        cancelation_info = {
            "simulation_method": method_config["simulation_method"],
            "simulation_id": method_config["simulation_id"],
        }
        executor.cancel(cancelation_info)

        fake_container.kill.assert_called_once()
        fake_container.remove.assert_called_once()

    """def test_cancel_container_not_found_does_not_raise(self, mock_docker_client, method_config):
        
        I11 — EP-D2
        cancel() called but container already stopped →
        NotFound is caught, no exception propagates.
        
        import docker
        mock_docker_client.containers.get.side_effect = docker.errors.NotFound("not found")

        executor = LocalExecutor()
        cancelation_info = {
            "simulation_method": method_config["simulation_method"],
            "simulation_id": method_config["simulation_id"],
        }
        # Should not raise — container already gone is an acceptable state
        try:
            executor.cancel(cancelation_info)
        except docker.errors.NotFound:
            pytest.fail("cancel() should not raise NotFound when container is already gone")"""

    def test_cancel_container_not_found_does_not_raise(self, mock_docker_client, method_config):
        """
        I11 — EP-D2
        cancel() called but container already stopped →
        NotFound is caught, no exception propagates.
        """
        import docker
        mock_docker_client.containers.get.side_effect = docker.errors.NotFound("not found")
        executor = LocalExecutor()
        cancelation_info = {
            "simulation_method": method_config["simulation_method"],
            "simulation_id": method_config["simulation_id"],
        }
        # If this raises, pytest will report the exception directly — no need for try/except
        executor.cancel(cancelation_info)