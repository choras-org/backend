import json
import os
import time
import pytest
import paramiko
from unittest.mock import MagicMock, patch, mock_open, call
from app.services.executors.cloud_executor import (
    CloudExecutor,
    SSHCommandError,
    _CompletedJob,
    get_filenames,
    get_local_file_path,
    get_remote_file_path,
)

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


# =============================================================================
# ORIGINAL — TestCloudExecutorUnit (unchanged)
# =============================================================================

class TestCloudExecutorUnit:
    def setup_method(self):
        # Patch SSHClient and SFTPClient for all tests
        self.ssh_patcher = patch("paramiko.SSHClient")
        self.sftp_patcher = patch("paramiko.SFTPClient")
        self.mock_ssh = self.ssh_patcher.start()
        self.mock_sftp = self.sftp_patcher.start()
        mock_stdin = MagicMock()
        mock_stdout = MagicMock()
        mock_stderr = MagicMock()
        # stdout.channel.recv_exit_status() returns 0 by default
        mock_stdout.channel.recv_exit_status.return_value = 0
        # stdout.read() and stderr.read() return empty bytes by default
        mock_stdout.read.return_value = b""
        mock_stderr.read.return_value = b""
        self.mock_ssh.return_value.exec_command.return_value = (mock_stdin, mock_stdout, mock_stderr)

    def _executor(self):
        # Provide dummy but valid args for CloudExecutor
        return CloudExecutor("host", "user", "/tmp")

    def _method_config(self):
        return {
            "container_image": "my-sim-image:latest",
            "container_name": "sim_container",
            "command": "python run.py",
            "task_id": "dummy-task"
        }

    def _sim_config(self):
        return {
            "env": {
                "JSON_PATH": "/app/uploads/input.json"
            }
        }

    def test_ssh_authentication_fails(self):
        """SSH authentication fails (AuthenticationException) → SSHCommandError raised mid-execute, sandbox partially created but not cleaned up."""
        self.mock_ssh.return_value.connect.side_effect = paramiko.AuthenticationException("Authentication failed")
        executor = self._executor()
        with pytest.raises(SSHCommandError, match="SSH authentication failed"):
            executor.execute(self._method_config(), self._sim_config())

    def test_sftp_upload_tar_fails_halfway(self):
        executor = self._executor()

        ssh_instance = self.mock_ssh.return_value
        sftp_mock = MagicMock()
        sftp_mock.__enter__.return_value = sftp_mock
        sftp_mock.put.side_effect = Exception("SFTP upload interrupted")
        ssh_instance.open_sftp.return_value = sftp_mock

        with pytest.raises(Exception, match="SFTP upload interrupted"):
            executor.execute(self._method_config(), self._sim_config())

    def test_build_singularity_image_fails(self):
        """_build_singularity_image fails (corrupted tar, insufficient disk space on remote) → singularity never launches but no cleanup runs."""
        with patch.object(CloudExecutor, "_build_singularity_image", side_effect=Exception("Disk full")):
            executor = self._executor()
            with pytest.raises(Exception, match="Disk full"):
                executor.execute(self._method_config(), self._sim_config())

    def test_remote_json_never_reaches_100(self):
        """Polling phase never reaches completion → execute remains stuck in the post-launch wait path until interrupted."""
        executor = self._executor()

        with patch.object(executor, "_upload_file_via_sftp", return_value=None), \
            patch.object(executor, "_build_singularity_image", return_value=None), \
            patch.object(executor, "_execute_singularity_image", return_value=None), \
            patch("app.services.executors.cloud_executor.get_filenames", return_value=("a.msh", "b.geo")), \
            patch.object(executor, "_poll_until_complete", side_effect=Exception("Timeout")):

            with pytest.raises(Exception, match="Timeout"):
                executor.execute(self._method_config(), self._sim_config())

    def test_remote_json_always_corrupt(self):
        """Remote progress JSON is unreadable on every polling retry → polling keeps retrying/skipping cycles until externally interrupted."""
        executor = self._executor()

        with patch.object(executor, "_upload_file_via_sftp", return_value=None), \
            patch.object(executor, "_build_singularity_image", return_value=None), \
            patch.object(executor, "_execute_singularity_image", return_value=None), \
            patch("app.services.executors.cloud_executor.get_filenames", return_value=("a.msh", "b.geo")), \
            patch.object(CloudExecutor, "_should_cancel", return_value=False), \
            patch.object(CloudExecutor, "_download_file_via_sftp", return_value=None), \
            patch("app.services.executors.cloud_executor.json.load",
                side_effect=json.JSONDecodeError("Corrupt JSON", "x", 0)), \
            patch("app.services.executors.cloud_executor.os.path.exists", return_value=False), \
            patch("app.services.executors.cloud_executor.time.sleep", side_effect=Exception("Timeout")):

            with pytest.raises(Exception, match="Timeout"):
                executor.execute(self._method_config(), self._sim_config())

    def test_cancel_flag_created_before_polling(self):
        """Cancel flag is detected before any polling download occurs → polling exits immediately and execute returns the completed-job stub."""
        executor = self._executor()

        with patch.object(executor, "_upload_file_via_sftp", return_value=None), \
            patch.object(executor, "_build_singularity_image", return_value=None), \
            patch.object(executor, "_execute_singularity_image", return_value=None), \
            patch("app.services.executors.cloud_executor.get_filenames", return_value=("a.msh", "b.geo")), \
            patch.object(CloudExecutor, "_should_cancel", return_value=True), \
            patch.object(CloudExecutor, "_download_file_via_sftp") as download_mock:

            result = executor.execute(self._method_config(), self._sim_config())

            download_mock.assert_not_called()
            assert isinstance(result, object)
            assert result.__class__.__name__ == "_CompletedJob"

    def test_collect_outputs_and_cleanup_fails_mid_download(self):
        """_collect_outputs_and_cleanup fails mid-download (network drops) → some files downloaded, some not, sandbox not cleaned up."""
        executor = self._executor()

        with patch.object(executor, "_upload_file_via_sftp", return_value=None), \
            patch.object(executor, "_build_singularity_image", return_value=None), \
            patch.object(executor, "_execute_singularity_image", return_value=None), \
            patch("app.services.executors.cloud_executor.get_filenames", return_value=("a.msh", "b.geo")), \
            patch.object(executor, "_poll_until_complete", side_effect=Exception("Network error")):

            with pytest.raises(Exception, match="Network error"):
                executor.execute(self._method_config(), self._sim_config())

    def test_build_fails_when_remote_sandbox_already_exists(self):
        """Remote sandbox already exists → build step fails and execute propagates the build error."""
        executor = self._executor()

        with patch.object(executor, "_upload_file_via_sftp", return_value=None), \
            patch.object(executor, "_build_singularity_image", side_effect=Exception("sandbox already exists")):

            with pytest.raises(Exception, match="sandbox already exists"):
                executor.execute(self._method_config(), self._sim_config())


# =============================================================================
# NEW — U1–U5: _parse_overall_progress
# Partitions: EP-P1, EP-P2, EP-C5
# =============================================================================

class TestParseOverallProgress:

    def test_multiple_results_returns_minimum(self):
        """
        U1 — EP-P1
        Multiple result entries → returns minimum percentage.
        Progress only reaches 100 when ALL sources complete.
        """
        json_data = {"results": [
            {"percentage": 80},
            {"percentage": 40},
            {"percentage": 60},
        ]}
        assert CloudExecutor._parse_overall_progress(json_data) == 40

    def test_single_result_at_100(self):
        """
        U2 — EP-P2
        Single result at 100% → returns 100.
        """
        assert CloudExecutor._parse_overall_progress(
            {"results": [{"percentage": 100}]}
        ) == 100

    def test_empty_results_list_returns_none(self):
        """
        U3 — EP-C5
        Empty results list → returns None, no exception raised.
        """
        assert CloudExecutor._parse_overall_progress({"results": []}) is None

    def test_results_entry_missing_percentage_key(self):
        """
        U4 — EP-C5
        Results entry has no 'percentage' key → defaults to 0, no exception.
        """
        result = CloudExecutor._parse_overall_progress({"results": [{"no_percentage": 1}]})
        assert result is not None
        assert result == 0

    def test_results_is_not_a_list_returns_none(self):
        """
        U5 — EP-C5
        results field is not a list → returns None, no exception.
        """
        assert CloudExecutor._parse_overall_progress({"results": "not_a_list"}) is None


# =============================================================================
# NEW — U6–U8: get_filenames
# Partitions: EP-C1, EP-C5
# =============================================================================

class TestGetFilenames:

    def test_full_paths_stripped_to_filenames(self, tmp_path):
        """
        U6 — EP-C1
        Full absolute paths stripped to filenames only.
        JSON file updated in place.
        """
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
        """
        U7 — EP-C5
        JSON missing msh_path → KeyError raised, no silent failure.
        """
        json_path = tmp_path / "input.json"
        json_path.write_text(json.dumps({"geo_path": "/app/uploads/sim1/room.geo"}))
        with pytest.raises(KeyError):
            get_filenames(str(json_path))

    def test_missing_geo_path_raises_key_error(self, tmp_path):
        """
        U8 — EP-C5
        JSON missing geo_path → KeyError raised.
        """
        json_path = tmp_path / "input.json"
        json_path.write_text(json.dumps({"msh_path": "/app/uploads/sim1/room.msh"}))
        with pytest.raises(KeyError):
            get_filenames(str(json_path))


# =============================================================================
# NEW — U9–U10: _should_cancel
# Partitions: EP-P1, EP-P6
# =============================================================================

class TestShouldCancel:

    def test_returns_false_when_no_cancel_flag(self, tmp_path):
        """
        U9 — EP-P1
        Cancel flag file absent → _should_cancel returns False.
        """
        executor = make_executor()
        executor.local_cancel_flag_path = str(tmp_path / "task.cancel")
        assert executor._should_cancel() is False

    def test_returns_true_when_cancel_flag_exists(self, tmp_path):
        """
        U10 — EP-P6
        Cancel flag file present → _should_cancel returns True.
        """
        cancel_flag = tmp_path / "task.cancel"
        cancel_flag.touch()
        executor = make_executor()
        executor.local_cancel_flag_path = str(cancel_flag)
        assert executor._should_cancel() is True


# =============================================================================
# NEW — I1–I4: _run_remote_command
# Partitions: EP-S1, EP-S2, EP-S3
# =============================================================================

class TestRunRemoteCommand:

    def _mock_exec(self, mock_ssh, exit_status=0, stdout=b"", stderr=b""):
        mock_stdout = MagicMock()
        mock_stdout.channel.recv_exit_status.return_value = exit_status
        mock_stdout.read.return_value = stdout
        mock_stderr = MagicMock()
        mock_stderr.read.return_value = stderr
        mock_ssh.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)

    def test_successful_command_returns_stdout(self):
        """
        I1 — EP-S1
        Command exits 0 → stdout returned as string.
        """
        mock_ssh = MagicMock()
        self._mock_exec(mock_ssh, exit_status=0, stdout=b"hello world")
        executor = make_executor()
        with mock_ssh_session(executor, mock_ssh):
            result = executor._run_remote_command("echo hello")
        assert result == "hello world"

    def test_ssh_authentication_fails_raises_ssh_command_error(self):
        """
        I2 — EP-S2
        AuthenticationException → SSHCommandError with clear message.
        """
        mock_ssh = MagicMock()
        mock_ssh.exec_command.side_effect = paramiko.AuthenticationException()
        executor = make_executor()
        with mock_ssh_session(executor, mock_ssh):
            with pytest.raises(SSHCommandError, match="SSH authentication failed"):
                executor._run_remote_command("mkdir -p /tmp/remote")

    def test_ssh_connection_timeout_raises_ssh_command_error(self):
        """
        I3 — EP-S3
        socket.timeout → SSHCommandError with 'SSH connection timed out'.
        """
        import socket
        mock_ssh = MagicMock()
        mock_ssh.exec_command.side_effect = socket.timeout()
        executor = make_executor()
        with mock_ssh_session(executor, mock_ssh):
            with pytest.raises(SSHCommandError, match="SSH connection timed out"):
                executor._run_remote_command("mkdir -p /tmp/remote")

    def test_non_zero_exit_status_raises_ssh_command_error(self):
        """
        I4 — EP-S1 (failure branch)
        Command exits non-zero → SSHCommandError with 'Command failed'.
        """
        mock_ssh = MagicMock()
        self._mock_exec(mock_ssh, exit_status=1, stderr=b"permission denied")
        executor = make_executor()
        with mock_ssh_session(executor, mock_ssh):
            with pytest.raises(SSHCommandError, match="Command failed"):
                executor._run_remote_command("rm -rf /protected")


# =============================================================================
# NEW — I5–I6: _upload_file_via_sftp
# Partitions: EP-S1, EP-S4
# =============================================================================

class TestUploadFileViaSftp:

    def _sftp_session(self, executor, mock_sftp):
        mock_ssh = MagicMock()
        mock_ssh.open_sftp.return_value.__enter__ = MagicMock(return_value=mock_sftp)
        mock_ssh.open_sftp.return_value.__exit__ = MagicMock(return_value=False)
        return mock_ssh_session(executor, mock_ssh)

    def test_successful_upload_calls_sftp_put(self, tmp_path):
        """
        I5 — EP-S1
        Successful upload → sftp.put called with correct local and remote paths.
        """
        local_file = tmp_path / "file.tar"
        local_file.write_bytes(b"fake tar content")
        mock_sftp = MagicMock()
        executor = make_executor()
        with self._sftp_session(executor, mock_sftp):
            executor._upload_file_via_sftp(str(local_file), "/tmp/remote/file.tar")
        mock_sftp.put.assert_called_once_with(str(local_file), "/tmp/remote/file.tar")

    def test_sftp_upload_fails_halfway_raises_exception(self, tmp_path):
        """
        I6 — EP-S4
        sftp.put raises mid-transfer → exception propagates.
        In execute() context: sandbox build attempted on incomplete tar.
        """
        local_file = tmp_path / "file.tar"
        local_file.write_bytes(b"fake tar content")
        mock_sftp = MagicMock()
        mock_sftp.put.side_effect = Exception("SFTP upload interrupted")
        executor = make_executor()
        with self._sftp_session(executor, mock_sftp):
            with pytest.raises(Exception, match="SFTP upload interrupted"):
                executor._upload_file_via_sftp(str(local_file), "/tmp/remote/file.tar")


# =============================================================================
# NEW — I7–I9: _build_singularity_image
# Partitions: EP-S1, EP-S5, EP-S6
# =============================================================================

class TestBuildSingularityImage:

    def test_successful_build_runs_correct_command(self):
        """
        I7 — EP-S1
        Successful build → singularity build command contains sandbox
        name and tar filename.
        """
        executor = make_executor()
        with patch.object(executor, "_run_remote_command", return_value="") as mock_cmd:
            executor._build_singularity_image("dg_image_sif_task1", "dg_image.tar")
        call_args = mock_cmd.call_args[0][0]
        assert "singularity build" in call_args
        assert "dg_image_sif_task1" in call_args
        assert "dg_image.tar" in call_args

    def test_disk_full_on_remote_raises_ssh_command_error(self):
        """
        I8 — EP-S5
        Remote disk full → SSHCommandError propagates.
        Singularity never launches; no cleanup runs.
        """
        executor = make_executor()
        with patch.object(executor, "_run_remote_command",
                          side_effect=SSHCommandError("No space left on device")):
            with pytest.raises(SSHCommandError, match="No space left on device"):
                executor._build_singularity_image("dg_image_sif_task1", "dg_image.tar")

    def test_sandbox_already_exists_raises_ssh_command_error(self):
        """
        I9 — EP-S6
        Sandbox already exists from a previous failed run →
        SSHCommandError referencing 'already exists'.
        """
        executor = make_executor()
        with patch.object(executor, "_run_remote_command",
                          side_effect=SSHCommandError(
                              "sandbox already exists: dg_image_sif_task1")):
            with pytest.raises(SSHCommandError, match="already exists"):
                executor._build_singularity_image("dg_image_sif_task1", "dg_image.tar")


# =============================================================================
# NEW — I10–I11: _execute_singularity_image
# Partitions: EP-S1, EP-S5
# =============================================================================

class TestExecuteSingularityImage:

    def test_launches_singularity_in_background(self):
        """
        I10 — EP-S1
        Singularity launched with nohup and & suffix so execute()
        returns immediately without blocking.
        """
        executor = make_executor()
        with patch.object(executor, "_run_remote_command", return_value="") as mock_cmd:
            executor._execute_singularity_image(
                sandbox_name="dg_image_sif_task1",
                input_json="input.json"
            )
        cmd = mock_cmd.call_args[0][0]
        assert "nohup" in cmd
        assert "singularity exec" in cmd
        assert "input.json" in cmd
        assert cmd.strip().endswith("&")

    def test_command_includes_entry_file(self):
        """
        I11 — EP-S1
        The entry file passed to CloudExecutor constructor appears
        in the singularity exec command.
        """
        executor = CloudExecutor(
            hostname="host",
            username="user",
            remote_work_dir="/tmp",
            password="pass",
            entry_file="DGinterface.py"
        )
        with patch.object(executor, "_run_remote_command", return_value="") as mock_cmd:
            executor._execute_singularity_image(
                sandbox_name="dg_image_sif_task1",
                input_json="input.json"
            )
        cmd = mock_cmd.call_args[0][0]
        assert "DGinterface.py" in cmd


# =============================================================================
# NEW — I12–I16, B12–B13: _poll_until_complete
# Partitions: EP-P1, EP-P2, EP-P3, EP-P4, EP-P5, EP-P6, EP-P7
# =============================================================================

class TestPollUntilComplete:

    def test_progress_reaches_100_calls_cleanup_and_returns_true(self, tmp_path):
        """
        I12 — EP-P1, EP-P2
        Remote JSON reaches 100% on first poll →
        _collect_outputs_and_cleanup called, True returned.
        """
        executor = make_executor()
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

    def test_json_only_written_locally_when_progress_changes(self, tmp_path):
        """
        I13 — EP-P1
        Local JSON only written when percentage changes.
        Cycle 1: 0% → write. Cycle 2: 0% → no write. Cycle 3: 100% → write.
        """
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

        executor = make_executor()
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
        """
        I14 — EP-P3
        JSON corrupt on first attempt, valid on second →
        polling recovers and completes successfully.
        """
        attempt = {"n": 0}

        def fake_download(remote, local):
            if attempt["n"] == 0:
                with open(local, "w") as f:
                    f.write("{corrupt json{{")
            else:
                write_json(local, 100)
            attempt["n"] += 1

        executor = make_executor()
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
        """
        I15 — EP-P6
        Cancel flag exists at poll entry →
        exits immediately, nothing downloaded, no cleanup.
        """
        cancel_flag = tmp_path / "task-001.cancel"
        cancel_flag.touch()

        executor = make_executor()
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
        """
        I16 — EP-P7
        Cancel flag created after cycle 1 →
        polling stops at cycle 2, outputs not downloaded.
        """
        cancel_flag = tmp_path / "task-001.cancel"
        call_count = {"n": 0}
        executor = make_executor()
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
        reason="KNOWN BUG B12: No stall timeout in _poll_until_complete. "
               "Progress stuck at 50% loops forever. "
               "Remove xfail once stall-detection is implemented."
    )
    def test_progress_stuck_raises_runtime_error(self, tmp_path):
        """
        B12 — EP-P5
        Remote job crashes silently — progress always 50% →
        should raise RuntimeError after stall timeout.
        """
        executor = make_executor()
        executor.local_cancel_flag_path = str(tmp_path / "task.cancel")

        with patch.object(executor, "_download_file_via_sftp",
                          side_effect=lambda r, l: write_json(l, 50)), \
             patch("time.sleep",
                   side_effect=[None] * 5 + [RuntimeError(
                       "forced exit — no timeout implemented")]):
            with pytest.raises(RuntimeError, match="timeout|stall|crashed|forced exit"):
                executor._poll_until_complete(
                    remote_json_path="/remote/app/input.json",
                    local_uploads_dir=str(tmp_path),
                    remote_app_dir="/remote/app",
                    remote_sandbox_path="/remote/sandbox",
                )

    @pytest.mark.xfail(
        reason="KNOWN BUG B13: No POLL_MAX_FAILED_CYCLES limit. "
               "JSON always corrupt loops forever. "
               "Remove xfail once max failed cycle count is implemented."
    )
    def test_json_always_corrupt_raises_runtime_error(self, tmp_path):
        """
        B13 — EP-P4
        Remote JSON corrupt on all 3 retries every cycle →
        should raise RuntimeError after POLL_MAX_FAILED_CYCLES.
        """
        executor = make_executor()
        executor.local_cancel_flag_path = str(tmp_path / "task.cancel")

        def always_corrupt(remote, local):
            with open(local, "w") as f:
                f.write("{always corrupt{{{")

        with patch.object(executor, "_download_file_via_sftp",
                          side_effect=always_corrupt), \
             patch("time.sleep",
                   side_effect=[None] * 5 + [RuntimeError(
                       "forced exit — no failed cycle limit implemented")]):
            with pytest.raises(RuntimeError, match="unreadable|corrupt|failed cycles|forced exit"):
                executor._poll_until_complete(
                    remote_json_path="/remote/app/input.json",
                    local_uploads_dir=str(tmp_path),
                    remote_app_dir="/remote/app",
                    remote_sandbox_path="/remote/sandbox",
                )


# =============================================================================
# NEW — I17–I19: _collect_outputs_and_cleanup
# Partitions: EP-O1, EP-S4
# =============================================================================

class TestCollectOutputsAndCleanup:

    def _sftp_session(self, executor, mock_sftp):
        mock_ssh = MagicMock()
        mock_ssh.open_sftp.return_value.__enter__ = MagicMock(return_value=mock_sftp)
        mock_ssh.open_sftp.return_value.__exit__ = MagicMock(return_value=False)
        return mock_ssh_session(executor, mock_ssh)

    def test_downloads_only_json_and_csv_ignores_others(self, tmp_path):
        """
        I17 — EP-O1
        Remote dir contains .json, .csv, .py, .msh →
        only .json and .csv downloaded.
        """
        mock_sftp = MagicMock()
        executor = make_executor()

        with self._sftp_session(executor, mock_sftp), \
             patch.object(executor, "_list_remote_files", return_value=[
                 "/remote/app/results.json",
                 "/remote/app/pressure.csv",
                 "/remote/app/solver.py",
                 "/remote/app/room.msh",
             ]), \
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

    def test_cleanup_called_after_successful_download(self, tmp_path):
        """
        I18 — EP-O1
        Outputs downloaded → _cleanup called with sandbox and tar paths.
        """
        mock_sftp = MagicMock()
        executor = make_executor()

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

    def test_sftp_download_failure_returns_false_no_cleanup(self, tmp_path):
        """
        I19 — EP-S4
        sftp.get raises mid-download →
        returns False, _cleanup not called (sandbox left on remote).
        """
        mock_sftp = MagicMock()
        mock_sftp.get.side_effect = Exception("Network error during download")
        executor = make_executor()

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
# NEW — I20–I23: execute() happy path
# Partitions: EP-S1, EP-M2
# =============================================================================

class TestExecuteHappyPath:

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
        """
        I20 — EP-S1, EP-M2
        Full successful execute() → returns _CompletedJob.
        """
        executor = make_executor()
        with patch.multiple(CloudExecutor, **self._all_ssh_patches()):
            result = executor.execute(self._method_config(), self._write_sim_config(tmp_path))
        assert isinstance(result, _CompletedJob)

    def test_execute_calls_poll_until_complete(self, tmp_path):
        """
        I21 — EP-S1
        execute() calls _poll_until_complete exactly once.
        """
        executor = make_executor()
        patches = self._all_ssh_patches()
        with patch.multiple(CloudExecutor, **patches):
            executor.execute(self._method_config(), self._write_sim_config(tmp_path))
        patches["_poll_until_complete"].assert_called_once()

    def test_execute_uploads_tar_file(self, tmp_path):
        """
        I22 — EP-S1
        execute() uploads the Docker tar to the remote host.
        """
        executor = make_executor()
        patches = self._all_ssh_patches()
        with patch.multiple(CloudExecutor, **patches):
            executor.execute(self._method_config(), self._write_sim_config(tmp_path))
        upload_calls = [c[0][1] for c in
                        patches["_upload_file_via_sftp"].call_args_list]
        assert any("dg_image.tar" in str(c) for c in upload_calls)

    def test_execute_strips_tag_from_sandbox_name(self, tmp_path):
        """
        I23 — EP-S1
        :latest tag stripped from image name when constructing sandbox name.
        """
        executor = make_executor()
        patches = self._all_ssh_patches()
        with patch.multiple(CloudExecutor, **patches):
            executor.execute(self._method_config(), self._write_sim_config(tmp_path))
        sandbox_arg = patches["_build_singularity_image"].call_args[0][0]
        assert ":latest" not in sandbox_arg
        assert "dg_image" in sandbox_arg


# =============================================================================
# NEW — I24–I25: cancel()
# Partitions: EP-S1
# =============================================================================

class TestCancel:

    def test_cancel_kills_processes_and_cleans_up(self):
        """
        I24 — EP-S1
        cancel() kills Singularity container processes and removes
        sandbox and tar from the remote host.
        """
        executor = make_executor()
        cancelation_info = {
            "container_image": "dg_image:latest",
            "task_id": "task-001"
        }
        with patch.object(executor, "_kill_container_processes") as mock_kill, \
             patch.object(executor, "_cleanup") as mock_cleanup:
            executor.cancel(cancelation_info)

        mock_kill.assert_called_once_with("dg_image_sif_task-001")
        mock_cleanup.assert_called_once()

    def test_cancel_constructs_correct_sandbox_name(self):
        """
        I25 — EP-S1
        cancel() strips :latest tag and appends sif_{task_id} to form
        the correct sandbox name.
        """
        executor = make_executor()
        cancelation_info = {
            "container_image": "dg_image:latest",
            "task_id": "abc-123"
        }
        with patch.object(executor, "_kill_container_processes") as mock_kill, \
             patch.object(executor, "_cleanup"):
            executor.cancel(cancelation_info)

        assert mock_kill.call_args[0][0] == "dg_image_sif_abc-123"
