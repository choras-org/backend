
import pytest
from unittest.mock import MagicMock, patch
from app.services.executors.cloud_executor import CloudExecutor, SSHCommandError

# =============================================================================
# CloudExecutor.execute() Integration/Edge Case Tests
# =============================================================================

class TestCloudExecutorExecute:
    def _executor(self):
        # Provide dummy but valid args for CloudExecutor
        return CloudExecutor("host", "user", "/tmp")

    def _method_config(self):
        return {
            "container_image": "my-sim-image:latest",
            "container_name": "sim_container",
            "command": "python run.py"
        }

    def _sim_config(self):
        return {
            "env": {
                "JSON_PATH": "/app/uploads/input.json"
            }
        }

    def test_ssh_authentication_fails(self):
        """SSH authentication fails (AuthenticationException) → SSHCommandError raised mid-execute, sandbox partially created but not cleaned up."""
        with patch("paramiko.SSHClient") as mock_ssh:
            mock_ssh.return_value.connect.side_effect = Exception("Authentication failed")
            executor = self._executor()
            with pytest.raises(SSHCommandError, match="Authentication failed"):
                executor.execute(self._method_config(), self._sim_config())

    def test_sftp_upload_tar_fails_halfway(self):
        """SFTP upload of tar fails halfway → sandbox build attempted on incomplete tar."""
        with patch("paramiko.SSHClient") as mock_ssh, \
             patch("paramiko.SFTPClient") as mock_sftp:
            mock_ssh.return_value.open_sftp.return_value = mock_sftp.return_value
            mock_sftp.return_value.put.side_effect = Exception("SFTP upload interrupted")
            executor = self._executor()
            with pytest.raises(Exception, match="SFTP upload interrupted"):
                executor.execute(self._method_config(), self._sim_config())

    def test_build_singularity_image_fails(self):
        """_build_singularity_image fails (corrupted tar, insufficient disk space on remote) → singularity never launches but no cleanup runs."""
        with patch.object(CloudExecutor, "_build_singularity_image", side_effect=Exception("Disk full")):
            executor = self._executor()
            with pytest.raises(Exception, match="Disk full"):
                executor.execute(self._method_config(), self._sim_config())

    def test_remote_json_never_reaches_100(self):
        """Remote JSON never reaches 100% (simulation crashes silently on remote) → polling loops forever, never exits."""
        # Patch a method that would be called in the polling loop. If not present, add a dummy method for test.
        if not hasattr(CloudExecutor, "_poll_progress"):
            setattr(CloudExecutor, "_poll_progress", lambda self: {"progress": 50})
        with patch.object(CloudExecutor, "_poll_progress", side_effect=lambda self: {"progress": 50}):
            executor = self._executor()
            with patch("time.sleep", side_effect=Exception("Timeout")):
                with pytest.raises(Exception, match="Timeout"):
                    executor.execute(self._method_config(), self._sim_config())

    def test_remote_json_always_corrupt(self):
        """Remote JSON is always corrupt / unreadable across all 3 retries → polling skips cycle indefinitely, same infinite loop risk."""
        if not hasattr(CloudExecutor, "_poll_progress"):
            setattr(CloudExecutor, "_poll_progress", lambda self: {"progress": 50})
        with patch.object(CloudExecutor, "_poll_progress", side_effect=Exception("Corrupt JSON")):
            executor = self._executor()
            with patch("time.sleep", side_effect=Exception("Timeout")):
                with pytest.raises(Exception, match="Timeout"):
                    executor.execute(self._method_config(), self._sim_config())

    def test_cancel_flag_created_before_polling(self):
        """Cancel flag created before polling even starts → should exit immediately without downloading outputs."""
        if not hasattr(CloudExecutor, "_check_cancel_flag"):
            setattr(CloudExecutor, "_check_cancel_flag", lambda self: True)
        with patch.object(CloudExecutor, "_check_cancel_flag", return_value=True):
            executor = self._executor()
            result = executor.execute(self._method_config(), self._sim_config())
            assert result == "cancelled"

    def test_collect_outputs_and_cleanup_fails_mid_download(self):
        """_collect_outputs_and_cleanup fails mid-download (network drops) → some files downloaded, some not, sandbox not cleaned up."""
        if not hasattr(CloudExecutor, "_collect_outputs_and_cleanup"):
            setattr(CloudExecutor, "_collect_outputs_and_cleanup", lambda self: None)
        with patch.object(CloudExecutor, "_collect_outputs_and_cleanup", side_effect=Exception("Network error")):
            executor = self._executor()
            with pytest.raises(Exception, match="Network error"):
                executor.execute(self._method_config(), self._sim_config())

    def test_remote_sandbox_already_exists(self):
        """Remote sandbox directory already exists from a previous failed run with the same task_id → _build_singularity_image may behave unexpectedly."""
        if not hasattr(CloudExecutor, "_sandbox_exists"):
            setattr(CloudExecutor, "_sandbox_exists", lambda self: True)
        with patch.object(CloudExecutor, "_sandbox_exists", return_value=True):
            executor = self._executor()
            with pytest.raises(Exception):
                executor.execute(self._method_config(), self._sim_config())