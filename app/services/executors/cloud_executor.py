from venv import logger
from contextlib import contextmanager
import threading
import socket
import paramiko
import time
import json
import os
import shutil
from typing import Any, Dict, List, Optional, Set
from .simulation_executor_interface import SimulationExecutor
from pathlib import Path
import json
paramiko.util.log_to_file("paramiko.log", level="DEBUG")

# ---------------------------------------------------------------------------
# Adaptive polling tunables
# ---------------------------------------------------------------------------
POLL_INTERVAL_MIN      = 15     # seconds — held for the first N cycles
POLL_INTERVAL_MAX      = 300    # seconds — ceiling (~5 min) for week-long jobs
POLL_BACKOFF_FACTOR    = 1.5    # multiplier applied after the fast phase
POLL_FAST_PHASE_CYCLES = 5      # how many cycles to keep the minimum interval

# Only these extensions are downloaded as simulation outputs at cleanup.
# The JSON is already kept up-to-date locally by the polling loop throughout
# the run, so it is included here to capture the final results-bearing version.
_OUTPUT_EXTENSIONS = {".json", ".csv"}

# The baked-in JSON filename inside the sandbox /app directory.
BAKED_IN_JSON_FILENAME = "exampleInput_DG.json"

def get_filenames(json_path):
    """Update msh_path and geo_path in the JSON to only the file name.

    Reads the JSON at the given path, strips the directory component from
    ``msh_path`` and ``geo_path`` so that only bare filenames remain, then
    writes the modified data back to the same file.

    Args:
        json_path (str): Absolute or relative path to the input JSON file.

    Returns:
        tuple : A ``(msh_filename, geo_filename)`` pair containing
            the bare file names extracted from the original paths.
    """
    with open(json_path, "r") as f:
        data = json.load(f)
    if "msh_path" in data:
        data["msh_path"] = Path(data["msh_path"]).name
    if "geo_path" in data:
        data["geo_path"] = Path(data["geo_path"]).name
    with open(json_path, "w") as f:
        json.dump(data, f, indent=4)
    return data["msh_path"], data["geo_path"]

def get_local_file_path(json_path, filename):
    """Get the local path for a file in the same directory as the JSON.

    Args:
        json_path (str): Path to the reference JSON file whose parent
            directory is used as the base.
        filename (str): Name of the file to locate in that directory.

    Returns:
        str: Absolute path formed by joining the parent directory of
            ``json_path`` with ``filename``.
    """
    return os.path.join(os.path.dirname(json_path), filename)

def get_remote_file_path(remote_work_dir, image_name, task_id, filename):
    """Get the remote path for a file inside the Singularity sandbox.

    Constructs the conventional sandbox path used by this executor:
    ``<remote_work_dir>/<image_name>_sif_<task_id>/app/<filename>``.

    Args:
        remote_work_dir (str): Root working directory on the remote host.
        image_name (str): Docker image name (without tag) used as a
            prefix for the sandbox directory.
        task_id (str): Unique task identifier appended to the sandbox
            directory name.
        filename (str): Name of the target file inside the sandbox's
            ``/app`` directory.

    Returns:
        str: Full remote path to the requested file.
    """
    return f"{remote_work_dir}/{image_name}_sif_{task_id}/app/{filename}"

class SSHCommandError(RuntimeError):
    """Raised when a remote SSH command exits with a non-zero status or when
    the SSH connection itself fails (authentication error, protocol error,
    or socket timeout).
    """
    pass

class _CompletedJob:
    """
    Minimal stub returned by CloudExecutor.execute() so that callers in
    simulation_service.py can call container.wait() / container.logs()
    without error.

    Since CloudExecutor.execute() already blocks until the job is fully done
    (via poll_until_complete), wait() is a no-op here.
    """
    def wait(self):
        """Block until the job finishes (no-op for already-completed jobs).

        Returns:
            dict: A status dict with ``{"StatusCode": 0}`` indicating
                successful completion.
        """
        return {"StatusCode": 0}

    def logs(self):
        """Return a placeholder log message for the completed cloud job.

        Returns:
            bytes: A static byte string indicating a cloud submission.
        """
        return b"Cloud job submitted."

class CloudExecutor(SimulationExecutor):
    """Executes simulations on a remote HPC cluster via SSH and Singularity.

    Uploads a Docker image tarball to a remote host, converts it into a
    Singularity sandbox, runs the simulation inside that sandbox, and
    adaptively polls the remote JSON output file for progress updates.
    On completion, output files are downloaded and the remote workspace is
    cleaned up.

    Attributes:
        hostname (str): Hostname or IP address of the remote HPC node.
        username (str): SSH username used for authentication.
        password (str | None): Password for password-based SSH auth.
        key_path (str | None): Path to a private key file for key-based auth.
        entry_file (str | None): Python entry-point script executed inside
            the Singularity container.
        remote_work_dir (str): Working directory on the remote host where
            the sandbox and output files are stored.
        local_cancel_flag_path (str | None): Path to a local sentinel file
            whose existence signals that the polling loop should stop.
    """
    
    def __init__(self, hostname, username, remote_work_dir, password=None, key_path=None, entry_file=None):
        """Initialise a CloudExecutor with SSH connection parameters.

        Args:
            hostname (str): Hostname or IP address of the remote HPC node.
            username (str): SSH username.
            remote_work_dir (str): Absolute path on the remote host used as
                the root working directory for all jobs.
            password (str, optional): SSH password. Defaults to ``None``.
            key_path (str, optional): Path to an SSH private key file.
                When provided, agent and ``look_for_keys`` are disabled.
                Defaults to ``None``.
            entry_file (str, optional): Python script executed as the
                container entry point. Defaults to ``None``.
        """
        self.hostname = hostname
        self.username = username
        self.password = password
        self.key_path = key_path
        self.entry_file = entry_file
        self.remote_work_dir = remote_work_dir
        self.local_cancel_flag_path = None
        
    @contextmanager
    def _ssh_session(self):
        """Context manager that yields an authenticated :class:`paramiko.SSHClient`.

        Opens a new SSH connection on entry and guarantees it is closed on
        exit, even if an exception is raised. Authentication preference order:

        1. Explicit private key (``key_path``) — disables agent and
           ``look_for_keys``.
        2. Password (``password``).
        3. SSH agent / default key search.

        Yields:
            paramiko.SSHClient: An open, authenticated SSH client.

        Raises:
            SSHCommandError: If authentication fails.
        """
        ssh = paramiko.SSHClient()
        ssh.load_system_host_keys()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            connect_kwargs = {
                            "hostname": self.hostname,
                            "username": self.username,
                            "look_for_keys": True,
                            "allow_agent": True,
                        }
            if self.key_path:
                connect_kwargs["key_filename"] = self.key_path
                connect_kwargs["allow_agent"] = False
                connect_kwargs["look_for_keys"] = False
            if self.password:
                connect_kwargs["password"] = self.password
            try:
                ssh.connect(**connect_kwargs)
            except paramiko.AuthenticationException:
                raise SSHCommandError("SSH authentication failed")
            print(f"SSH connection established to {self.hostname} as {self.username}")
            yield ssh
        finally:
            ssh.close()

    def _run_remote_command(self, cmd: str) -> str:
        """Execute a shell command on the remote host and return its stdout.

        Opens a fresh SSH session for each call. Waits for the remote
        process to exit and reads both stdout and stderr before returning.

        Args:
            cmd (str): Shell command to execute on the remote host.

        Returns:
            str: Stripped stdout output from the command.

        Raises:
            SSHCommandError: If the command exits with a non-zero status,
                if authentication fails, if an SSH protocol error occurs,
                or if the connection times out.
        """

        with self._ssh_session() as ssh_client:
            try:
                stdin, stdout, stderr = ssh_client.exec_command(cmd)

                exit_status = stdout.channel.recv_exit_status()

                output = stdout.read().decode().strip()
                errors = stderr.read().decode().strip()

                if exit_status != 0:
                    raise SSHCommandError(
                        f"Command failed ({exit_status}): {cmd}\n{errors}"
                    )
                return output

            except paramiko.AuthenticationException:
                raise SSHCommandError("SSH authentication failed")

            except paramiko.SSHException as e:
                raise SSHCommandError(f"SSH protocol error: {e}")

            except socket.timeout:
                raise SSHCommandError("SSH connection timed out")

            except Exception as e:
                raise SSHCommandError(f"Unexpected SSH error: {e}")

    def _mkdir_remote(self, path: str):
        """Create a directory on the remote host, including any parents.

        Equivalent to ``mkdir -p <path>`` on the remote machine. Succeeds
        silently if the directory already exists.

        Args:
            path (str): Absolute or relative path to create on the remote host.

        Raises:
            SSHCommandError: If the remote command fails.
        """
        self._run_remote_command(f"mkdir -p {path}")

    def _upload_file_via_sftp(self, local_path, remote_path):
        """Upload a single local file to the remote host over SFTP.

        Args:
            local_path (str): Absolute or relative path to the local source file.
            remote_path (str): Destination path on the remote host. The parent
                directory must already exist.

        Raises:
            Exception: Re-raises any SFTP transfer exception after logging it.
        """
        with self._ssh_session() as ssh_client:
            with ssh_client.open_sftp() as sftp:
                try:
                    sftp.put(local_path, remote_path)
                    print(f"Uploaded {local_path} → ~/{remote_path}")
                except Exception as e:
                    print(f"Error while transfering file via SFTP: {e}")
                    raise
            
    def _download_file_via_sftp(self, remote_path: str, local_path: str):
        """Download a single file from the remote host to a local path over SFTP.

        Args:
            remote_path (str): Path to the file on the remote host, relative
                to the authenticated user's home directory.
            local_path (str): Absolute local destination path where the file
                will be saved.

        Raises:
            Exception: Re-raises any SFTP transfer exception after logging it.
        """
        with self._ssh_session() as ssh_client:
            with ssh_client.open_sftp() as sftp:
                try:
                    sftp = ssh_client.open_sftp()
                    sftp.get(remote_path, local_path)
                except Exception as e:
                    print(f"Error while downloading file via SFTP: {e}")
                    raise
    
    def _list_remote_files(self, remote_dir: str) -> List[str]:
        """List all non-hidden files in a remote directory.

        Hidden files (those whose names start with ``.``) are excluded.

        Args:
            remote_dir (str): Path to the remote directory to list, relative
                to the authenticated user's home directory.

        Returns:
            List[str]: Full remote paths (``remote_dir/filename``) for each
                non-hidden file found in the directory.

        Raises:
            Exception: Re-raises any SFTP error after logging it.
        """
        with self._ssh_session() as ssh_client:
            with ssh_client.open_sftp() as sftp:
                try:
                    entries = sftp.listdir_attr(remote_dir)
                    return [
                        f"{remote_dir}/{e.filename}"
                        for e in entries
                        if not e.filename.startswith(".")
                    ]
                except Exception as e:
                    print(f"Error while listing remote files file via SFTP: {e}")
                    raise


    def _delete_remote_path(self, remote_path: str):
        """Delete a file or directory (recursively) on the remote host.

        Equivalent to ``rm -rf <remote_path>``. No error is raised if the
        path does not exist.

        Args:
            remote_path (str): Absolute or home-relative path on the remote
                host to delete.

        Raises:
            SSHCommandError: If the remote ``rm`` command itself fails.
        """
        self._run_remote_command(f"rm -rf {remote_path}")


    def _build_singularity_image(self, sandbox_name="sif_sandbox", image_tar_name=None):
        """Convert a Docker tarball into a writable Singularity sandbox on the remote host.

        Runs ``singularity build --sandbox`` using the provided Docker archive
        as the source. The resulting sandbox directory is placed under
        :attr:`remote_work_dir`.

        Args:
            sandbox_name: Name of the sandbox directory to
                create inside :attr:`remote_work_dir`.
                Defaults to ``"sif_sandbox"``.
            image_tar_name (str, optional): Filename of the Docker image
                tarball already present in :attr:`remote_work_dir`.
                Defaults to ``None``.

        Raises:
            SSHCommandError: If the ``singularity build`` command fails.
        """
            
        build_cmd = f"singularity build --sandbox {self.remote_work_dir}/{sandbox_name} docker-archive://{self.remote_work_dir}/{image_tar_name}"
        print("Singularity image name is ", sandbox_name, "\n")
        print("image tar name is ",image_tar_name,"\n")
        build_output = self._run_remote_command(build_cmd)
        print(f"Singularity build_output: {build_output}")


    def _execute_singularity_image(self, sandbox_name="sif_sandbox",input_json = "exampleInput_DG.json"):
        """Launch the simulation inside a Singularity sandbox in the background.

        Runs the container's entry-point script via ``singularity exec`` with
        ``nohup`` so that the process persists after the SSH session closes.
        Stdout and stderr are redirected to ``singularity_run.log`` inside the
        sandbox's ``/app`` directory.

        Args:
            sandbox_name (str, optional): Name of the Singularity sandbox
                directory inside :attr:`remote_work_dir`.
                Defaults to ``"sif_sandbox"``.
            input_json (str, optional): Filename of the input JSON to pass
                via the ``JSON_PATH`` environment variable inside the container.
                Defaults to ``"exampleInput_DG.json"``.

        Raises:
            SSHCommandError: If the ``singularity exec`` command fails to
                launch (note: because it runs under ``nohup &``, failures
                inside the container will not surface here).
        """
            
        run_cmd = f"nohup singularity exec -w --pwd /app --env JSON_PATH=/app/{input_json} {self.remote_work_dir}/{sandbox_name} python {self.entry_file} --image-name {sandbox_name} &> {self.remote_work_dir}/{sandbox_name}/app/singularity_run.log 2>&1 &"

        print(f"Running command: {run_cmd}")

        self._run_remote_command(run_cmd)
        print(f"Singularity launched in background.")

    
    @staticmethod
    def _parse_overall_progress(json_data: dict) -> Optional[float]:
        """Return the minimum completion percentage across all result entries.

        Uses the minimum so that overall progress only reaches 100 when
        every source has finished computing.

        Args:
            json_data (dict): Parsed JSON dictionary expected to contain a
                ``"results"`` key whose value is a list of dicts, each with
                a ``"percentage"`` field.

        Returns:
            value: The minimum ``percentage`` value found, or ``None``
                if ``"results"`` is absent, empty, or malformed.
        """
        try:
            results = json_data.get("results", [])
            if not results:
                return None
            return min(r.get("percentage", 0) for r in results)
        except Exception:
            return None
    
    def _poll_until_complete(
        self,
        remote_json_path: str,
        local_uploads_dir: str,
        remote_app_dir: str,
        remote_sandbox_path: str,
        remote_tar_path: Optional[str] = None,
    ) -> bool:
        """Adaptively poll the remote job until all results reach 100 % progress.

        Opens a fresh SSH connection each cycle to download the output JSON,
        parse progress, and—if progress changed—persist the JSON locally so
        the frontend progress bar stays current. The polling interval starts
        at :data:`POLL_INTERVAL_MIN` seconds and, after
        :data:`POLL_FAST_PHASE_CYCLES` cycles, grows by
        :data:`POLL_BACKOFF_FACTOR` on each subsequent cycle up to
        :data:`POLL_INTERVAL_MAX`. The loop exits early if a local cancel
        flag file is detected (see :meth:`_should_cancel`).

        On completion, calls :meth:`_collect_outputs_and_cleanup` to download
        output files and remove the remote sandbox and tarball.

        Args:
            remote_json_path: Remote path to the output JSON file,
                relative to the user's home directory (e.g.
                ``dg_image_sif_<uuid>/app/exampleInput_DG.json``).
            local_uploads_dir: Absolute local directory where the JSON
                and other output files will be written (e.g. ``/app/uploads``).
            remote_app_dir: Remote path to the sandbox ``/app`` directory
                (e.g. ``dg_image_sif_<uuid>/app``).
            remote_sandbox_path: Remote path to the sandbox root (e.g.
                ``dg_image_sif_<uuid>``), used for cleanup.
            remote_tar_path: Remote path to the Docker image
                tarball, used for cleanup. Defaults to ``None``.

        Returns:
            bool: ``True`` if outputs were collected and the remote workspace
                was cleaned up successfully; ``False`` if an error occurred
                during :meth:`_collect_outputs_and_cleanup`.
        """
        local_json_path = os.path.join(local_uploads_dir, Path(remote_json_path).name)

        last_progress: Optional[float] = None
        poll_interval = float(POLL_INTERVAL_MIN)
        cycle = 0

        print(f"[Polling] Starting — remote JSON : {remote_json_path}")
        print(f"[Polling]            local dest   : {local_json_path}")

        while True:
            if self._should_cancel():
                print("[Polling] Cancel requested. Exiting.")
                return
            
            cycle += 1
            print(f"[Polling] Cycle {cycle} (interval={poll_interval:.0f}s)")

            # download and parse the remote JSON (with retry on corrupt read)
            json_data = None
            tmp_path = local_json_path + ".tmp"
            MAX_PARSE_RETRIES = 3

            for attempt in range(MAX_PARSE_RETRIES):
                try:
                    self._download_file_via_sftp(remote_json_path, tmp_path)
                    with open(tmp_path, "r") as fh:
                        json_data = json.load(fh)
                    break  # success — exit retry loop
                except json.JSONDecodeError as e:
                    print(f"[Polling] JSON parse failed (attempt {attempt + 1}/{MAX_PARSE_RETRIES}): {e}")
                    if attempt < MAX_PARSE_RETRIES - 1:
                        print(f"[Polling] Simulation may still be writing — retrying in 5s...")
                        time.sleep(5)
                except Exception as e:
                    print(f"[Polling] Download error: {e}. Will retry next cycle.")
                    break

            if json_data is None:
                print(f"[Polling] Could not read JSON after {MAX_PARSE_RETRIES} attempts. Skipping cycle.")
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                time.sleep(poll_interval)
                continue

            current_progress = self._parse_overall_progress(json_data)
            print(f"[Polling] Progress: {current_progress}%")

            # only replace the local file when progress has changed
            if current_progress != last_progress:
                shutil.move(tmp_path, local_json_path)
                print(
                    f"[Polling] {last_progress} → {current_progress}%  "
                    f"(JSON written to {local_json_path})"
                )
                last_progress = current_progress
            else:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

            if last_progress is not None and last_progress >= 100:
                print("[Polling] Job complete — collecting outputs …")
                success = self._collect_outputs_and_cleanup(
                    remote_app_dir      = remote_app_dir,
                    local_uploads_dir   = local_uploads_dir,
                    remote_sandbox_path = remote_sandbox_path,
                    remote_tar_path     = remote_tar_path,
                )

                return success

            if cycle >= POLL_FAST_PHASE_CYCLES:
                poll_interval = min(
                    poll_interval * POLL_BACKOFF_FACTOR,
                    POLL_INTERVAL_MAX,
                )

            print(f"[Polling] Sleeping {poll_interval:.0f}s …\n")
            time.sleep(poll_interval)

    def _cleanup(self, 
        remote_sandbox_path: str,
        remote_tar_path: Optional[str]):
        """Delete the remote Singularity sandbox and optionally the image tarball.

        Args:
            remote_sandbox_path (str): Path to the sandbox directory on the
                remote host to remove recursively.
            remote_tar_path (str | None): Path to the Docker image tarball on
                the remote host. Pass ``None`` to skip tar removal.

        Raises:
            SSHCommandError: If either ``rm -rf`` command fails.
        """
        print(f"[Cleanup] Removing sandbox : ~/{remote_sandbox_path}")
        self._delete_remote_path(remote_sandbox_path)

        if remote_tar_path:
            print(f"[Cleanup] Removing tar     : ~/{remote_tar_path}")
            self._delete_remote_path(remote_tar_path)
        

    def _collect_outputs_and_cleanup(
        self,
        remote_app_dir: str,
        local_uploads_dir: str,
        remote_sandbox_path: str,
        remote_tar_path: Optional[str],
    ) -> bool:
        """Download simulation outputs from the remote sandbox and clean up.

        Lists all files in ``remote_app_dir``, filters to those whose
        extension is in :data:`_OUTPUT_EXTENSIONS` (``{".json", ".csv"}``),
        downloads them to ``local_uploads_dir``, then calls :meth:`_cleanup`
        to remove the remote sandbox and tarball.

        Args:
            remote_app_dir (str): Remote path to the sandbox ``/app``
                directory containing simulation output files.
            local_uploads_dir (str): Absolute local directory where output
                files will be saved. Created if it does not exist.
            remote_sandbox_path (str): Remote path to the sandbox root,
                passed to `_cleanup`.
            remote_tar_path: Remote path to the Docker image
                tarball, passed to :meth:`_cleanup`. Pass ``None`` to skip.

        Returns:
            bool: ``True`` if all outputs were downloaded and the remote
                workspace was cleaned up without error; ``False`` otherwise.
        """
        try:
            all_remote_files = self._list_remote_files(remote_app_dir)

            output_files = [
                f for f in all_remote_files
                if Path(f).suffix in _OUTPUT_EXTENSIONS
            ]

            print(f"[Cleanup] {len(output_files)} output file(s) to download:")
            for f in output_files:
                print(f"[Cleanup]   ~/{f}")

            os.makedirs(local_uploads_dir, exist_ok=True)

            with self._ssh_session() as ssh_client:
                with ssh_client.open_sftp() as sftp:
                    try:
                        for remote_file in output_files:
                            local_dest = os.path.join(local_uploads_dir, Path(remote_file).name)
                            print(f"[Cleanup] ~/{remote_file} → {local_dest}")
                            sftp.get(remote_file, local_dest)
                    except Exception as e:
                        print(f"[Cleanup] Error while downloading files via SFTP: {e}")
                        raise

            self._cleanup(remote_sandbox_path, remote_tar_path)

            print("[Cleanup] Done.")
            return True

        except Exception as e:
            print(f"[Cleanup] Error: {e}")
            return False
    
    def _get_container_processes(self, sandbox_name: str) -> List[str]:
        """Return the PIDs of all remote processes associated with a sandbox.

        Uses ``pgrep`` scoped to the current SSH user so that only processes
        belonging to this executor are returned. Both the parent Singularity
        process and any Python child process inside the container match
        because ``sandbox_name`` appears in their command lines.

        Args:
            sandbox_name (str): Name of the Singularity sandbox whose
                processes should be found.

        Returns:
            List[str]: List of PID strings. Empty list if no matching
                processes are running.

        Raises:
            SSHCommandError: If the ``pgrep`` command itself fails for a
                reason other than finding no matches.
        """
        processes: List[str] = []
        # only get processes associated with the current user.
        # both parent singularity process and the python process inside
        # the container have the sandbox name in the command.
        output = self._run_remote_command(
            f"pgrep -u {self.username} -f {sandbox_name}")
        if output:
            processes = output.split("\n") 

        print(f"Found process(es) with PID(s): {processes}")
        return processes 

    def _kill_container_processes(self, sandbox_name: str):
        """Kill all remote processes associated with a Singularity sandbox.

        Retrieves PIDs via :meth:`_get_container_processes`, then sends
        ``SIGTERM`` to each one via a single ``kill`` invocation.

        Args:
            sandbox_name: Name of the Singularity sandbox whose
                processes should be terminated.

        Raises:
            SSHCommandError: If :meth:`_get_container_processes` or the
                ``kill`` command fails.
        """

        pids = self._get_container_processes(sandbox_name)
        pid_str = " ".join(pids)
        self._run_remote_command(f"kill {pid_str}")
        print(f"Successfully killed PIDs: {pid_str}")
    
    def _should_cancel(self) -> bool:
        """Check whether a local cancellation sentinel file exists.

        The polling loop calls this method each cycle. The local backend
        creates the sentinel file when the user cancels the simulation via
        the frontend, allowing the Celery task to stop the blocking poll.

        Returns:
            bool: ``True`` if the cancel flag file exists; ``False`` otherwise.
        """
        return os.path.exists(self.local_cancel_flag_path)
    

    def execute(self, method_config: Dict[str, Any], sim_config: Dict[str, Any]):
        """Run a simulation on the remote HPC cluster end-to-end.

        Orchestrates the full lifecycle:

        1. Creates the remote working directory.
        2. Uploads the Docker image tarball.
        3. Builds a writable Singularity sandbox from the tarball.
        4. Uploads the input JSON, mesh, and geometry files.
        5. Launches the simulation inside the sandbox in the background.
        6. Blocks via :meth:`_poll_until_complete` until the job finishes,
           updating the local JSON as progress changes.
        7. Downloads output files and removes the remote workspace.

        Args:
            method_config (Dict[str, Any]): Executor configuration dict with keys
                ``container_image`` (str, Docker image in ``name:tag`` format, tag is
                stripped to derive sandbox and tarball names) and ``task_id`` (str,
                unique identifier appended to the sandbox name).
            sim_config (Dict[str, Any]): Simulation configuration dict with key
                ``env`` (dict), an environment variable map containing at least
                ``JSON_PATH`` — the absolute local path to the input JSON file.

        Returns:
            _CompletedJob: A stub object whose wait() and logs() methods satisfy
                the simulation_service.py caller contract.
        """

        self._mkdir_remote(self.remote_work_dir)

        docker_image_name = method_config["container_image"].split(":")[0]  # Docker image name without the :latest tag
        task_id = method_config["task_id"]
        tar_image_name = docker_image_name + ".tar"
        local_tar_image_path = os.path.join(os.path.dirname(__file__), tar_image_name)

        self._upload_file_via_sftp(
            local_tar_image_path, 
            f"{self.remote_work_dir}/{tar_image_name}")
        
        sandbox_name = f"{docker_image_name}_sif_{task_id}"

        self._build_singularity_image(sandbox_name, tar_image_name)    

        env = sim_config.get("env", {})
        container_json_path = env.get("JSON_PATH")
        json_filename = Path(container_json_path).name
        msh_filename, geo_filename = get_filenames(container_json_path)

        remote_json_path = get_remote_file_path(
            self.remote_work_dir, docker_image_name, task_id, json_filename)
        remote_msh_path = get_remote_file_path(
            self.remote_work_dir, docker_image_name, task_id, msh_filename)
        remote_geo_path = get_remote_file_path(
            self.remote_work_dir, docker_image_name, task_id, geo_filename)

        self._upload_file_via_sftp(
            container_json_path, 
            remote_json_path)
        
        self._upload_file_via_sftp(
            get_local_file_path(container_json_path, msh_filename), 
            remote_msh_path)
        
        self._upload_file_via_sftp(
            get_local_file_path(container_json_path, geo_filename), 
            remote_geo_path)
        
        self._execute_singularity_image(
            sandbox_name=sandbox_name, input_json=json_filename)

        env = sim_config.get("env", {})
        local_uploads_dir = str(Path(env.get("JSON_PATH")).parent)  # /app/uploads

        # if this file exists, polling stops. Local backend creates this file
        # when simulation is canceled via the frontend, polling stops, and
        # Celery task can be stopped. 
        self.local_cancel_flag_path = f"{local_uploads_dir}/{task_id}.cancel"

        remote_app_dir_path = f"{self.remote_work_dir}/{sandbox_name}/app"

        self._poll_until_complete(
            remote_json_path    = f"{remote_app_dir_path}/{json_filename}",
            local_uploads_dir   = local_uploads_dir,
            remote_app_dir      = remote_app_dir_path,
            remote_sandbox_path = f"{self.remote_work_dir}/{sandbox_name}",
            remote_tar_path     = f"{self.remote_work_dir}/{tar_image_name}",
        )

        return _CompletedJob()

    def cancel(self, cancelation_info: Dict[str, Any]):
        """Cancel a running Singularity job and clean up the remote workspace.

        Kills all remote processes associated with the sandbox derived from
        ``cancelation_info``, then removes the sandbox directory and image
        tarball from the remote host.

        Args:
            cancelation_info (Dict[str, Any]): Cancellation metadata dict.
                Expected keys:

                * ``"container_image"`` (str): Docker image reference in
                  ``name:tag`` format. The tag is stripped to derive the
                  sandbox name.
                * ``"task_id"`` (str): Unique task identifier used to locate
                  the correct sandbox directory.

        Raises:
            SSHCommandError: If killing the remote processes or deleting
                the remote paths fails.
        """

        docker_image_name = cancelation_info["container_image"].split(":")[0]
        task_id = cancelation_info["task_id"]
        sandbox_name = f"{docker_image_name}_sif_{task_id}"
        remote_tar_path = f"{self.remote_work_dir}/{docker_image_name}.tar"
        remote_sandbox_path = f"{self.remote_work_dir}/{sandbox_name}"


        self._kill_container_processes(sandbox_name)
        self._cleanup(remote_sandbox_path, remote_tar_path)


