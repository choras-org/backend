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
    """Create a CloudExecutor with all required constructor arguments."""
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
    """
    Patch _ssh_session so that open_sftp() returns mock_sftp both:
      - As a direct call:  sftp = ssh_client.open_sftp()
      - As a context mgr:  with ssh_client.open_sftp() as sftp:

    _download_file_via_sftp calls open_sftp() twice — once as a context
    manager and once as a direct reassignment inside the with block.
    _list_remote_files uses only the context manager form.
    Both patterns are handled by making mock_sftp its own context manager
    that returns itself from __enter__.
    """
    mock_ssh = MagicMock()

    # open_sftp() returns mock_sftp on every direct call
    mock_ssh.open_sftp.return_value = mock_sftp

    # mock_sftp also supports the context manager protocol so that
    # `with ssh_client.open_sftp() as sftp:` also gives mock_sftp
    mock_sftp.__enter__ = MagicMock(return_value=mock_sftp)
    mock_sftp.__exit__ = MagicMock(return_value=False)

    return mock_ssh_session(executor, mock_ssh)


# =============================================================================
# U5-U6: get_local_file_path
# Partitions: EP-C1
# =============================================================================

class TestGetLocalFilePath:

    def test_joins_dirname_and_filename(self):
        """
        U5 - EP-C1
        Function constructs a local path by joining the directory of the
        JSON path with a given filename.

        Input:    json_path="/app/uploads/input.json", filename="mesh.msh"
        Expected: "/app/uploads/mesh.msh"
        Process:  Call get_local_file_path and assert result equals expected path.
        """
        result = get_local_file_path("/app/uploads/input.json", "mesh.msh")
        assert result == "/app/uploads/mesh.msh"

    def test_works_with_nested_directory(self):
        """
        U6 - EP-C1
        Correctly handles a deeply nested directory path.

        Input:    json_path="/a/b/c/file.json", filename="out.csv"
        Expected: "/a/b/c/out.csv"
        Process:  Call get_local_file_path and assert result equals expected path.
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
        U7 - EP-C1
        Function builds the correct remote sandbox path for a given file,
        combining remote_work_dir, image name, task_id, and filename.

        Uses the current 4-argument signature:
            get_remote_file_path(remote_work_dir, image_name, task_id, filename)

        Input:    remote_work_dir="/tmp/remote", image_name="dg_image",
                  task_id="abc-123", filename="input.json"
        Expected: "/tmp/remote/dg_image_sif_abc-123/app/input.json"
        Process:  Call get_remote_file_path with 4 args and assert result.
        """
        result = get_remote_file_path(
            "/tmp/remote", "dg_image", "abc-123", "input.json"
        )
        assert result == "/tmp/remote/dg_image_sif_abc-123/app/input.json"


# =============================================================================
# U8-U9: _CompletedJob
# Partitions: EP-O1
# =============================================================================

class TestCompletedJob:

    def test_wait_returns_zero_status_code(self):
        """
        U8 - EP-O1
        wait() returns {"StatusCode": 0} so simulation_service.py can
        call container.wait() without error after a cloud job completes.

        Input:    _CompletedJob() instance
        Expected: {"StatusCode": 0}
        Process:  Instantiate _CompletedJob, call wait(), assert return value.
        """
        job = _CompletedJob()
        assert job.wait() == {"StatusCode": 0}

    def test_logs_returns_bytes(self):
        """
        U9 - EP-O1
        logs() returns a bytes object so callers can call .decode()
        on it without a TypeError.

        Input:    _CompletedJob() instance
        Expected: isinstance(result, bytes) is True
        Process:  Instantiate _CompletedJob, call logs(), assert type is bytes.
        """
        job = _CompletedJob()
        assert isinstance(job.logs(), bytes)


# =============================================================================
# U10-U11: CloudExecutor.__init__
# Partitions: EP-S1
# =============================================================================

class TestCloudExecutorInit:

    def test_stores_all_constructor_parameters(self):
        """
        U10 - EP-S1
        All constructor arguments are stored as instance attributes
        with correct values.

        Constructor signature:
            CloudExecutor(hostname, username, remote_work_dir,
                          password=None, key_path=None, entry_file=None)

        Input:    keyword args for all six parameters
        Expected: each attribute matches the corresponding argument
        Process:  Instantiate with all params, assert each attribute value.
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
        U11 - EP-S1
        local_cancel_flag_path is None on construction - not set until
        execute() is called with a specific task_id.

        remote_work_dir is a required positional argument and must be
        provided even in minimal instantiation.

        Input:    CloudExecutor(hostname="host", username="user",
                                remote_work_dir="/tmp")
        Expected: executor.local_cancel_flag_path is None
        Process:  Instantiate, assert local_cancel_flag_path attribute is None.
        """
        executor = CloudExecutor(
            hostname="host",
            username="user",
            remote_work_dir="/tmp"
        )
        assert executor.local_cancel_flag_path is None


# =============================================================================
# U25: LocalExecutor.__init__ - _jobs dict
# Partitions: EP-D1
# =============================================================================

class TestLocalExecutorInitJobs:

    @pytest.mark.xfail(
        reason="KNOWN IMPLEMENTATION GAP: _jobs = {} not yet added to "
               "LocalExecutor.__init__. Remove xfail once the attribute "
               "is added to the constructor."
    )
    def test_jobs_dict_initialised_empty(self):
        """
        U25 - EP-D1
        The _jobs dict starts empty on construction - no stale state
        from previous runs.

        Input:    LocalExecutor()
        Expected: executor._jobs == {}
        Process:  Instantiate LocalExecutor, assert _jobs attribute is
                  an empty dict.

        Implementation note: add _jobs = {} to LocalExecutor.__init__
        to make this test pass.
        """
        executor = LocalExecutor()
        assert hasattr(executor, "_jobs"), \
            "_jobs attribute missing - add _jobs = {} to LocalExecutor.__init__"
        assert executor._jobs == {}


# =============================================================================
# I7: _download_file_via_sftp - happy path
# Partitions: EP-S1
# =============================================================================

class TestDownloadFileViaSftp:

    def test_successful_download_calls_sftp_get(self):
        """
        I7 - EP-S1
        Successful download calls sftp.get with the correct remote and
        local paths.

        The actual implementation calls open_sftp() twice:
          1. As a context manager: with ssh_client.open_sftp() as sftp:
          2. Direct reassignment:  sftp = ssh_client.open_sftp()
        make_sftp_session handles both by making mock_sftp its own
        context manager that returns itself from __enter__.

        Input:    remote="remote/file.json", local="/local/file.json"
        Expected: sftp.get called once with
                  ("remote/file.json", "/local/file.json")
        Process:  Mock SSH/SFTP session, call _download_file_via_sftp,
                  assert sftp.get call arguments.
        """
        mock_sftp = MagicMock()
        executor = make_executor()
        with make_sftp_session(executor, mock_sftp):
            executor._download_file_via_sftp(
                "remote/file.json", "/local/file.json"
            )
        mock_sftp.get.assert_called_once_with(
            "remote/file.json", "/local/file.json"
        )


# =============================================================================
# I8: _list_remote_files - happy path
# Partitions: EP-O1
# =============================================================================

class TestListRemoteFiles:

    def test_returns_full_paths_and_excludes_hidden_files(self):
        """
        I8 - EP-O1
        Returns full remote paths for all non-hidden files and excludes
        files starting with '.'.

        _list_remote_files uses the context manager form only:
            with ssh_client.open_sftp() as sftp:
                entries = sftp.listdir_attr(remote_dir)
        mock_sftp.__enter__ returns mock_sftp so listdir_attr is
        reachable.

        Input:    Directory entries: output.json, data.csv, .hidden
        Expected: Result contains "sandbox/app/output.json" and
                  "sandbox/app/data.csv" but not "sandbox/app/.hidden"
        Process:  Mock listdir_attr return value, call _list_remote_files,
                  assert presence and absence of paths.
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
        I8 (boundary) - EP-O1
        Empty remote directory returns an empty list without raising.

        Input:    listdir_attr returns []
        Expected: Returns []
        Process:  Mock listdir_attr to return empty list,
                  call _list_remote_files, assert result is empty list.
        """
        mock_sftp = MagicMock()
        mock_sftp.listdir_attr.return_value = []

        executor = make_executor()
        with make_sftp_session(executor, mock_sftp):
            result = executor._list_remote_files("sandbox/app")

        assert result == []


# =============================================================================
# I9: _delete_remote_path
# Partitions: EP-S1, EP-S5
# =============================================================================

class TestDeleteRemotePath:

    def test_runs_rm_rf_command(self):
        """
        I9 - EP-S1
        _delete_remote_path executes 'rm -rf {path}' on the remote
        by passing the command to _run_remote_command.

        Input:    remote_path="sandbox/path"
        Expected: _run_remote_command called with "rm -rf sandbox/path"
        Process:  Patch _run_remote_command, call _delete_remote_path,
                  assert the exact command string passed.
        """
        executor = make_executor()
        with patch.object(
            executor, "_run_remote_command", return_value=""
        ) as mock_cmd:
            executor._delete_remote_path("sandbox/path")
        mock_cmd.assert_called_once_with("rm -rf sandbox/path")

    def test_delete_propagates_ssh_error(self):
        """
        I9 (bad day) - EP-S5
        If _run_remote_command raises (e.g. permission denied on remote),
        the exception propagates out of _delete_remote_path unchanged.

        Input:    _run_remote_command raises SSHCommandError("permission denied")
        Expected: SSHCommandError matching "permission denied" propagates
        Process:  Patch _run_remote_command to raise, call _delete_remote_path,
                  assert exception is raised with correct message.
        """
        executor = make_executor()
        with patch.object(
            executor, "_run_remote_command",
            side_effect=SSHCommandError("permission denied")
        ):
            with pytest.raises(SSHCommandError, match="permission denied"):
                executor._delete_remote_path("sandbox/path")


# =============================================================================
# B5: _execute_singularity_image - bad day
# Partitions: EP-S5
# =============================================================================

class TestExecuteSingularityImageBadDay:

    def test_raises_when_exec_command_fails(self):
        """
        B5 - EP-S5
        When _run_remote_command raises during the singularity exec call,
        the exception propagates out of _execute_singularity_image.
        Singularity never launches; no background process is started.

        Input:    _run_remote_command raises SSHCommandError("exec failed")
        Expected: SSHCommandError matching "exec failed" propagates
        Process:  Patch _run_remote_command to raise, call
                  _execute_singularity_image, assert exception propagates.
        """
        executor = make_executor()
        with patch.object(
            executor, "_run_remote_command",
            side_effect=SSHCommandError("exec failed")
        ):
            with pytest.raises(SSHCommandError, match="exec failed"):
                executor._execute_singularity_image(
                    sandbox_name="dg_image_sif_task1",
                    input_json="input.json"
                )

    def test_raises_when_ssh_connection_drops_mid_launch(self):
        """
        B5 (variant) - EP-S5
        SSH connection drops during the nohup launch command -
        SSHCommandError propagates. The remote process may or may not
        have started before the connection was lost.

        Input:    _run_remote_command raises
                  SSHCommandError("SSH connection lost")
        Expected: SSHCommandError matching "SSH connection lost" propagates
        Process:  Patch _run_remote_command to raise on connection loss,
                  assert exception propagates out of
                  _execute_singularity_image.
        """
        executor = make_executor()
        with patch.object(
            executor, "_run_remote_command",
            side_effect=SSHCommandError("SSH connection lost")
        ):
            with pytest.raises(SSHCommandError, match="SSH connection lost"):
                executor._execute_singularity_image(
                    sandbox_name="dg_image_sif_task1",
                    input_json="input.json"
                )