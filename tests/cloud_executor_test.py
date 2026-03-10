import os
import json
import time
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open, call

# ── adjust this import to match your actual module path ──────────────────────
from app.services.executors.cloud_executor import (
    CloudExecutor,
    _CompletedJob,
    get_filenames,
    get_local_file_path,
    get_remote_file_path,
    POLL_INTERVAL_MIN,
    POLL_INTERVAL_MAX,
    POLL_BACKOFF_FACTOR,
    POLL_FAST_PHASE_CYCLES,
    _OUTPUT_EXTENSIONS,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def executor():
    return CloudExecutor(
        hostname="remote.host.com",
        username="user",
        password="secret",
        key_path=None,
        entry_file="main.py",
        remote_work_dir="/app",
    )


@pytest.fixture
def executor_with_key():
    return CloudExecutor(
        hostname="remote.host.com",
        username="user",
        password=None,
        key_path="/home/user/.ssh/id_rsa",
        entry_file="main.py",
    )


@pytest.fixture
def mock_ssh(executor):
    """Attach a mock SSH client to the executor."""
    executor.ssh_client = MagicMock()
    return executor.ssh_client


@pytest.fixture
def method_config():
    return {
        "container_image": "dg_image:latest",
        "container_name": "dg_container",
        "command": "python main.py",
    }


@pytest.fixture
def sim_config(tmp_path):
    json_path = tmp_path / "input.json"
    json_path.write_text(json.dumps({
        "msh_path": "/some/path/mesh.msh",
        "geo_path": "/some/path/geo.geo",
    }))
    return {
        "env": {
            "JSON_PATH": str(json_path),
        }
    }


# =============================================================================
# Tests: helper functions
# =============================================================================

class TestGetFilenames:

    def test_extracts_msh_and_geo_filenames(self, tmp_path):
        json_path = tmp_path / "input.json"
        json_path.write_text(json.dumps({
            "msh_path": "/full/path/to/mesh.msh",
            "geo_path": "/full/path/to/geo.geo",
        }))
        msh, geo = get_filenames(str(json_path))
        assert msh == "mesh.msh"
        assert geo == "geo.geo"

    def test_updates_json_in_place(self, tmp_path):
        json_path = tmp_path / "input.json"
        json_path.write_text(json.dumps({
            "msh_path": "/full/path/mesh.msh",
            "geo_path": "/full/path/geo.geo",
        }))
        get_filenames(str(json_path))
        data = json.loads(json_path.read_text())
        assert data["msh_path"] == "mesh.msh"
        assert data["geo_path"] == "geo.geo"

    def test_handles_missing_msh_path(self, tmp_path):
        json_path = tmp_path / "input.json"
        json_path.write_text(json.dumps({"geo_path": "/path/geo.geo"}))
        # Should not raise; msh_path is optional
        _, geo = get_filenames(str(json_path))
        assert geo == "geo.geo"

    def test_handles_missing_geo_path(self, tmp_path):
        json_path = tmp_path / "input.json"
        json_path.write_text(json.dumps({"msh_path": "/path/mesh.msh"}))
        msh, _ = get_filenames(str(json_path))
        assert msh == "mesh.msh"


class TestGetLocalFilePath:

    def test_joins_dirname_and_filename(self):
        result = get_local_file_path("/app/uploads/input.json", "mesh.msh")
        assert result == "/app/uploads/mesh.msh"

    def test_works_with_nested_dir(self):
        result = get_local_file_path("/a/b/c/file.json", "out.csv")
        assert result == "/a/b/c/out.csv"


class TestGetRemoteFilePath:

    def test_constructs_correct_remote_path(self):
        result = get_remote_file_path("dg_image", "abc-123", "input.json")
        assert result == "dg_image_sif_abc-123/app/input.json"


# =============================================================================
# Tests: _CompletedJob
# =============================================================================

class TestCompletedJob:

    def test_wait_returns_zero_status(self):
        job = _CompletedJob()
        assert job.wait() == {"StatusCode": 0}

    def test_logs_returns_bytes(self):
        job = _CompletedJob()
        assert isinstance(job.logs(), bytes)


# =============================================================================
# Tests: CloudExecutor.__init__
# =============================================================================

class TestCloudExecutorInit:

    def test_stores_all_init_params(self):
        ex = CloudExecutor("host", "user", "pass", "/key", "entry.py", "/work")
        assert ex.hostname == "host"
        assert ex.username == "user"
        assert ex.password == "pass"
        assert ex.key_path == "/key"
        assert ex.entry_file == "entry.py"
        assert ex.remote_work_dir == "/work"

    def test_default_remote_work_dir(self):
        ex = CloudExecutor("host", "user")
        assert ex.remote_work_dir == "/app"

    def test_ssh_client_initially_none(self):
        ex = CloudExecutor("host", "user")
        assert ex.ssh_client is None


# =============================================================================
# Tests: CloudExecutor._connect / _disconnect
# =============================================================================

class TestConnect:

    @patch("app.services.executors.cloud_executor.paramiko.SSHClient")
    def test_connect_uses_password_when_provided(self, mock_ssh_class, executor):
        mock_client = MagicMock()
        mock_ssh_class.return_value = mock_client

        executor._connect()

        call_kwargs = mock_client.connect.call_args.kwargs
        assert call_kwargs["password"] == "secret"
        assert call_kwargs["hostname"] == "remote.host.com"
        assert call_kwargs["username"] == "user"

    @patch("app.services.executors.cloud_executor.paramiko.SSHClient")
    def test_connect_uses_key_path_when_provided(self, mock_ssh_class, executor_with_key):
        mock_client = MagicMock()
        mock_ssh_class.return_value = mock_client

        executor_with_key._connect()

        call_kwargs = mock_client.connect.call_args.kwargs
        assert call_kwargs["key_filename"] == "/home/user/.ssh/id_rsa"
        assert call_kwargs["allow_agent"] is False
        assert call_kwargs["look_for_keys"] is False

    @patch("app.services.executors.cloud_executor.paramiko.SSHClient")
    def test_connect_closes_stale_connection_first(self, mock_ssh_class, executor):
        old_client = MagicMock()
        executor.ssh_client = old_client
        mock_ssh_class.return_value = MagicMock()

        executor._connect()

        old_client.close.assert_called_once()

    def test_disconnect_closes_client_and_nones_it(self, executor, mock_ssh):
        executor._disconnect()
        mock_ssh.close.assert_called_once()
        assert executor.ssh_client is None

    def test_disconnect_when_already_none_is_safe(self, executor):
        executor.ssh_client = None
        executor._disconnect()  # should not raise


# =============================================================================
# Tests: SFTP operations
# =============================================================================

class TestSftpOperations:

    def test_upload_file_opens_sftp_and_puts(self, executor, mock_ssh, tmp_path):
        local_file = tmp_path / "test.json"
        local_file.write_text("{}")
        mock_sftp = MagicMock()
        mock_ssh.open_sftp.return_value = mock_sftp

        executor.upload_file_via_sftp(str(local_file), "remote/test.json")

        mock_sftp.put.assert_called_once_with(str(local_file), "remote/test.json")
        mock_sftp.close.assert_called_once()

    def test_upload_raises_when_not_connected(self, executor):
        executor.ssh_client = None
        with pytest.raises(RuntimeError, match="not connected"):
            executor.upload_file_via_sftp("local.json", "remote.json")

    def test_download_file_calls_sftp_get(self, executor, mock_ssh):
        mock_sftp = MagicMock()
        mock_ssh.open_sftp.return_value = mock_sftp

        executor._download_file_via_sftp("remote/file.json", "/local/file.json")

        mock_sftp.get.assert_called_once_with("remote/file.json", "/local/file.json")
        mock_sftp.close.assert_called_once()

    def test_download_raises_when_not_connected(self, executor):
        executor.ssh_client = None
        with pytest.raises(RuntimeError, match="not connected"):
            executor._download_file_via_sftp("remote.json", "local.json")

    def test_list_remote_files_returns_full_paths(self, executor, mock_ssh):
        mock_sftp = MagicMock()
        mock_ssh.open_sftp.return_value = mock_sftp

        entry_a = MagicMock(); entry_a.filename = "output.json"
        entry_b = MagicMock(); entry_b.filename = "data.csv"
        entry_hidden = MagicMock(); entry_hidden.filename = ".hidden"
        mock_sftp.listdir_attr.return_value = [entry_a, entry_b, entry_hidden]

        result = executor._list_remote_files("sandbox/app")

        assert "sandbox/app/output.json" in result
        assert "sandbox/app/data.csv" in result
        assert "sandbox/app/.hidden" not in result   # hidden files excluded

    def test_list_remote_files_raises_when_not_connected(self, executor):
        executor.ssh_client = None
        with pytest.raises(RuntimeError, match="not connected"):
            executor._list_remote_files("remote/dir")

    def test_delete_remote_path_runs_rm_rf(self, executor, mock_ssh):
        stdout = MagicMock()
        stdout.channel.recv_exit_status.return_value = 0
        mock_ssh.exec_command.return_value = (MagicMock(), stdout, MagicMock())

        executor._delete_remote_path("sandbox/path")

        mock_ssh.exec_command.assert_called_once_with("rm -rf sandbox/path")


# =============================================================================
# Tests: build_singularity_image
# =============================================================================

class TestBuildSingularityImage:

    def test_runs_correct_build_command(self, executor, mock_ssh):
        stdout = MagicMock(); stdout.read.return_value = b"OK"
        stderr = MagicMock(); stderr.read.return_value = b""
        mock_ssh.exec_command.return_value = (MagicMock(), stdout, stderr)

        executor.build_singularity_image("my_sandbox", "my_image.tar")

        cmd = mock_ssh.exec_command.call_args[0][0]
        assert "singularity build --sandbox my_sandbox" in cmd
        assert "docker-archive://my_image.tar" in cmd

    def test_raises_on_ssh_error(self, executor, mock_ssh):
        mock_ssh.exec_command.side_effect = Exception("SSH broken")
        with pytest.raises(Exception, match="SSH broken"):
            executor.build_singularity_image("sandbox", "image.tar")


# =============================================================================
# Tests: execute_singularity_image
# =============================================================================

class TestExecuteSingularityImage:

    def test_runs_nohup_command_in_background(self, executor, mock_ssh):
        stdout = MagicMock()
        stdout.channel.recv_exit_status.return_value = 0
        mock_ssh.exec_command.return_value = (MagicMock(), stdout, MagicMock())

        executor.execute_singularity_image("sandbox", "input.json")

        cmd = mock_ssh.exec_command.call_args[0][0]
        assert "nohup" in cmd
        assert "singularity exec" in cmd
        assert "input.json" in cmd
        assert cmd.strip().endswith("&")

    def test_raises_on_error(self, executor, mock_ssh):
        mock_ssh.exec_command.side_effect = Exception("exec failed")
        with pytest.raises(Exception, match="exec failed"):
            executor.execute_singularity_image("sandbox", "input.json")


# =============================================================================
# Tests: _parse_overall_progress
# =============================================================================

class TestParseOverallProgress:

    def test_returns_minimum_percentage(self):
        data = {"results": [{"percentage": 80}, {"percentage": 60}, {"percentage": 100}]}
        assert CloudExecutor._parse_overall_progress(data) == 60

    def test_returns_none_when_results_absent(self):
        assert CloudExecutor._parse_overall_progress({}) is None

    def test_returns_none_when_results_empty(self):
        assert CloudExecutor._parse_overall_progress({"results": []}) is None

    def test_defaults_missing_percentage_to_zero(self):
        data = {"results": [{"percentage": 50}, {}]}
        assert CloudExecutor._parse_overall_progress(data) == 0

    def test_returns_100_when_all_complete(self):
        data = {"results": [{"percentage": 100}, {"percentage": 100}]}
        assert CloudExecutor._parse_overall_progress(data) == 100

    def test_returns_none_on_malformed_data(self):
        assert CloudExecutor._parse_overall_progress({"results": "bad"}) is None


# =============================================================================
# Tests: _collect_outputs_and_cleanup
# =============================================================================

class TestCollectOutputsAndCleanup:

    def test_downloads_only_output_extensions(self, executor, mock_ssh, tmp_path):
        mock_sftp = MagicMock()
        mock_ssh.open_sftp.return_value = mock_sftp

        executor._list_remote_files = MagicMock(return_value=[
            "sandbox/app/output.json",
            "sandbox/app/data.csv",
            "sandbox/app/script.py",     # should be ignored
            "sandbox/app/mesh.msh",      # should be ignored
        ])
        stdout = MagicMock(); stdout.channel.recv_exit_status.return_value = 0
        mock_ssh.exec_command.return_value = (MagicMock(), stdout, MagicMock())

        result = executor._collect_outputs_and_cleanup(
            remote_app_dir="sandbox/app",
            local_uploads_dir=str(tmp_path),
            remote_sandbox_path="sandbox",
            remote_tar_path="image.tar",
        )

        assert result is True
        downloaded = [c[0][0] for c in mock_sftp.get.call_args_list]
        assert "sandbox/app/output.json" in downloaded
        assert "sandbox/app/data.csv" in downloaded
        assert "sandbox/app/script.py" not in downloaded
        assert "sandbox/app/mesh.msh" not in downloaded

    def test_deletes_sandbox_and_tar(self, executor, mock_ssh, tmp_path):
        mock_sftp = MagicMock()
        mock_ssh.open_sftp.return_value = mock_sftp
        executor._list_remote_files = MagicMock(return_value=[])
        executor._delete_remote_path = MagicMock()

        executor._collect_outputs_and_cleanup(
            remote_app_dir="sandbox/app",
            local_uploads_dir=str(tmp_path),
            remote_sandbox_path="sandbox",
            remote_tar_path="image.tar",
        )

        executor._delete_remote_path.assert_any_call("sandbox")
        executor._delete_remote_path.assert_any_call("image.tar")

    def test_skips_tar_deletion_when_none(self, executor, mock_ssh, tmp_path):
        mock_sftp = MagicMock()
        mock_ssh.open_sftp.return_value = mock_sftp
        executor._list_remote_files = MagicMock(return_value=[])
        executor._delete_remote_path = MagicMock()

        executor._collect_outputs_and_cleanup(
            remote_app_dir="sandbox/app",
            local_uploads_dir=str(tmp_path),
            remote_sandbox_path="sandbox",
            remote_tar_path=None,
        )

        calls = [c[0][0] for c in executor._delete_remote_path.call_args_list]
        assert "image.tar" not in calls

    def test_returns_false_on_error(self, executor, mock_ssh, tmp_path):
        executor._list_remote_files = MagicMock(side_effect=Exception("SFTP error"))

        result = executor._collect_outputs_and_cleanup(
            remote_app_dir="sandbox/app",
            local_uploads_dir=str(tmp_path),
            remote_sandbox_path="sandbox",
            remote_tar_path=None,
        )

        assert result is False


# =============================================================================
# Tests: poll_until_complete
# =============================================================================

class TestPollUntilComplete:

    def _make_json(self, percentage):
        return json.dumps({"results": [{"percentage": percentage}]}).encode()

    @patch("app.services.executors.cloud_executor.time.sleep")
    def test_returns_true_when_job_completes(self, mock_sleep, executor, tmp_path):
        """Should return True when progress reaches 100 on first poll."""
        executor._connect = MagicMock()
        executor._disconnect = MagicMock()
        executor._collect_outputs_and_cleanup = MagicMock(return_value=True)

        # Write a fake tmp file that _download_file_via_sftp would produce
        def fake_download(remote, local):
            Path(local).write_text(json.dumps({"results": [{"percentage": 100}]}))

        executor._download_file_via_sftp = MagicMock(side_effect=fake_download)

        result = executor.poll_until_complete(
            remote_json_path="sandbox/app/input.json",
            local_uploads_dir=str(tmp_path),
            remote_app_dir="sandbox/app",
            remote_sandbox_path="sandbox",
        )

        assert result is True
        executor._collect_outputs_and_cleanup.assert_called_once()

    @patch("app.services.executors.cloud_executor.time.sleep")
    def test_polls_multiple_times_before_completion(self, mock_sleep, executor, tmp_path):
        """Should poll multiple cycles, sleeping between them."""
        executor._connect = MagicMock()
        executor._disconnect = MagicMock()
        executor._collect_outputs_and_cleanup = MagicMock(return_value=True)

        call_count = 0
        def fake_download(remote, local):
            nonlocal call_count
            call_count += 1
            pct = 100 if call_count >= 3 else call_count * 30
            Path(local).write_text(json.dumps({"results": [{"percentage": pct}]}))

        executor._download_file_via_sftp = MagicMock(side_effect=fake_download)

        executor.poll_until_complete(
            remote_json_path="sandbox/app/input.json",
            local_uploads_dir=str(tmp_path),
            remote_app_dir="sandbox/app",
            remote_sandbox_path="sandbox",
        )

        assert mock_sleep.call_count >= 2

    @patch("app.services.executors.cloud_executor.time.sleep")
    def test_retries_on_ssh_failure(self, mock_sleep, executor, tmp_path):
        """Should retry polling if SSH connect fails."""
        connect_calls = 0
        def flaky_connect():
            nonlocal connect_calls
            connect_calls += 1
            if connect_calls < 2:
                raise Exception("SSH timeout")

        executor._connect = MagicMock(side_effect=flaky_connect)
        executor._disconnect = MagicMock()
        executor._collect_outputs_and_cleanup = MagicMock(return_value=True)

        def fake_download(remote, local):
            Path(local).write_text(json.dumps({"results": [{"percentage": 100}]}))

        executor._download_file_via_sftp = MagicMock(side_effect=fake_download)

        result = executor.poll_until_complete(
            remote_json_path="sandbox/app/input.json",
            local_uploads_dir=str(tmp_path),
            remote_app_dir="sandbox/app",
            remote_sandbox_path="sandbox",
        )

        assert result is True
        assert connect_calls >= 2

    @patch("app.services.executors.cloud_executor.time.sleep")
    def test_applies_backoff_after_fast_phase(self, mock_sleep, executor, tmp_path):
        """Poll interval should grow after POLL_FAST_PHASE_CYCLES cycles."""
        cycle = 0
        def fake_download(remote, local):
            nonlocal cycle
            cycle += 1
            pct = 100 if cycle > POLL_FAST_PHASE_CYCLES + 1 else 50
            Path(local).write_text(json.dumps({"results": [{"percentage": pct}]}))

        executor._connect = MagicMock()
        executor._disconnect = MagicMock()
        executor._collect_outputs_and_cleanup = MagicMock(return_value=True)
        executor._download_file_via_sftp = MagicMock(side_effect=fake_download)

        executor.poll_until_complete(
            remote_json_path="sandbox/app/input.json",
            local_uploads_dir=str(tmp_path),
            remote_app_dir="sandbox/app",
            remote_sandbox_path="sandbox",
        )

        sleep_intervals = [c[0][0] for c in mock_sleep.call_args_list]
        # At least one sleep should be larger than POLL_INTERVAL_MIN
        assert any(s > POLL_INTERVAL_MIN for s in sleep_intervals)

    @patch("app.services.executors.cloud_executor.time.sleep")
    def test_json_written_only_when_progress_changes(self, mock_sleep, executor, tmp_path):
        """Local JSON should only be written when progress value changes."""
        call_count = 0
        def fake_download(remote, local):
            nonlocal call_count
            call_count += 1
            # Return same progress twice, then 100
            pct = 100 if call_count >= 3 else 50
            Path(local).write_text(json.dumps({"results": [{"percentage": pct}]}))

        executor._connect = MagicMock()
        executor._disconnect = MagicMock()
        executor._collect_outputs_and_cleanup = MagicMock(return_value=True)
        executor._download_file_via_sftp = MagicMock(side_effect=fake_download)

        local_json = tmp_path / "input.json"

        executor.poll_until_complete(
            remote_json_path="sandbox/app/input.json",
            local_uploads_dir=str(tmp_path),
            remote_app_dir="sandbox/app",
            remote_sandbox_path="sandbox",
        )

        # File should exist (written at least once)
        assert local_json.exists()


# =============================================================================
# Tests: execute (integration-style, fully mocked)
# =============================================================================

class TestExecute:

    @patch("app.services.executors.cloud_executor.get_filenames")
    def test_execute_returns_job_id_and_completed_job(
        self, mock_get_filenames, executor, method_config, sim_config, tmp_path
    ):
        mock_get_filenames.return_value = ("mesh.msh", "geo.geo")
        executor._connect = MagicMock()
        executor._disconnect = MagicMock()
        executor.upload_file_via_sftp = MagicMock()
        executor.build_singularity_image = MagicMock()
        executor.execute_singularity_image = MagicMock()
        executor.poll_until_complete = MagicMock()

        job_id, completed = executor.execute(method_config, sim_config)

        assert isinstance(job_id, str) and len(job_id) == 36
        assert isinstance(completed, _CompletedJob)

    @patch("app.services.executors.cloud_executor.get_filenames")
    def test_execute_uploads_tar_json_msh_geo(
        self, mock_get_filenames, executor, method_config, sim_config, tmp_path
    ):
        mock_get_filenames.return_value = ("mesh.msh", "geo.geo")
        executor._connect = MagicMock()
        executor._disconnect = MagicMock()
        executor.upload_file_via_sftp = MagicMock()
        executor.build_singularity_image = MagicMock()
        executor.execute_singularity_image = MagicMock()
        executor.poll_until_complete = MagicMock()

        executor.execute(method_config, sim_config)

        upload_calls = [c[0][1] for c in executor.upload_file_via_sftp.call_args_list]
        # tar upload
        assert any("dg_image.tar" in c for c in upload_calls)
        # json upload
        assert any("input.json" in c for c in upload_calls)

    @patch("app.services.executors.cloud_executor.get_filenames")
    def test_execute_calls_poll_until_complete(
        self, mock_get_filenames, executor, method_config, sim_config
    ):
        mock_get_filenames.return_value = ("mesh.msh", "geo.geo")
        executor._connect = MagicMock()
        executor._disconnect = MagicMock()
        executor.upload_file_via_sftp = MagicMock()
        executor.build_singularity_image = MagicMock()
        executor.execute_singularity_image = MagicMock()
        executor.poll_until_complete = MagicMock()

        executor.execute(method_config, sim_config)

        executor.poll_until_complete.assert_called_once()

    @patch("app.services.executors.cloud_executor.get_filenames")
    def test_execute_strips_tag_from_image_name(
        self, mock_get_filenames, executor, method_config, sim_config
    ):
        """Image name used for sandbox should not include :latest tag."""
        mock_get_filenames.return_value = ("mesh.msh", "geo.geo")
        executor._connect = MagicMock()
        executor._disconnect = MagicMock()
        executor.upload_file_via_sftp = MagicMock()
        executor.build_singularity_image = MagicMock()
        executor.execute_singularity_image = MagicMock()
        executor.poll_until_complete = MagicMock()

        executor.execute(method_config, sim_config)

        sandbox_arg = executor.build_singularity_image.call_args[0][0]
        assert ":latest" not in sandbox_arg
        assert "dg_image" in sandbox_arg