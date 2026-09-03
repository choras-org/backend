import pytest
from unittest.mock import MagicMock, patch

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
        "simulation_method": "MySim",
        "simulation_id": 123,
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
    def test_returns_container(self, mock_resolve, mock_docker_client, method_config, sim_config):
        """execute() should return a container object."""
        mock_resolve.return_value = "/host/uploads"
        fake_container = MagicMock()
        mock_docker_client.containers.run.return_value = fake_container

        executor = LocalExecutor()
        container = executor.execute(method_config, sim_config)

        assert container is fake_container

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
    def test_uses_generated_container_name(
        self, mock_resolve, mock_docker_client, method_config, sim_config
    ):
        """execute() should generate container name from method_config."""
        mock_resolve.return_value = "/host/uploads"
        mock_docker_client.containers.run.return_value = MagicMock()

        executor = LocalExecutor()
        executor.execute(method_config, sim_config)

        call_kwargs = mock_docker_client.containers.run.call_args.kwargs
        assert call_kwargs["name"] == "choras-MySim-simulation-123"

    @patch("app.services.executors.local_executor.threading.Thread")
    @patch("app.services.executors.local_executor.get_host_path_for_container_path")
    def test_starts_log_streaming_thread(
        self, mock_resolve, mock_thread_class, mock_docker_client, method_config, sim_config
    ):
        """execute() should start a daemon thread to stream container logs."""
        mock_resolve.return_value = "/host/uploads"
        fake_container = MagicMock()
        mock_docker_client.containers.run.return_value = fake_container
        mock_thread_instance = MagicMock()
        mock_thread_class.return_value = mock_thread_instance

        executor = LocalExecutor()
        executor.execute(method_config, sim_config)

        # Verify Thread was created with correct parameters
        mock_thread_class.assert_called_once()
        call_kwargs = mock_thread_class.call_args.kwargs
        assert call_kwargs["daemon"] is True
        assert "local-exec-logs-choras-MySim-simulation-123" in call_kwargs["name"]
        assert callable(call_kwargs["target"])

        # Verify thread.start() was called
        mock_thread_instance.start.assert_called_once()

    @patch("app.services.executors.local_executor.threading.Thread")
    @patch("app.services.executors.local_executor.get_host_path_for_container_path")
    def test_log_streaming_function_logs_container_output(
        self, mock_resolve, mock_thread_class, mock_docker_client, method_config, sim_config
    ):
        """The log streaming function should call container.logs() and log each line."""
        mock_resolve.return_value = "/host/uploads"
        fake_container = MagicMock()
        # Simulate container.logs() returning some log lines
        fake_container.logs.return_value = [
            b"Starting simulation...\n",
            b"Processing step 1\n",
            b"Simulation complete\n",
        ]
        mock_docker_client.containers.run.return_value = fake_container

        # Capture the thread target function
        captured_target = None
        def capture_target(*args, **kwargs):
            nonlocal captured_target
            captured_target = kwargs["target"]
            return MagicMock()
        mock_thread_class.side_effect = capture_target

        executor = LocalExecutor()

        with patch("app.services.executors.local_executor.logger") as mock_logger:
            executor.execute(method_config, sim_config)
            mock_logger.info.reset_mock()  # ignore any logger.info calls from execute() itself

            # Execute the captured thread target function
            assert captured_target is not None
            captured_target()

            # Verify container.logs() was called with correct parameters
            fake_container.logs.assert_called_once_with(stream=True, follow=True)

            # Verify logger.info was called for each log line with the correct prefix
            assert mock_logger.info.call_count == 3
            calls = mock_logger.info.call_args_list
            assert "[LocalExecutor - SimulationMethod: MySim]" in calls[0][0][0]
            assert "Starting simulation..." in calls[0][0][0]
            assert "Processing step 1" in calls[1][0][0]
            assert "Simulation complete" in calls[2][0][0]

    @patch("app.services.executors.local_executor.threading.Thread")
    @patch("app.services.executors.local_executor.get_host_path_for_container_path")
    def test_log_streaming_handles_exceptions_gracefully(
        self, mock_resolve, mock_thread_class, mock_docker_client, method_config, sim_config
    ):
        """The log streaming function should catch and log exceptions without crashing."""
        mock_resolve.return_value = "/host/uploads"
        fake_container = MagicMock()
        # Simulate container.logs() raising an exception
        fake_container.logs.side_effect = Exception("Connection lost")
        mock_docker_client.containers.run.return_value = fake_container

        # Capture the thread target function
        captured_target = None
        def capture_target(*args, **kwargs):
            nonlocal captured_target
            captured_target = kwargs["target"]
            return MagicMock()
        mock_thread_class.side_effect = capture_target

        executor = LocalExecutor()

        with patch("app.services.executors.local_executor.logger") as mock_logger:
            executor.execute(method_config, sim_config)

            # Execute the captured thread target function - should not raise
            assert captured_target is not None
            captured_target()  # Should handle exception internally

            # Verify logger.exception was called
            mock_logger.exception.assert_called_once()
            exception_msg = mock_logger.exception.call_args[0][0]
            assert "Failed to stream container logs" in exception_msg
            assert "[LocalExecutor - SimulationMethod: MySim]" in exception_msg

    @patch("app.services.executors.local_executor.threading.Thread")
    @patch("app.services.executors.local_executor.get_host_path_for_container_path")
    def test_log_streaming_skips_empty_lines(
        self, mock_resolve, mock_thread_class, mock_docker_client, method_config, sim_config
    ):
        """The log streaming function should skip empty log lines."""
        mock_resolve.return_value = "/host/uploads"
        fake_container = MagicMock()
        # Simulate container.logs() returning lines with empty ones
        fake_container.logs.return_value = [
            b"Line 1\n",
            b"\n",  # Empty line
            b"\r\n",  # Just newline
            b"Line 2\n",
        ]
        mock_docker_client.containers.run.return_value = fake_container

        # Capture the thread target function
        captured_target = None
        def capture_target(*args, **kwargs):
            nonlocal captured_target
            captured_target = kwargs["target"]
            return MagicMock()
        mock_thread_class.side_effect = capture_target

        executor = LocalExecutor()

        with patch("app.services.executors.local_executor.logger") as mock_logger:
            executor.execute(method_config, sim_config)
            mock_logger.info.reset_mock()  # ignore any logger.info calls from execute() itself

            # Execute the captured thread target function
            assert captured_target is not None
            captured_target()

            # Verify only non-empty lines were logged
            assert mock_logger.info.call_count == 2
            calls = mock_logger.info.call_args_list
            assert "Line 1" in calls[0][0][0]
            assert "Line 2" in calls[1][0][0]
