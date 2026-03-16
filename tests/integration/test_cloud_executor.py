
import json
import pytest
import paramiko
from unittest.mock import MagicMock, patch, mock_open
from app.services.executors.cloud_executor import CloudExecutor, SSHCommandError

# =============================================================================
# CloudExecutor.execute() Integration/Edge Case Tests
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


