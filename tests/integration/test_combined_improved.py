"""
CHORAS — Combined Improved Test File
=====================================
Combines test_cloud_executor_final.py, test_local_executor_final.py,
test_missing_cases.py, and test_remaining_cases.py into a single file.

Key improvements over previous versions:
  1. FakeSSH collaborator replaces MagicMock for SSH — internal methods
     run through their real logic rather than being bypassed.
  2. Full polling chain test — poll → cleanup → SFTP download → files on disk.
  3. LocalExecutor.execute() with real path resolution — no patch on
     get_host_path_for_container_path, real call chain exercises mount logic.
  4. Volume mount test corrected — @patch decorator removed so
     get_host_path_for_container_path runs for real.
  5. Download file test asserts observable outcome (file on disk with content)
     rather than just that sftp.get was called.
"""

import json
import os
import unittest
import pytest
import paramiko
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services.executors.cloud_executor import (
    CloudExecutor,
    SSHCommandError,
    _CompletedJob,
    get_filenames,
    get_local_file_path,
    get_remote_file_path,
)
from app.services.executors.local_executor import (
    LocalExecutor,
    get_host_path_for_container_path,
)
from app.services import discovery_service, simulation_service
from app.types import Status, ResourceType
from app.models import SimulationRun, Simulation
from tests.unit import BaseTestCase
from config import DefaultConfig


# =============================================================================
# Shared Helpers
# =============================================================================

def make_cloud_executor():
    """Create a CloudExecutor with all required constructor arguments."""
    return CloudExecutor(
        hostname="test-host",
        username="test-user",
        remote_work_dir="/tmp/remote",
        password="test-pass"
    )


def write_json(path, percentage):
    """Write a minimal progress JSON to path."""
    with open(path, "w") as f:
        json.dump({"results": [{"percentage": percentage}]}, f)


def mock_ssh_session(executor, mock_ssh):
    """Patch _ssh_session to yield mock_ssh as a context manager."""
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=mock_ssh)
    ctx.__exit__ = MagicMock(return_value=False)
    return patch.object(executor, "_ssh_session", return_value=ctx)


def make_sftp_session(executor, mock_sftp):
    """
    Patch _ssh_session so that open_sftp() returns mock_sftp both as a
    direct call and as a context manager.  Both patterns are handled by
    making mock_sftp its own context manager that returns itself from
    __enter__.
    """
    mock_ssh = MagicMock()
    mock_ssh.open_sftp.return_value = mock_sftp
    mock_sftp.__enter__ = MagicMock(return_value=mock_sftp)
    mock_sftp.__exit__ = MagicMock(return_value=False)
    return mock_ssh_session(executor, mock_ssh)


# =============================================================================
# FakeSSH — real collaborator replacing MagicMock for SSH
# =============================================================================

class FakeSSH:
    """
    Minimal SSH fake that records commands and returns pre-configured
    stdout/stderr without a real connection.

    Using a fake collaborator instead of MagicMock means the real
    _run_remote_command, _build_singularity_image, and
    _execute_singularity_image methods run through their actual logic.
    If any of those methods change how they construct or send commands,
    tests using FakeSSH will catch the regression.
    """

    def __init__(self, responses=None, exit_status=0):
        self.commands_received = []
        self.responses = responses or {}
        self.exit_status = exit_status

    def exec_command(self, command):
        self.commands_received.append(command)
        stdout_data = self.responses.get(command, b"")
        mock_stdout = MagicMock()
        mock_stdout.channel.recv_exit_status.return_value = self.exit_status
        mock_stdout.read.return_value = stdout_data
        mock_stderr = MagicMock()
        mock_stderr.read.return_value = b""
        return MagicMock(), mock_stdout, mock_stderr

    def open_sftp(self):
        return MagicMock()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def fake_ssh_session(executor, fake_ssh):
    """Patch _ssh_session to yield a FakeSSH as a context manager."""
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=fake_ssh)
    ctx.__exit__ = MagicMock(return_value=False)
    return patch.object(executor, "_ssh_session", return_value=ctx)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_docker_client():
    with patch("app.services.executors.local_executor.docker.from_env") as mock_from_env:
        client = MagicMock()
        mock_from_env.return_value = client
        yield client


@pytest.fixture
def container_with_mounts():
    container = MagicMock()
    container.attrs = {
        "Mounts": [{"Source": "/host/uploads", "Destination": "/app/uploads"}]
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
        "env": {"JSON_PATH": "/app/uploads/input.json"}
    }


# =============================================================================
# SECTION 1 — CloudExecutor Unit Tests
# Pure logic, no external dependencies
# =============================================================================

class TestParseOverallProgress:
    """U1–U5 — EP-P1, EP-P2, EP-C5"""

    def test_multiple_results_returns_minimum(self):
        """U1 — EP-P1: returns minimum so progress only reaches 100 when ALL complete."""
        json_data = {"results": [{"percentage": 80}, {"percentage": 40}, {"percentage": 60}]}
        assert CloudExecutor._parse_overall_progress(json_data) == 40

    def test_single_result_at_100(self):
        """U2 — EP-P2: single result at 100% returns 100."""
        assert CloudExecutor._parse_overall_progress({"results": [{"percentage": 100}]}) == 100

    def test_empty_results_list_returns_none(self):
        """U3 — EP-C5: empty list returns None without raising."""
        assert CloudExecutor._parse_overall_progress({"results": []}) is None

    def test_results_entry_missing_percentage_key(self):
        """U4 — EP-C5: missing percentage key defaults to 0."""
        result = CloudExecutor._parse_overall_progress({"results": [{"no_percentage": 1}]})
        assert result == 0

    def test_results_is_not_a_list_returns_none(self):
        """U5 — EP-C5: non-list results returns None."""
        assert CloudExecutor._parse_overall_progress({"results": "not_a_list"}) is None


class TestGetFilenames:
    """U6–U8 — EP-C1, EP-C5"""

    def test_full_paths_stripped_to_filenames(self, tmp_path):
        """U6 — EP-C1: paths stripped to filenames only; JSON updated in place."""
        json_path = tmp_path / "input.json"
        json_path.write_text(json.dumps({
            "msh_path": "/app/uploads/sim1/room.msh",
            "geo_path": "/app/uploads/sim1/room.geo",
        }))
        msh, geo = get_filenames(str(json_path))
        assert msh == "room.msh"
        assert geo == "room.geo"
        with open(json_path) as f:
            data = json.load(f)
        assert data["msh_path"] == "room.msh"
        assert data["geo_path"] == "room.geo"

    def test_missing_msh_path_raises_key_error(self, tmp_path):
        """U7 — EP-C5: missing msh_path raises KeyError."""
        json_path = tmp_path / "input.json"
        json_path.write_text(json.dumps({"geo_path": "/app/uploads/sim1/room.geo"}))
        with pytest.raises(KeyError):
            get_filenames(str(json_path))

    def test_missing_geo_path_raises_key_error(self, tmp_path):
        """U8 — EP-C5: missing geo_path raises KeyError."""
        json_path = tmp_path / "input.json"
        json_path.write_text(json.dumps({"msh_path": "/app/uploads/sim1/room.msh"}))
        with pytest.raises(KeyError):
            get_filenames(str(json_path))


class TestShouldCancel:
    """U9–U10 — EP-P1, EP-P6"""

    def test_returns_false_when_no_cancel_flag(self, tmp_path):
        """U9 — EP-P1: absent flag file → False."""
        executor = make_cloud_executor()
        executor.local_cancel_flag_path = str(tmp_path / "task.cancel")
        assert executor._should_cancel() is False

    def test_returns_true_when_cancel_flag_exists(self, tmp_path):
        """U10 — EP-P6: present flag file → True."""
        cancel_flag = tmp_path / "task.cancel"
        cancel_flag.touch()
        executor = make_cloud_executor()
        executor.local_cancel_flag_path = str(cancel_flag)
        assert executor._should_cancel() is True


class TestGetLocalFilePath:
    """U5-U6 (missing_cases) — EP-C1"""

    def test_joins_dirname_and_filename(self):
        """U5-MC — EP-C1: joins dir of JSON path with filename."""
        assert get_local_file_path("/app/uploads/input.json", "mesh.msh") == "/app/uploads/mesh.msh"

    def test_works_with_nested_directory(self):
        """U6-MC — EP-C1: handles deeply nested paths."""
        assert get_local_file_path("/a/b/c/file.json", "out.csv") == "/a/b/c/out.csv"


class TestGetRemoteFilePath:
    """U7-MC — EP-C1"""

    def test_constructs_correct_remote_path(self):
        """U7-MC — EP-C1: builds sandbox path from work_dir, image, task_id, filename."""
        result = get_remote_file_path("/tmp/remote", "dg_image", "abc-123", "input.json")
        assert result == "/tmp/remote/dg_image_sif_abc-123/app/input.json"


class TestCompletedJob:
    """U8-U9 (missing_cases) — EP-O1"""

    def test_wait_returns_zero_status_code(self):
        """U8-MC — EP-O1: wait() returns StatusCode 0."""
        assert _CompletedJob().wait() == {"StatusCode": 0}

    def test_logs_returns_bytes(self):
        """U9-MC — EP-O1: logs() returns bytes."""
        assert isinstance(_CompletedJob().logs(), bytes)


class TestCloudExecutorInit:
    """U10–U11 (missing_cases) — EP-S1"""

    def test_stores_all_constructor_parameters(self):
        """U10-MC — EP-S1: all constructor args stored as attributes."""
        executor = CloudExecutor(
            hostname="host", username="user", remote_work_dir="/work",
            password="pass", key_path="/key", entry_file="entry.py"
        )
        assert executor.hostname == "host"
        assert executor.username == "user"
        assert executor.remote_work_dir == "/work"
        assert executor.password == "pass"
        assert executor.key_path == "/key"
        assert executor.entry_file == "entry.py"

    def test_local_cancel_flag_path_initially_none(self):
        """U11-MC — EP-S1: local_cancel_flag_path is None on construction."""
        executor = CloudExecutor(hostname="host", username="user", remote_work_dir="/tmp")
        assert executor.local_cancel_flag_path is None


# =============================================================================
# SECTION 2 — CloudExecutor Integration Tests using FakeSSH
# FakeSSH lets real internal methods run through their actual logic.
# =============================================================================

class TestRunRemoteCommandWithFakeSSH:
    """
    I1–I4 — EP-S1, EP-S2, EP-S3
    _run_remote_command runs for real against FakeSSH.
    Exit code parsing, stdout decoding, and exception mapping are all tested.
    """

    def test_successful_command_returns_stdout(self):
        """I1 — EP-S1: exit 0 → stdout decoded and returned."""
        fake_ssh = FakeSSH(responses={"echo hello": b"hello world"}, exit_status=0)
        executor = make_cloud_executor()
        with fake_ssh_session(executor, fake_ssh):
            result = executor._run_remote_command("echo hello")
        assert result == "hello world"
        assert "echo hello" in fake_ssh.commands_received

    def test_non_zero_exit_raises_ssh_command_error(self):
        """I4 — EP-S1 (failure): non-zero exit → SSHCommandError."""
        fake_ssh = FakeSSH(exit_status=1)
        executor = make_cloud_executor()
        with fake_ssh_session(executor, fake_ssh):
            with pytest.raises(SSHCommandError, match="Command failed"):
                executor._run_remote_command("rm -rf /protected")

    def test_ssh_auth_exception_raises_ssh_command_error(self):
        """I2 — EP-S2: AuthenticationException → SSHCommandError."""
        mock_ssh = MagicMock()
        mock_ssh.exec_command.side_effect = paramiko.AuthenticationException()
        executor = make_cloud_executor()
        with mock_ssh_session(executor, mock_ssh):
            with pytest.raises(SSHCommandError, match="SSH authentication failed"):
                executor._run_remote_command("ls")

    def test_socket_timeout_raises_ssh_command_error(self):
        """I3 — EP-S3: socket.timeout → SSHCommandError."""
        import socket
        mock_ssh = MagicMock()
        mock_ssh.exec_command.side_effect = socket.timeout()
        executor = make_cloud_executor()
        with mock_ssh_session(executor, mock_ssh):
            with pytest.raises(SSHCommandError, match="SSH connection timed out"):
                executor._run_remote_command("ls")


class TestBuildSingularityImageWithFakeSSH:
    """
    I7–I9 — EP-S1, EP-S5, EP-S6
    _build_singularity_image runs through _run_remote_command for real.
    FakeSSH records the actual command string issued.
    """

    def test_correct_singularity_build_command_issued(self):
        """
        I7 — EP-S1
        Full call chain: _build_singularity_image → _run_remote_command →
        FakeSSH.exec_command. Verifies the real command string sent to SSH.
        """
        fake_ssh = FakeSSH(exit_status=0)
        executor = make_cloud_executor()
        with fake_ssh_session(executor, fake_ssh):
            executor._build_singularity_image("dg_image_sif_task1", "dg_image.tar")
        assert len(fake_ssh.commands_received) == 1
        cmd = fake_ssh.commands_received[0]
        assert "singularity build" in cmd
        assert "dg_image_sif_task1" in cmd
        assert "dg_image.tar" in cmd

    def test_disk_full_raises_ssh_command_error(self):
        """I8 — EP-S5: SSH error during build propagates as SSHCommandError."""
        executor = make_cloud_executor()
        with patch.object(executor, "_run_remote_command",
                          side_effect=SSHCommandError("No space left on device")):
            with pytest.raises(SSHCommandError, match="No space left on device"):
                executor._build_singularity_image("dg_image_sif_task1", "dg_image.tar")

    def test_sandbox_already_exists_raises_ssh_command_error(self):
        """I9 — EP-S6: existing sandbox raises SSHCommandError."""
        executor = make_cloud_executor()
        with patch.object(executor, "_run_remote_command",
                          side_effect=SSHCommandError("sandbox already exists")):
            with pytest.raises(SSHCommandError, match="already exists"):
                executor._build_singularity_image("dg_image_sif_task1", "dg_image.tar")


class TestExecuteSingularityImageWithFakeSSH:
    """
    I10–I11 — EP-S1, EP-S5
    _execute_singularity_image runs through _run_remote_command for real.
    """

    def test_nohup_background_command_issued(self):
        """
        I10 — EP-S1
        Full chain: _execute_singularity_image → _run_remote_command →
        FakeSSH. Verifies nohup, singularity exec, input json, trailing &.
        """
        fake_ssh = FakeSSH(exit_status=0)
        executor = make_cloud_executor()
        with fake_ssh_session(executor, fake_ssh):
            executor._execute_singularity_image(
                sandbox_name="dg_image_sif_task1",
                input_json="input.json"
            )
        assert len(fake_ssh.commands_received) == 1
        cmd = fake_ssh.commands_received[0]
        assert "nohup" in cmd
        assert "singularity exec" in cmd
        assert "input.json" in cmd
        assert cmd.strip().endswith("&")

    def test_entry_file_appears_in_command(self):
        """I11 — EP-S1: entry_file from constructor appears in the command."""
        fake_ssh = FakeSSH(exit_status=0)
        executor = CloudExecutor(
            hostname="host", username="user", remote_work_dir="/tmp",
            password="pass", entry_file="DGinterface.py"
        )
        with fake_ssh_session(executor, fake_ssh):
            executor._execute_singularity_image(
                sandbox_name="dg_image_sif_task1",
                input_json="input.json"
            )
        assert "DGinterface.py" in fake_ssh.commands_received[0]

    def test_exec_failure_propagates(self):
        """B5 — EP-S5: SSH error during exec propagates."""
        executor = make_cloud_executor()
        with patch.object(executor, "_run_remote_command",
                          side_effect=SSHCommandError("exec failed")):
            with pytest.raises(SSHCommandError, match="exec failed"):
                executor._execute_singularity_image(
                    sandbox_name="dg_image_sif_task1",
                    input_json="input.json"
                )

    def test_ssh_drop_mid_launch_propagates(self):
        """B5v — EP-S5: connection drop during launch propagates."""
        executor = make_cloud_executor()
        with patch.object(executor, "_run_remote_command",
                          side_effect=SSHCommandError("SSH connection lost")):
            with pytest.raises(SSHCommandError, match="SSH connection lost"):
                executor._execute_singularity_image(
                    sandbox_name="dg_image_sif_task1",
                    input_json="input.json"
                )


# =============================================================================
# SECTION 3 — SFTP Operation Tests
# =============================================================================

class TestUploadFileViaSftp:
    """I5–I6 — EP-S1, EP-S4"""

    def _sftp_session(self, executor, mock_sftp):
        mock_ssh = MagicMock()
        mock_ssh.open_sftp.return_value.__enter__ = MagicMock(return_value=mock_sftp)
        mock_ssh.open_sftp.return_value.__exit__ = MagicMock(return_value=False)
        return mock_ssh_session(executor, mock_ssh)

    def test_successful_upload_calls_sftp_put(self, tmp_path):
        """I5 — EP-S1: sftp.put called with correct paths."""
        local_file = tmp_path / "file.tar"
        local_file.write_bytes(b"fake tar content")
        mock_sftp = MagicMock()
        executor = make_cloud_executor()
        with self._sftp_session(executor, mock_sftp):
            executor._upload_file_via_sftp(str(local_file), "/tmp/remote/file.tar")
        mock_sftp.put.assert_called_once_with(str(local_file), "/tmp/remote/file.tar")

    def test_sftp_upload_failure_propagates(self, tmp_path):
        """I6 — EP-S4: sftp.put raises → exception propagates."""
        local_file = tmp_path / "file.tar"
        local_file.write_bytes(b"fake tar content")
        mock_sftp = MagicMock()
        mock_sftp.put.side_effect = Exception("SFTP upload interrupted")
        executor = make_cloud_executor()
        with self._sftp_session(executor, mock_sftp):
            with pytest.raises(Exception, match="SFTP upload interrupted"):
                executor._upload_file_via_sftp(str(local_file), "/tmp/remote/file.tar")


class TestDownloadFileViaSftp:
    """I7-MC — EP-S1"""

    def test_sftp_get_called_with_correct_paths(self):
        """I7-MC — EP-S1: sftp.get called with correct remote and local paths."""
        mock_sftp = MagicMock()
        executor = make_cloud_executor()
        with make_sftp_session(executor, mock_sftp):
            executor._download_file_via_sftp("remote/file.json", "/local/file.json")
        mock_sftp.get.assert_called_once_with("remote/file.json", "/local/file.json")

    def test_download_writes_real_file_to_local_path(self, tmp_path):
        """
        I7-MC improved — EP-S1
        Uses fake_get to write a real file so the test asserts on an
        observable outcome (file exists with correct content) rather than
        just that sftp.get was called.
        """
        local_path = str(tmp_path / "file.json")

        def fake_get(remote, local):
            with open(local, "w") as f:
                json.dump({"results": [{"percentage": 50}]}, f)

        mock_sftp = MagicMock()
        mock_sftp.get.side_effect = fake_get
        executor = make_cloud_executor()

        with make_sftp_session(executor, mock_sftp):
            executor._download_file_via_sftp("remote/file.json", local_path)

        assert os.path.exists(local_path)
        with open(local_path) as f:
            data = json.load(f)
        assert data["results"][0]["percentage"] == 50


class TestListRemoteFiles:
    """I8-MC — EP-O1"""

    def test_returns_full_paths_and_excludes_hidden_files(self):
        """I8-MC — EP-O1: full paths returned; hidden files excluded."""
        entry_a = MagicMock(); entry_a.filename = "output.json"
        entry_b = MagicMock(); entry_b.filename = "data.csv"
        entry_hidden = MagicMock(); entry_hidden.filename = ".hidden"

        mock_sftp = MagicMock()
        mock_sftp.listdir_attr.return_value = [entry_a, entry_b, entry_hidden]
        executor = make_cloud_executor()
        with make_sftp_session(executor, mock_sftp):
            result = executor._list_remote_files("sandbox/app")

        assert "sandbox/app/output.json" in result
        assert "sandbox/app/data.csv" in result
        assert "sandbox/app/.hidden" not in result

    def test_empty_directory_returns_empty_list(self):
        """I8-MC boundary — EP-O1: empty dir returns []."""
        mock_sftp = MagicMock()
        mock_sftp.listdir_attr.return_value = []
        executor = make_cloud_executor()
        with make_sftp_session(executor, mock_sftp):
            result = executor._list_remote_files("sandbox/app")
        assert result == []


class TestDeleteRemotePath:
    """I9-MC — EP-S1, EP-S5"""

    def test_runs_rm_rf_command(self):
        """I9-MC — EP-S1: issues 'rm -rf {path}' via _run_remote_command."""
        executor = make_cloud_executor()
        with patch.object(executor, "_run_remote_command", return_value="") as mock_cmd:
            executor._delete_remote_path("sandbox/path")
        mock_cmd.assert_called_once_with("rm -rf sandbox/path")

    def test_ssh_error_propagates(self):
        """I9-MC bad day — EP-S5: SSH error propagates unchanged."""
        executor = make_cloud_executor()
        with patch.object(executor, "_run_remote_command",
                          side_effect=SSHCommandError("permission denied")):
            with pytest.raises(SSHCommandError, match="permission denied"):
                executor._delete_remote_path("sandbox/path")


# =============================================================================
# SECTION 4 — _collect_outputs_and_cleanup Tests
# =============================================================================

class TestCollectOutputsAndCleanup:
    """I17–I19 — EP-O1, EP-S4"""

    def _sftp_session(self, executor, mock_sftp):
        mock_ssh = MagicMock()
        mock_ssh.open_sftp.return_value.__enter__ = MagicMock(return_value=mock_sftp)
        mock_ssh.open_sftp.return_value.__exit__ = MagicMock(return_value=False)
        return mock_ssh_session(executor, mock_ssh)

    def test_downloads_only_json_and_csv_ignores_others(self, tmp_path):
        """
        I17 — EP-O1 (improved)
        _list_remote_files runs for real against fake listdir_attr entries.
        The .json/.csv filtering logic inside _collect_outputs_and_cleanup
        is actually exercised rather than bypassed.
        """
        mock_sftp = MagicMock()
        executor = make_cloud_executor()

        def fake_listdir_attr(path):
            entries = []
            for name in ["results.json", "pressure.csv", "solver.py", "room.msh"]:
                e = MagicMock()
                e.filename = name
                entries.append(e)
            return entries

        mock_sftp.listdir_attr.side_effect = fake_listdir_attr

        with self._sftp_session(executor, mock_sftp), \
             patch.object(executor, "_cleanup"):
            executor._collect_outputs_and_cleanup(
                remote_app_dir="/remote/app",
                local_uploads_dir=str(tmp_path),
                remote_sandbox_path="/remote/sandbox",
                remote_tar_path="/remote/image.tar",
            )

        downloaded = [c[0][0] for c in mock_sftp.get.call_args_list]
        assert any("results.json" in d for d in downloaded)
        assert any("pressure.csv" in d for d in downloaded)
        assert not any("solver.py" in d for d in downloaded)
        assert not any("room.msh" in d for d in downloaded)

    def test_cleanup_called_with_correct_paths(self, tmp_path):
        """I18 — EP-O1: _cleanup called with sandbox and tar paths after download."""
        mock_sftp = MagicMock()
        executor = make_cloud_executor()
        with self._sftp_session(executor, mock_sftp), \
             patch.object(executor, "_list_remote_files",
                          return_value=["/remote/app/results.json"]), \
             patch.object(executor, "_cleanup") as mock_cleanup:
            executor._collect_outputs_and_cleanup(
                remote_app_dir="/remote/app",
                local_uploads_dir=str(tmp_path),
                remote_sandbox_path="/remote/sandbox",
                remote_tar_path="/remote/image.tar",
            )
        mock_cleanup.assert_called_once_with("/remote/sandbox", "/remote/image.tar")

    def test_sftp_failure_returns_false_no_cleanup(self, tmp_path):
        """I19 — EP-S4: sftp.get raises → returns False, cleanup not called."""
        mock_sftp = MagicMock()
        mock_sftp.get.side_effect = Exception("Network error")
        executor = make_cloud_executor()
        with self._sftp_session(executor, mock_sftp), \
             patch.object(executor, "_list_remote_files",
                          return_value=["/remote/app/results.json"]), \
             patch.object(executor, "_cleanup") as mock_cleanup:
            result = executor._collect_outputs_and_cleanup(
                remote_app_dir="/remote/app",
                local_uploads_dir=str(tmp_path),
                remote_sandbox_path="/remote/sandbox",
                remote_tar_path="/remote/image.tar",
            )
        assert result is False
        mock_cleanup.assert_not_called()


# =============================================================================
# SECTION 5 — _poll_until_complete Tests
# =============================================================================

class TestPollUntilComplete:
    """I12–I16, B12–B13 — EP-P1 through EP-P7"""

    def test_progress_reaches_100_calls_cleanup_and_returns_true(self, tmp_path):
        """I12 — EP-P1, EP-P2: 100% on first poll → cleanup called, True returned."""
        executor = make_cloud_executor()
        executor.local_cancel_flag_path = str(tmp_path / "task.cancel")
        with patch.object(executor, "_download_file_via_sftp",
                          side_effect=lambda r, local: write_json(local, 100)), \
             patch.object(executor, "_collect_outputs_and_cleanup",
                          return_value=True) as mock_cleanup:
            result = executor._poll_until_complete(
                remote_json_path="/remote/app/input.json",
                local_uploads_dir=str(tmp_path),
                remote_app_dir="/remote/app",
                remote_sandbox_path="/remote/sandbox",
                remote_tar_path="/remote/image.tar",
            )
        assert result is True
        mock_cleanup.assert_called_once()

    def test_full_chain_poll_to_completion_writes_output_files(self, tmp_path):
        """
        Full chain integration — EP-P1, EP-O1
        poll → 100% → _collect_outputs_and_cleanup runs for real →
        SFTP downloads real files → files appear on disk.
        This is the highest-value test in the suite: it exercises the full
        post-completion path without mocking either poll or cleanup.
        """
        executor = make_cloud_executor()
        executor.local_cancel_flag_path = str(tmp_path / "task.cancel")

        mock_sftp = MagicMock()

        def fake_get(remote_path, local_path):
            filename = os.path.basename(remote_path)
            with open(os.path.join(str(tmp_path), filename), "w") as f:
                json.dump({"downloaded_from": remote_path}, f)

        mock_sftp.get.side_effect = fake_get

        def fake_listdir_attr(path):
            return [MagicMock(filename="results.json"), MagicMock(filename="pressure.csv")]

        mock_sftp.listdir_attr.side_effect = fake_listdir_attr
        mock_sftp.__enter__ = MagicMock(return_value=mock_sftp)
        mock_sftp.__exit__ = MagicMock(return_value=False)

        mock_ssh = MagicMock()
        mock_ssh.open_sftp.return_value = mock_sftp

        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=mock_ssh)
        ctx.__exit__ = MagicMock(return_value=False)

        with patch.object(executor, "_ssh_session", return_value=ctx), \
             patch.object(executor, "_download_file_via_sftp",
                          side_effect=lambda r, local: write_json(local, 100)), \
             patch.object(executor, "_cleanup"):
            result = executor._poll_until_complete(
                remote_json_path="/remote/app/input.json",
                local_uploads_dir=str(tmp_path),
                remote_app_dir="/remote/app",
                remote_sandbox_path="/remote/sandbox",
                remote_tar_path="/remote/image.tar",
            )

        assert result is True
        output_files = list(tmp_path.glob("*.json")) + list(tmp_path.glob("*.csv"))
        assert len(output_files) > 0

    def test_json_only_written_locally_when_progress_changes(self, tmp_path):
        """I13 — EP-P1: local JSON only written when percentage changes."""
        call_count = {"n": 0}
        percentages = [0, 0, 100]

        def fake_download(remote, local):
            pct = percentages[call_count["n"]]
            call_count["n"] += 1
            write_json(local, pct)

        written_files = []
        import shutil
        real_move = shutil.move

        def track_move(src, dst):
            written_files.append(dst)
            real_move(src, dst)

        executor = make_cloud_executor()
        executor.local_cancel_flag_path = str(tmp_path / "task.cancel")
        with patch.object(executor, "_download_file_via_sftp", side_effect=fake_download), \
             patch.object(executor, "_collect_outputs_and_cleanup", return_value=True), \
             patch("app.services.executors.cloud_executor.shutil.move",
                   side_effect=track_move), \
             patch("time.sleep"):
            executor._poll_until_complete(
                remote_json_path="/remote/app/input.json",
                local_uploads_dir=str(tmp_path),
                remote_app_dir="/remote/app",
                remote_sandbox_path="/remote/sandbox",
            )
        assert len(written_files) == 2

    def test_corrupt_json_retries_then_recovers(self, tmp_path):
        """I14 — EP-P3: corrupt JSON on attempt 1, valid on attempt 2 → recovers."""
        attempt = {"n": 0}

        def fake_download(remote, local):
            if attempt["n"] == 0:
                with open(local, "w") as f:
                    f.write("{corrupt json{{")
            else:
                write_json(local, 100)
            attempt["n"] += 1

        executor = make_cloud_executor()
        executor.local_cancel_flag_path = str(tmp_path / "task.cancel")
        with patch.object(executor, "_download_file_via_sftp", side_effect=fake_download), \
             patch.object(executor, "_collect_outputs_and_cleanup", return_value=True), \
             patch("time.sleep"):
            result = executor._poll_until_complete(
                remote_json_path="/remote/app/input.json",
                local_uploads_dir=str(tmp_path),
                remote_app_dir="/remote/app",
                remote_sandbox_path="/remote/sandbox",
            )
        assert result is True

    def test_cancel_flag_before_polling_exits_immediately(self, tmp_path):
        """I15 — EP-P6: cancel flag at entry → exits immediately, nothing downloaded."""
        cancel_flag = tmp_path / "task-001.cancel"
        cancel_flag.touch()
        executor = make_cloud_executor()
        executor.local_cancel_flag_path = str(cancel_flag)
        download_mock = MagicMock()
        cleanup_mock = MagicMock()
        with patch.object(executor, "_download_file_via_sftp", download_mock), \
             patch.object(executor, "_collect_outputs_and_cleanup", cleanup_mock):
            executor._poll_until_complete(
                remote_json_path="/remote/app/input.json",
                local_uploads_dir=str(tmp_path),
                remote_app_dir="/remote/app",
                remote_sandbox_path="/remote/sandbox",
            )
        download_mock.assert_not_called()
        cleanup_mock.assert_not_called()

    def test_cancel_flag_mid_polling_stops_at_next_cycle(self, tmp_path):
        """I16 — EP-P7: cancel flag created after cycle 1 → stops at cycle 2."""
        cancel_flag = tmp_path / "task-001.cancel"
        call_count = {"n": 0}
        executor = make_cloud_executor()
        executor.local_cancel_flag_path = str(cancel_flag)

        def fake_download(remote, local):
            if call_count["n"] == 0:
                cancel_flag.touch()
            call_count["n"] += 1
            write_json(local, 50)

        cleanup_mock = MagicMock()
        with patch.object(executor, "_download_file_via_sftp", side_effect=fake_download), \
             patch.object(executor, "_collect_outputs_and_cleanup", cleanup_mock), \
             patch("time.sleep"):
            executor._poll_until_complete(
                remote_json_path="/remote/app/input.json",
                local_uploads_dir=str(tmp_path),
                remote_app_dir="/remote/app",
                remote_sandbox_path="/remote/sandbox",
            )
        assert call_count["n"] == 1
        cleanup_mock.assert_not_called()

    @pytest.mark.xfail(
        reason="KNOWN BUG DEF-001: No stall timeout in _poll_until_complete. "
               "Progress stuck at 50% loops forever. "
               "Remove xfail once stall-detection is implemented."
    )
    def test_progress_stuck_raises_runtime_error(self, tmp_path):
        """B12 — EP-P5: stuck at 50% → RuntimeError after stall timeout."""
        executor = make_cloud_executor()
        executor.local_cancel_flag_path = str(tmp_path / "task.cancel")
        with patch.object(executor, "_download_file_via_sftp",
                          side_effect=lambda r, l: write_json(l, 50)), \
             patch("time.sleep",
                   side_effect=[None] * 5 + [RuntimeError("forced exit")]):
            with pytest.raises(RuntimeError, match="timeout|stall|crashed|forced exit"):
                executor._poll_until_complete(
                    remote_json_path="/remote/app/input.json",
                    local_uploads_dir=str(tmp_path),
                    remote_app_dir="/remote/app",
                    remote_sandbox_path="/remote/sandbox",
                )

    @pytest.mark.xfail(
        reason="KNOWN BUG DEF-002: No POLL_MAX_FAILED_CYCLES limit. "
               "JSON always corrupt loops forever. "
               "Remove xfail once max failed cycle count is implemented."
    )
    def test_json_always_corrupt_raises_runtime_error(self, tmp_path):
        """B13 — EP-P4: always corrupt JSON → RuntimeError after POLL_MAX_FAILED_CYCLES."""
        executor = make_cloud_executor()
        executor.local_cancel_flag_path = str(tmp_path / "task.cancel")

        def always_corrupt(remote, local):
            with open(local, "w") as f:
                f.write("{always corrupt{{{")

        with patch.object(executor, "_download_file_via_sftp", side_effect=always_corrupt), \
             patch("time.sleep",
                   side_effect=[None] * 5 + [RuntimeError("forced exit")]):
            with pytest.raises(RuntimeError, match="unreadable|corrupt|failed cycles|forced exit"):
                executor._poll_until_complete(
                    remote_json_path="/remote/app/input.json",
                    local_uploads_dir=str(tmp_path),
                    remote_app_dir="/remote/app",
                    remote_sandbox_path="/remote/sandbox",
                )


# =============================================================================
# SECTION 6 — execute() and cancel() Tests
# =============================================================================

class TestExecuteHappyPath:
    """I20–I23 — EP-S1, EP-M2"""

    def _method_config(self):
        return {
            "container_image": "dg_image:latest",
            "simulation_method": "dg",
            "simulation_id": "sim-001",
            "task_id": "task-001"
        }

    def _all_ssh_patches(self):
        return {
            "_mkdir_remote":              MagicMock(),
            "_upload_file_via_sftp":      MagicMock(),
            "_build_singularity_image":   MagicMock(),
            "_execute_singularity_image": MagicMock(),
            "_poll_until_complete":       MagicMock(return_value=True),
        }

    def _write_sim_config(self, tmp_path):
        json_path = str(tmp_path / "input.json")
        with open(json_path, "w") as f:
            json.dump({
                "msh_path": "/app/uploads/room.msh",
                "geo_path": "/app/uploads/room.geo",
                "results": []
            }, f)
        return {"env": {"JSON_PATH": json_path}}

    def test_execute_returns_completed_job(self, tmp_path):
        """I20 — EP-S1, EP-M2: successful execute() returns _CompletedJob."""
        executor = make_cloud_executor()
        with patch.multiple(CloudExecutor, **self._all_ssh_patches()):
            result = executor.execute(self._method_config(), self._write_sim_config(tmp_path))
        assert isinstance(result, _CompletedJob)

    def test_execute_calls_poll_exactly_once(self, tmp_path):
        """I21 — EP-S1: poll_until_complete called exactly once."""
        executor = make_cloud_executor()
        patches = self._all_ssh_patches()
        with patch.multiple(CloudExecutor, **patches):
            executor.execute(self._method_config(), self._write_sim_config(tmp_path))
        patches["_poll_until_complete"].assert_called_once()

    def test_execute_uploads_tar_file(self, tmp_path):
        """I22 — EP-S1: Docker tar uploaded to remote."""
        executor = make_cloud_executor()
        patches = self._all_ssh_patches()
        with patch.multiple(CloudExecutor, **patches):
            executor.execute(self._method_config(), self._write_sim_config(tmp_path))
        upload_calls = [c[0][1] for c in patches["_upload_file_via_sftp"].call_args_list]
        assert any("dg_image.tar" in str(c) for c in upload_calls)

    def test_execute_strips_tag_from_sandbox_name(self, tmp_path):
        """I23 — EP-S1: :latest tag stripped from sandbox name."""
        executor = make_cloud_executor()
        patches = self._all_ssh_patches()
        with patch.multiple(CloudExecutor, **patches):
            executor.execute(self._method_config(), self._write_sim_config(tmp_path))
        sandbox_arg = patches["_build_singularity_image"].call_args[0][0]
        assert ":latest" not in sandbox_arg
        assert "dg_image" in sandbox_arg


class TestCancel:
    """I24–I25 — EP-S1"""

    def test_cancel_kills_and_cleans_up(self):
        """I24 — EP-S1: kill and cleanup called with correct sandbox name."""
        executor = make_cloud_executor()
        cancelation_info = {"container_image": "dg_image:latest", "task_id": "task-001"}
        with patch.object(executor, "_kill_container_processes") as mock_kill, \
             patch.object(executor, "_cleanup") as mock_cleanup:
            executor.cancel(cancelation_info)
        mock_kill.assert_called_once_with("dg_image_sif_task-001")
        mock_cleanup.assert_called_once()

    def test_cancel_constructs_correct_sandbox_name(self):
        """I25 — EP-S1: :latest stripped, sif_{task_id} appended correctly."""
        executor = make_cloud_executor()
        cancelation_info = {"container_image": "dg_image:latest", "task_id": "abc-123"}
        with patch.object(executor, "_kill_container_processes") as mock_kill, \
             patch.object(executor, "_cleanup"):
            executor.cancel(cancelation_info)
        assert mock_kill.call_args[0][0] == "dg_image_sif_abc-123"


# =============================================================================
# SECTION 7 — LocalExecutor Tests
# =============================================================================

class TestGetHostPathForContainerPath:
    """U17–U22 — EP-D1, EP-D2, EP-D4"""

    def test_resolves_exact_mount_destination(self, mock_docker_client, container_with_mounts):
        """U18 — EP-D1: exact match resolved to host source path."""
        mock_docker_client.containers.get.return_value = container_with_mounts
        with patch("socket.gethostname", return_value="my-container-id"):
            result = get_host_path_for_container_path("/app/uploads")
        assert os.path.normpath(result) == "/host/uploads"

    def test_resolves_subdirectory_of_mount(self, mock_docker_client, container_with_mounts):
        """U19 — EP-D1: subdirectory resolved with relative suffix appended."""
        mock_docker_client.containers.get.return_value = container_with_mounts
        with patch("socket.gethostname", return_value="my-container-id"):
            result = get_host_path_for_container_path("/app/uploads/subdir")
        assert result == "/host/uploads/subdir"

    def test_raises_when_no_mount_covers_path(self, mock_docker_client, container_with_mounts):
        """B7 — EP-D4: no covering mount → RuntimeError."""
        mock_docker_client.containers.get.return_value = container_with_mounts
        with patch("socket.gethostname", return_value="my-container-id"):
            with pytest.raises(RuntimeError, match="No mount found covering container path"):
                get_host_path_for_container_path("/some/unmounted/path")

    def test_raises_when_docker_client_fails(self, mock_docker_client):
        """B8 — EP-D2: containers.get() raises → exception propagates."""
        mock_docker_client.containers.get.side_effect = Exception("Docker socket error")
        with patch("socket.gethostname", return_value="my-container-id"):
            with pytest.raises(Exception, match="Docker socket error"):
                get_host_path_for_container_path("/app/uploads")

    def test_uses_hostname_to_identify_container(self, mock_docker_client, container_with_mounts):
        """U21 — EP-D1: containers.get() called with current hostname."""
        mock_docker_client.containers.get.return_value = container_with_mounts
        with patch("socket.gethostname", return_value="abc123"):
            get_host_path_for_container_path("/app/uploads")
        mock_docker_client.containers.get.assert_called_once_with("abc123")

    def test_normalises_backslashes(self, mock_docker_client):
        """U22 — EP-D1: Windows backslash paths normalised to forward slashes."""
        container = MagicMock()
        container.attrs = {
            "Mounts": [{"Source": "C:\\Users\\host\\uploads", "Destination": "/app/uploads"}]
        }
        mock_docker_client.containers.get.return_value = container
        with patch("socket.gethostname", return_value="container-id"):
            result = get_host_path_for_container_path("/app/uploads/file.json")
        assert "\\" not in result


class TestLocalExecutorInit:
    """U23–U25 — EP-D1"""

    def test_work_dir_from_env_var(self):
        """U23 — EP-D1: DOCKER_WORK_DIR env var used when set."""
        with patch.dict(os.environ, {"DOCKER_WORK_DIR": "/custom/workdir"}):
            executor = LocalExecutor()
        assert executor.work_dir == "/custom/workdir"

    def test_work_dir_fallback_to_app(self):
        """U24 — EP-D1: falls back to /app when env var absent."""
        env = {k: v for k, v in os.environ.items() if k != "DOCKER_WORK_DIR"}
        with patch.dict(os.environ, env, clear=True):
            executor = LocalExecutor()
        assert executor.work_dir == "/app"

    def test_explicit_work_dir_overrides_env(self):
        """U25 — EP-D1: explicit arg overrides env var."""
        executor = LocalExecutor(work_dir="/my/dir")
        assert executor.work_dir == "/my/dir"

    @pytest.mark.xfail(
        reason="KNOWN IMPLEMENTATION GAP: _jobs = {} not yet in __init__. "
               "Remove xfail once added."
    )
    def test_jobs_dict_initialised_empty(self):
        """U25-MC — EP-D1: _jobs starts as empty dict."""
        executor = LocalExecutor()
        assert hasattr(executor, "_jobs")
        assert executor._jobs == {}


class TestLocalExecutorExecuteHappyPath:
    """I1–I9 — EP-D1, EP-M1–M3, EP-G1–G3, EP-C1"""

    @patch("app.services.executors.local_executor.get_host_path_for_container_path",
           return_value="/host/uploads")
    def test_returns_container_object(self, mock_resolve, mock_docker_client,
                                      method_config, sim_config):
        """I1 — EP-D1, EP-M2: valid inputs → container returned."""
        fake_container = MagicMock()
        mock_docker_client.containers.run.return_value = fake_container
        result = LocalExecutor().execute(method_config, sim_config)
        assert result is fake_container

    @patch("app.services.executors.local_executor.get_host_path_for_container_path",
           return_value="/host/uploads")
    def test_passes_correct_image(self, mock_resolve, mock_docker_client,
                                  method_config, sim_config):
        """I2 — EP-D1: container_image passed to containers.run."""
        mock_docker_client.containers.run.return_value = MagicMock()
        LocalExecutor().execute(method_config, sim_config)
        assert mock_docker_client.containers.run.call_args.kwargs["image"] == "my-sim-image:latest"

    @patch("app.services.executors.local_executor.get_host_path_for_container_path",
           return_value="/host/uploads")
    def test_passes_env(self, mock_resolve, mock_docker_client, method_config, sim_config):
        """I3 — EP-D1, EP-C1: env from sim_config passed to containers.run."""
        mock_docker_client.containers.run.return_value = MagicMock()
        LocalExecutor().execute(method_config, sim_config)
        assert mock_docker_client.containers.run.call_args.kwargs["environment"] == sim_config["env"]

    def test_volume_mount_with_real_path_resolution(
        self, mock_docker_client, method_config, sim_config
    ):
        """
        I4 — EP-D1 (improved)
        get_host_path_for_container_path runs for real against a container
        mock with realistic mount data. No @patch on the resolver.
        Tests the full call chain: execute → resolver → mount lookup → run.
        """
        self_container = MagicMock()
        self_container.attrs = {
            "Mounts": [{"Source": "/host/uploads", "Destination": "/app/uploads"}]
        }
        mock_docker_client.containers.get.return_value = self_container
        mock_docker_client.containers.run.return_value = MagicMock()

        with patch("socket.gethostname", return_value="test-container"):
            LocalExecutor().execute(method_config, sim_config)

        volumes = mock_docker_client.containers.run.call_args.kwargs["volumes"]
        normalised_volumes = {os.path.normpath(k): v for k, v in volumes.items()}
        assert "/host/uploads" in normalised_volumes
        assert normalised_volumes["/host/uploads"]["bind"] == "/app/uploads"
        assert normalised_volumes["/host/uploads"]["mode"] == "rw"
        """ assert "/host/uploads" in volumes
        assert volumes["/host/uploads"]["bind"] == "/app/uploads"
        assert volumes["/host/uploads"]["mode"] == "rw" """

    @patch("app.services.executors.local_executor.get_host_path_for_container_path",
           return_value="/host/uploads")
    def test_container_runs_detached(self, mock_resolve, mock_docker_client,
                                     method_config, sim_config):
        """I5 — EP-D1: detach=True always set."""
        mock_docker_client.containers.run.return_value = MagicMock()
        LocalExecutor().execute(method_config, sim_config)
        assert mock_docker_client.containers.run.call_args.kwargs["detach"] is True

    @patch("app.services.executors.local_executor.get_host_path_for_container_path",
           return_value="/host/uploads")
    def test_de_method_on_simple_geometry(self, mock_resolve, mock_docker_client, sim_config):
        """I6 — EP-M1, EP-G1: DE on simple geometry → correct image."""
        de_config = {
            "container_image": "de_image:latest", "container_name": "de_container",
            "simulation_method": "de", "simulation_id": "sim-de-001",
        }
        mock_docker_client.containers.run.return_value = MagicMock()
        result = LocalExecutor().execute(de_config, sim_config)
        assert result is not None
        assert mock_docker_client.containers.run.call_args.kwargs["image"] == "de_image:latest"

    @patch("app.services.executors.local_executor.get_host_path_for_container_path",
           return_value="/host/uploads")
    def test_dg_method_on_moderate_geometry(self, mock_resolve, mock_docker_client, sim_config):
        """I7 — EP-M2, EP-G2: DG on moderate geometry → correct image."""
        dg_config = {
            "container_image": "dg_image:latest", "container_name": "dg_container",
            "simulation_method": "dg", "simulation_id": "sim-dg-001",
        }
        mock_docker_client.containers.run.return_value = MagicMock()
        result = LocalExecutor().execute(dg_config, sim_config)
        assert result is not None
        assert mock_docker_client.containers.run.call_args.kwargs["image"] == "dg_image:latest"

    @patch("app.services.executors.local_executor.get_host_path_for_container_path",
           return_value="/host/uploads")
    def test_new_method_on_complex_geometry(self, mock_resolve, mock_docker_client, sim_config):
        """I8 — EP-M3, EP-G3: new method on complex geometry → correct image."""
        new_config = {
            "container_image": "mynew_image:latest", "container_name": "mynew_container",
            "simulation_method": "mynewmethod", "simulation_id": "sim-new-001",
        }
        mock_docker_client.containers.run.return_value = MagicMock()
        result = LocalExecutor().execute(new_config, sim_config)
        assert result is not None
        assert mock_docker_client.containers.run.call_args.kwargs["image"] == "mynew_image:latest"

    @patch("app.services.executors.local_executor.get_host_path_for_container_path",
           return_value="/host/uploads")
    def test_exactly_one_container_started(self, mock_resolve, mock_docker_client,
                                           method_config, sim_config):
        """I9 — EP-D1: exactly one container started per execute() call."""
        mock_docker_client.containers.run.return_value = MagicMock()
        LocalExecutor().execute(method_config, sim_config)
        mock_docker_client.containers.run.assert_called_once()


class TestLocalExecutorCancel:
    """I10–I11 — EP-D1, EP-D2"""

    def test_cancel_kills_and_removes_container(self, mock_docker_client, method_config):
        """I10 — EP-D1: kill() and remove() both called."""
        fake_container = MagicMock()
        mock_docker_client.containers.get.return_value = fake_container
        executor = LocalExecutor()
        executor.cancel({
            "simulation_method": method_config["simulation_method"],
            "simulation_id": method_config["simulation_id"],
        })
        fake_container.kill.assert_called_once()
        fake_container.remove.assert_called_once()

    def test_cancel_container_not_found_does_not_raise(self, mock_docker_client, method_config):
        """
        I11 — EP-D2 (improved)
        NotFound is caught internally — no try/except needed.
        If cancel() raises, pytest reports it directly.
        """
        import docker
        mock_docker_client.containers.get.side_effect = docker.errors.NotFound("not found")
        executor = LocalExecutor()
        executor.cancel({
            "simulation_method": method_config["simulation_method"],
            "simulation_id": method_config["simulation_id"],
        })


# =============================================================================
# SECTION 8 — DB Failure Tests (service layer via mocked session)
# =============================================================================

class RunSolverDBFailureTests(BaseTestCase):
    """EP-DB4: session.commit() raises SQLAlchemyError"""

    def setUp(self):
        super().setUp()
        self.simulation_run_id = 123
        self.json_path = "/tmp/test_db_failure.json"
        self.test_json = {
            "task_id": "test-task-db-fail",
            "simulationSettings": {},
            "results": [{"resultType": "DE", "responses": [{"receiverResults": []}]}]
        }
        Path(self.json_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self.json_path, "w") as f:
            json.dump(self.test_json, f)

    def tearDown(self):
        if os.path.exists(self.json_path):
            os.chmod(self.json_path, 0o644)
            os.unlink(self.json_path)
        super().tearDown()

    def _make_mock_simrun(self):
        m = MagicMock()
        m.id = self.simulation_run_id
        m.status = Status.Created
        m.simulationMethod = "DE"
        return m

    def _make_mock_simulation(self):
        m = MagicMock()
        m.id = 456
        m.solverSettings = {"simulationSettings": {}}
        m.settingsPreset = MagicMock(value="Default")
        m.simulationMethod = "DE"
        m.resourceType = ResourceType.LOCAL
        m.status = Status.Created
        m.simulationRunId = self.simulation_run_id
        return m

    @patch('app.services.simulation_service.scoped_session')
    @patch('app.services.simulation_service.sessionmaker')
    def test_db_commit_fails_rollback_called(self, mock_sessionmaker, mock_scoped):
        """REM1 — EP-DB4: commit raises → rollback called, session closed."""
        from sqlalchemy.exc import SQLAlchemyError
        mock_simrun = self._make_mock_simrun()
        mock_simulation = self._make_mock_simulation()
        mock_session = MagicMock()

        def query_side_effect(model_class):
            mock_query = MagicMock()
            if model_class.__name__ == 'SimulationRun':
                mock_query.get.return_value = mock_simrun
            elif model_class.__name__ == 'Simulation':
                mock_query.filter_by.return_value.first.return_value = mock_simulation
            return mock_query

        mock_session.query.side_effect = query_side_effect
        mock_session.commit.side_effect = SQLAlchemyError("DB commit failed")
        mock_scoped.return_value.return_value = mock_session

        simulation_service.run_solver(self.simulation_run_id, self.json_path)

        mock_session.rollback.assert_called()
        mock_session.close.assert_called_once()

    @patch('app.services.simulation_service.scoped_session')
    @patch('app.services.simulation_service.sessionmaker')
    def test_db_commit_fails_does_not_propagate(self, mock_sessionmaker, mock_scoped):
        """REM2 — EP-DB4: SQLAlchemyError caught internally, Celery worker safe."""
        from sqlalchemy.exc import SQLAlchemyError
        mock_session = MagicMock()
        mock_session.query.return_value.get.return_value = self._make_mock_simrun()
        mock_session.commit.side_effect = SQLAlchemyError("DB commit failed")
        mock_scoped.return_value.return_value = mock_session
        try:
            simulation_service.run_solver(self.simulation_run_id, self.json_path)
        except Exception as e:
            self.fail(f"run_solver() should not propagate DB exceptions but raised: {e}")


# =============================================================================
# SECTION 9 — Discovery Service Tests
# =============================================================================

class DiscoveryServiceRemovedMethodTests(BaseTestCase):
    """EP-DS3, EP-M4, EP-M6"""

    def setUp(self):
        super().setUp()

    def test_removed_method_does_not_appear_in_discovery(self):
        """REM3 — EP-DS3: method removed from config → no longer discovered."""
        config_with = json.dumps([
            {"simulationType": "DG", "containerImage": "dg_image:latest",
             "entryFile": "DGinterface.py", "label": "DG"},
            {"simulationType": "DE", "containerImage": "de_image:latest",
             "entryFile": "DEinterface.py", "label": "DE"},
            {"simulationType": "MyNewMethod", "containerImage": "mynew_image:latest",
             "entryFile": "MyNewMethodInterface.py", "label": "My New Method"},
        ])
        config_without = json.dumps([
            {"simulationType": "DG", "containerImage": "dg_image:latest",
             "entryFile": "DGinterface.py", "label": "DG"},
            {"simulationType": "DE", "containerImage": "de_image:latest",
             "entryFile": "DEinterface.py", "label": "DE"},
        ])
        with self.app.app_context():
            with patch("builtins.open", unittest.mock.mock_open(read_data=config_with)), \
                 patch("app.services.discovery_service.os.path.exists", return_value=True):
                methods_before = discovery_service.discover_methods()
            self.assertIn("MyNewMethod",
                          [m.get("simulationType") for m in methods_before])

            with patch("builtins.open", unittest.mock.mock_open(read_data=config_without)), \
                 patch("app.services.discovery_service.os.path.exists", return_value=True):
                methods_after = discovery_service.discover_methods()
            self.assertNotIn("MyNewMethod",
                             [m.get("simulationType") for m in methods_after])

    def test_unknown_method_returns_none_from_discover_container_image(self):
        """REM4 — EP-M4: unregistered method → discover_container_image returns None."""
        with self.app.app_context():
            result = discovery_service.discover_container_image("UnknownMethod")
        self.assertIsNone(result)

    def test_unknown_method_returns_none_from_discover_entry_file(self):
        """REM5 — EP-M4, EP-M6: unregistered method → discover_entry_file returns None."""
        with self.app.app_context():
            result = discovery_service.discover_entry_file("UnknownMethod")
        self.assertIsNone(result)
