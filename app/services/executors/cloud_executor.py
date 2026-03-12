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
    """Update msh_path and geo_path in the JSON to only the file name."""
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
    """Get the local path for a file in the same directory as the JSON."""
    return os.path.join(os.path.dirname(json_path), filename)

def get_remote_file_path(remote_work_dir, image_name, task_id, filename):
    """Get the remote path for a file inside the singularity image."""
    return f"{remote_work_dir}/{image_name}_sif_{task_id}/app/{filename}"

class SSHCommandError(RuntimeError):
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
        return {"StatusCode": 0}

    def logs(self):
        return b"Cloud job submitted."

class CloudExecutor(SimulationExecutor):
    
    def __init__(self, hostname, username, remote_work_dir, password=None, key_path=None, entry_file=None):
        self.hostname = hostname
        self.username = username
        self.password = password
        self.key_path = key_path
        self.entry_file = entry_file
        self.remote_work_dir = remote_work_dir
        self.local_cancel_flag_path = None
        
    @contextmanager
    def _ssh_session(self):
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
            ssh.connect(**connect_kwargs)
            print(f"SSH connection established to {self.hostname} as {self.username}")
            yield ssh
        finally:
            ssh.close()

    def _run_remote_command(self, cmd: str) -> str:
        """
        Execute a command over SSH and return stdout.
        Raises SSHCommandError on failure. Assumes a pre-existing ssh session.
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
        """ Make a directory in the remote if it doesn't already exist. """
        self._run_remote_command(f"mkdir -p {path}")

    def _upload_file_via_sftp(self, local_path, remote_path):
        with self._ssh_session() as ssh_client:
            with ssh_client.open_sftp() as sftp:
                try:
                    sftp.put(local_path, remote_path)
                    print(f"Uploaded {local_path} → ~/{remote_path}")
                except Exception as e:
                    print(f"Error while transfering file via SFTP: {e}")
                    raise
            
    def _download_file_via_sftp(self, remote_path: str, local_path: str):
        """
        Download a single file from the remote host to a local path.
        remote_path is relative to the authenticated user's home directory.
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
        """
        Return full relative remote paths for all non-hidden files in remote_dir.
        remote_dir is relative to the authenticated user's home directory.
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
        full_path = os.path.join(self.remote_work_dir, remote_path)
        print(f"[Delete] Removing: {full_path}")
        _, stdout, stderr = self.ssh_client.exec_command(f"rm -rf {full_path}")
        exit_code = stdout.channel.recv_exit_status()
        if exit_code != 0:
            print(f"[Delete] Warning: rm -rf exited with code {exit_code}")
        else:
            print(f"[Delete] Successfully removed: {full_path}")
        """
        Delete a file or directory (recursively) on the remote host.
        remote_path is relative to the authenticated user's home directory, 
        or absolute. 
        """
        self._run_remote_command(f"rm -rf {remote_path}")


    def _build_singularity_image(self, sandbox_name="sif_sandbox", image_tar_name=None):
            
        build_cmd = f"singularity build --sandbox {self.remote_work_dir}/{sandbox_name} docker-archive://{self.remote_work_dir}/{image_tar_name}"
        print("Singularity image name is ", sandbox_name, "\n")
        print("image tar name is ",image_tar_name,"\n")
        build_output = self._run_remote_command(build_cmd)
        print(f"Singularity build_output: {build_output}")


    def _execute_singularity_image(self, sandbox_name="sif_sandbox",input_json = "exampleInput_DG.json"):
            
        #this need to be refactored!!!!!  
        run_cmd = f"nohup singularity exec -w --pwd /app --env JSON_PATH=/app/{input_json} {self.remote_work_dir}/{sandbox_name} python {self.entry_file} --image-name {sandbox_name} &> {self.remote_work_dir}/{sandbox_name}/app/singularity_run.log 2>&1 &"

        print(f"Running command: {run_cmd}")
        #this need to be refactored!!!!! Then test DE as well
        self._run_remote_command(run_cmd)
        print(f"Singularity launched in background.")

    
    @staticmethod
    def _parse_overall_progress(json_data: dict) -> Optional[float]:
        """
        Return the minimum ``percentage`` across all ``results`` entries.

        Using the minimum means the overall progress only reaches 100 when
        every source has finished computing.
        Returns None when the results field is absent or malformed.
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
        """
        Adaptively poll the cloud job until every result ``percentage`` == 100.

        Each cycle:
          - Opens a fresh SSH connection (no persistent socket).
          - Downloads the baked-in JSON and parses progress.
          - Writes the JSON to local_uploads_dir ONLY when the progress value
            has changed, so the frontend progress bar stays current throughout
            the run without unnecessary disk writes.
          - After POLL_FAST_PHASE_CYCLES cycles at POLL_INTERVAL_MIN seconds,
            the interval grows by POLL_BACKOFF_FACTOR up to POLL_INTERVAL_MAX.

        On completion (progress == 100):
          - Downloads all .json and .csv files from remote_app_dir.
          - Deletes the sandbox and tar from the cloud.

        Parameters
        ----------
        remote_json_path    : relative to user home, e.g.
                              dg_image_sif_<uuid>/app/exampleInput_DG.json
        local_uploads_dir   : absolute path in the local backend container,
                              e.g. /app/uploads  (bind-mounted to host)
        remote_app_dir      : relative to user home, e.g.
                              dg_image_sif_<uuid>/app
        remote_sandbox_path : relative to user home, e.g.
                              dg_image_sif_<uuid>
        remote_tar_path     : relative to user home, e.g. dg_image.tar
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

            # 2 ── download and parse the remote JSON (with retry on corrupt read)
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

    # ------------------------------------------------------------------
    # Output collection & cloud cleanup
    # ------------------------------------------------------------------
    def _cleanup(self, 
        remote_sandbox_path: str,
        remote_tar_path: Optional[str]):
        
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
        """
        Download .json and .csv output files from the remote sandbox's /app
        directory to local_uploads_dir, then delete the sandbox and tar.

        Only _OUTPUT_EXTENSIONS = {".json", ".csv"} are downloaded.
        Everything else (.py, .msh, .geo, .mat, .txt, etc.) is ignored.
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
        """ 
        Returns a list of PIDs for processes related to a particular
        Singularity container. Assumes an existing ssh session. 

        Raises RuntimeError if command fails.
        Returns an empty list if no processes are found
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
        """ 
        Kills the processes related to a Singularity container. Assumes
        an existing ssh session.

        Raises RuntimeError if command fails.  
        """

        pids = self._get_container_processes(sandbox_name)
        pid_str = " ".join(pids)
        self._run_remote_command(f"kill {pid_str}")
        print(f"Successfully killed PIDs: {pid_str}")
    
    def _should_cancel(self) -> bool:
        """
        Necessary for terminating the ssh polling loop, the Celery task
        in the backend cannot be revoked if that is still running. 
        """
        return os.path.exists(self.local_cancel_flag_path)
    

    def execute(self, method_config: Dict[str, Any], sim_config: Dict[str, Any]):

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
        """Cancel a Singularity container by its corresponding image name. """

        docker_image_name = cancelation_info["container_image"].split(":")[0]
        task_id = cancelation_info["task_id"]
        sandbox_name = f"{docker_image_name}_sif_{task_id}"
        remote_tar_path = f"{self.remote_work_dir}/{docker_image_name}.tar"
        remote_sandbox_path = f"{self.remote_work_dir}/{sandbox_name}"


        self._kill_container_processes(sandbox_name)
        self._cleanup(remote_sandbox_path, remote_tar_path)


