import json
import pytest
from unittest.mock import MagicMock, patch
from app.services.executors.cloud_executor import (
    CloudExecutor,
    SSHCommandError,
    _CompletedJob,
    get_local_file_path,
    get_remote_file_path,
)
from app.services.executors.local_executor import LocalExecutor

# =============================================================================
# Helpers
# =============================================================================

def make_executor():
    return CloudExecutor(
        hostname="test-host",
        username="test-user",
        remote_work_dir="/tmp/remote",
        password="test-pass"
    )


def mock_ssh_session(executor, mock_ssh):
    """Patch _ssh_session to yield mock_ssh as a context manager."""
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=mock_ssh)
    ctx.__exit__ = MagicMock(return_value=False)
    return patch.object(executor, "_ssh_session", return_value=ctx)


def make_sftp_session(executor, mock_sftp):
    """Patch _ssh_session so open_sftp() returns mock_sftp."""
    mock_ssh = MagicMock()
    mock_ssh.open_sftp.return_value.__enter__ = MagicMock(return_value=mock_sftp)
    mock_ssh.open_sftp.return_value.__exit__ = MagicMock(return_value=False)
    return mock_ssh_session(executor, mock_ssh)


# =============================================================================
# U5–U6: get_local_file_path
# Partitions: EP-C1
# =============================================================================

class TestGetLocalFilePath:

    def test_joins_dirname_and_filename(self):
        """
        U5 — EP-C1
        Function constructs a local path by joining the directory of the
        JSON path with a given filename.

        Input: json_path="/app/uploads/input.json", filename="mesh.msh"
        Expected: "/app/uploads/mesh.msh"
        Process: Call get_local_file_path and assert result equals expected path.
        """
        result = get_local_file_path("/app/uploads/input.json", "mesh.msh")
        assert result == "/app/uploads/mesh.msh"

    def test_works_with_nested_directory(self):
        """
        U6 — EP-C1
        Correctly handles a deeply nested directory path.

        Input: json_path="/a/b/c/file.json", filename="out.csv"
        Expected: "/a/b/c/out.csv"
        Process: Call get_local_file_path and assert result equals expected path.
        """
        result = get_local_file_path("/a/b/c/file.json", "out.csv")
        assert result == "/a/b/c/out.csv"


# =============================================================================
# U7: get_remote_file_path
# Partitions: EP-C1
# =============================================================================

class TestGetRemoteFilePath:

    def test_constructs_correct_remote_path(self):
        """
        U7 — EP-C1
        Function builds the correct remote sandbox path for a given file,
        combining the remote_work_dir, image name, task_id and filename.

        Input: remote_work_dir="/tmp/remote", image_name="dg_image",
               task_id="abc-123", filename="input.json"
        Expected: "/tmp/remote/dg_image_sif_abc-123/app/input.json"
        Process: Call get_remote_file_path and assert result equals expected path.
        """
        result = get_remote_file_path("/tmp/remote", "dg_image", "abc-123", "input.json")
        assert result == "/tmp/remote/dg_image_sif_abc-123/app/input.json"


# =============================================================================
# U8–U9: _CompletedJob
# Partitions: EP-O1
# =============================================================================

class TestCompletedJob:

    def test_wait_returns_zero_status_code(self):
        """
        U8 — EP-O1
        wait() returns {"StatusCode": 0} so simulation_service.py can
        call it without error after a cloud job completes.

        Input: _CompletedJob() instance
        Expected: {"StatusCode": 0}
        Process: Instantiate _CompletedJob, call wait(), assert return value.
        """
        job = _CompletedJob()
        assert job.wait() == {"StatusCode": 0}

    def test_logs_returns_bytes(self):
        """
        U9 — EP-O1
        logs() returns a bytes object so callers can call .decode()
        on it without error.

        Input: _CompletedJob() instance
        Expected: isinstance(result, bytes) is True
        Process: Instantiate _CompletedJob, call logs(), assert type is bytes.
        """
        job = _CompletedJob()
        assert isinstance(job.logs(), bytes)


# =============================================================================
# U10–U11: CloudExecutor.__init__
# Partitions: EP-S1
# =============================================================================

class TestCloudExecutorInit:

    def test_stores_all_constructor_parameters(self):
        """
        U10 — EP-S1
        All constructor arguments are stored as instance attributes
        with correct values.

        Input: CloudExecutor("host", "user", "/work", "pass", "/key", "entry.py")
        Expected: Each attribute matches the corresponding constructor argument.
        Process: Instantiate with all params, assert each attribute value.
        """
        executor = CloudExecutor(
            hostname="host",
            username="user",
            remote_work_dir="/work",
            password="pass",
            key_path="/key",
            entry_file="entry.py"
        )
        assert executor.hostname == "host"
        assert executor.username == "user"
        assert executor.remote_work_dir == "/work"
        assert executor.password == "pass"
        assert executor.key_path == "/key"
        assert executor.entry_file == "entry.py"

    def test_local_cancel_flag_path_initially_none(self):
        """
        U11 — EP-S1
        local_cancel_flag_path is None on construction — not set until
        execute() is called with a specific task_id.

        Input: CloudExecutor("host", "user")
        Expected: executor.local_cancel_flag_path is None
        Process: Instantiate, assert local_cancel_flag_path attribute is None.
        """
        executor = CloudExecutor(hostname="host", username="user")
        assert executor.local_cancel_flag_path is None


# =============================================================================
# U25: LocalExecutor.__init__ — _jobs dict
# Partitions: EP-D1
# =============================================================================

class TestLocalExecutorInitJobs:

    def test_jobs_dict_initialised_empty(self):
        """
        U25 — EP-D1
        The _jobs dict starts empty on construction — no stale state
        from previous runs.

        Input: LocalExecutor()
        Expected: executor._jobs == {}
        Process: Instantiate LocalExecutor, assert _jobs attribute is empty dict.

        Note: Requires _jobs = {} to be added to LocalExecutor.__init__
        if not already present.
        """
        executor = LocalExecutor()
        # If _jobs does not exist yet this test will fail with AttributeError,
        # indicating the implementation change is still needed.
        assert hasattr(executor, "_jobs"), \
            "_jobs attribute missing — add _jobs = {} to LocalExecutor.__init__"
        assert executor._jobs == {}


# =============================================================================
# I7: _download_file_via_sftp — happy path
# Partitions: EP-S1
# =============================================================================

class TestDownloadFileViaSftp:

    def test_successful_download_calls_sftp_get(self):
        """
        I7 — EP-S1
        Successful download calls sftp.get with correct remote and
        local paths.

        Input: remote="remote/file.json", local="/local/file.json"
        Expected: sftp.get called once with ("remote/file.json", "/local/file.json")
        Process: Mock SSH session, call _download_file_via_sftp, assert sftp.get call.
        """
        mock_sftp = MagicMock()
        executor = make_executor()
        with make_sftp_session(executor, mock_sftp):
            executor._download_file_via_sftp("remote/file.json", "/local/file.json")
        mock_sftp.get.assert_called_once_with("remote/file.json", "/local/file.json")


# =============================================================================
# I8: _list_remote_files — happy path
# Partitions: EP-O1
# =============================================================================

class TestListRemoteFiles:

    def test_returns_full_paths_and_excludes_hidden_files(self):
        """
        I8 — EP-O1
        Returns full remote paths for all non-hidden files and excludes
        files starting with '.'.

        Input: Directory entries: output.json, data.csv, .hidden
        Expected: Result contains full paths for output.json and data.csv,
                  does not contain .hidden
        Process: Mock listdir_attr, call _list_remote_files, assert contents.
        """
        entry_a = MagicMock()
        entry_a.filename = "output.json"
        entry_b = MagicMock()
        entry_b.filename = "data.csv"
        entry_hidden = MagicMock()
        entry_hidden.filename = ".hidden"

        mock_sftp = MagicMock()
        mock_sftp.listdir_attr.return_value = [entry_a, entry_b, entry_hidden]

        executor = make_executor()
        with make_sftp_session(executor, mock_sftp):
            result = executor._list_remote_files("sandbox/app")

        assert "sandbox/app/output.json" in result
        assert "sandbox/app/data.csv" in result
        assert "sandbox/app/.hidden" not in result

    def test_returns_empty_list_for_empty_directory(self):
        """
        I8 (boundary) — EP-O1
        Empty remote directory returns an empty list without error.

        Input: listdir_attr returns []
        Expected: Returns []
        Process: Mock listdir_attr to return empty list, assert empty result.
        """
        mock_sftp = MagicMock()
        mock_sftp.listdir_attr.return_value = []

        executor = make_executor()
        with make_sftp_session(executor, mock_sftp):
            result = executor._list_remote_files("sandbox/app")

        assert result == []


# =============================================================================
# I9: _delete_remote_path
# Partitions: EP-S1
# =============================================================================

class TestDeleteRemotePath:

    def test_runs_rm_rf_command(self):
        """
        I9 — EP-S1
        _delete_remote_path executes 'rm -rf {path}' on the remote
        via _run_remote_command.

        Input: remote_path="sandbox/path"
        Expected: _run_remote_command called with "rm -rf sandbox/path"
        Process: Patch _run_remote_command, call _delete_remote_path, assert call.
        """
        executor = make_executor()
        with patch.object(executor, "_run_remote_command", return_value="") as mock_cmd:
            executor._delete_remote_path("sandbox/path")
        mock_cmd.assert_called_once_with("rm -rf sandbox/path")

    def test_delete_propagates_ssh_error(self):
        """
        I9 (bad day) — EP-S5
        If _run_remote_command raises (e.g. permission denied),
        the exception propagates out of _delete_remote_path.

        Input: _run_remote_command raises SSHCommandError
        Expected: SSHCommandError propagates
        Process: Patch _run_remote_command to raise, assert exception raised.
        """
        executor = make_executor()
        with patch.object(executor, "_run_remote_command",
                          side_effect=SSHCommandError("permission denied")):
            with pytest.raises(SSHCommandError, match="permission denied"):
                executor._delete_remote_path("sandbox/path")


# =============================================================================
# B5: _execute_singularity_image — bad day
# Partitions: EP-S5
# =============================================================================

class TestExecuteSingularityImageBadDay:

    def test_raises_when_exec_command_fails(self):
        """
        B5 — EP-S5
        When _run_remote_command raises during singularity exec,
        the exception propagates out of _execute_singularity_image.
        Singularity never launches; no background process started.

        Input: _run_remote_command raises SSHCommandError("exec failed")
        Expected: SSHCommandError raised matching "exec failed"
        Process: Patch _run_remote_command to raise, call _execute_singularity_image,
                 assert exception propagates.
        """
        executor = make_executor()
        with patch.object(executor, "_run_remote_command",
                          side_effect=SSHCommandError("exec failed")):
            with pytest.raises(SSHCommandError, match="exec failed"):
                executor._execute_singularity_image(
                    sandbox_name="dg_image_sif_task1",
                    input_json="input.json"
                )

    def test_raises_when_ssh_connection_drops_mid_launch(self):
        """
        B5 (variant) — EP-S5
        SSH connection drops during the nohup launch command →
        SSHCommandError propagates, process may or may not have started
        on the remote.

        Input: _run_remote_command raises SSHCommandError("SSH connection lost")
        Expected: SSHCommandError raised matching "SSH connection lost"
        Process: Patch _run_remote_command to raise on connection loss,
                 assert exception propagates.
        """
        executor = make_executor()
        with patch.object(executor, "_run_remote_command",
                          side_effect=SSHCommandError("SSH connection lost")):
            with pytest.raises(SSHCommandError, match="SSH connection lost"):
                executor._execute_singularity_image(
                    sandbox_name="dg_image_sif_task1",
                    input_json="input.json"
                )
