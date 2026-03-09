from venv import logger

import paramiko
import time
import json
import os
import shutil
from typing import Any, Dict, List, Optional, Set
from .simulation_executor_interface import SimulationExecutor
import uuid
from pathlib import Path
import docker
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

def get_remote_file_path(image_name, job_id, filename):
    """Get the remote path for a file inside the singularity image."""
    return f"{image_name}_sif_{job_id}/app/{filename}"

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
        return b"Cloud job completed."

class CloudExecutor(SimulationExecutor):
    
    def __init__(self, hostname, username, password=None, key_path=None, entry_file=None, remote_work_dir="/app"):
        self.hostname = hostname
        self.username = username
        self.password = password
        self.key_path = key_path
        self.entry_file = entry_file
        self.remote_work_dir = remote_work_dir
        self.ssh_client = None


    def _connect(self):
        #close any stale connections
        self._disconnect()
        self.ssh_client = paramiko.SSHClient()
        self.ssh_client.load_system_host_keys()
        self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

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
            self.ssh_client.connect(**connect_kwargs)
            print(f"SSH connection established to {self.hostname} as {self.username}")

        except Exception as e:
            print(f"Error while connecting SSH: {e}")
    def _disconnect(self):
        """Quietly close the SSH client if one is open."""
        if self.ssh_client:
            try:
                self.ssh_client.close()
            except Exception:
                pass
            self.ssh_client = None


    def upload_file_via_sftp(self, local_path, remote_path):
        
        try:
            if self.ssh_client is None:
                raise RuntimeError("SSH client is not connected. Call _connect() first.")
            sftp = self.ssh_client.open_sftp()
            sftp.put(local_path, remote_path)
            sftp.close()
            print(f"Uploaded {local_path} → ~/{remote_path}")
        except Exception as e:
            print(f"Error while transfering file via SFTP: {e}")
            raise
    
    def _download_file_via_sftp(self, remote_path: str, local_path: str):
        """
        Download a single file from the remote host to a local path.
        remote_path is relative to the authenticated user's home directory.
        """
        if self.ssh_client is None:
            raise RuntimeError("SSH client is not connected.")
        sftp = self.ssh_client.open_sftp()
        try:
            sftp.get(remote_path, local_path)
        finally:
            sftp.close()
    
    def _list_remote_files(self, remote_dir: str) -> List[str]:
        """
        Return full relative remote paths for all non-hidden files in remote_dir.
        remote_dir is relative to the authenticated user's home directory.
        """
        if self.ssh_client is None:
            raise RuntimeError("SSH client is not connected.")
        sftp = self.ssh_client.open_sftp()
        try:
            entries = sftp.listdir_attr(remote_dir)
            return [
                f"{remote_dir}/{e.filename}"
                for e in entries
                if not e.filename.startswith(".")
            ]
        finally:
            sftp.close()

    def _delete_remote_path(self, remote_path: str):
        """
        Delete a file or directory (recursively) on the remote host.
        remote_path is relative to the authenticated user's home directory.
        """
        _, stdout, _ = self.ssh_client.exec_command(f"rm -rf {remote_path}")
        stdout.channel.recv_exit_status()   # block until done


    def build_singularity_image(self, singularity_image_name="sif_sandbox", image_tar_name=None):
            
        try:
            build_cmd = f"singularity build --sandbox {singularity_image_name} docker-archive://{image_tar_name}"
            print("Singularity image name is ", singularity_image_name, "\n")
            print("image tar name is ",image_tar_name,"\n")
            _, stdout, stderr = self.ssh_client.exec_command(build_cmd)
            build_output = stdout.read().decode()
            build_error = stderr.read().decode()
            print(f"Singularity build_output: {build_output}")
            print(f"Singularity build_error: {build_error}")
        except Exception as e:
            print(f"Error while building singularity image: {e}")
            raise


   

    def execute_singularity_image(self, singularity_image_name="sif_sandbox",input_json = "exampleInput_DG.json"):
            
        try:
            #this need to be refactored!!!!!  
            run_cmd = f"nohup singularity exec -w --pwd /app --env JSON_PATH=/app/{input_json} {singularity_image_name} python {self.entry_file} > {singularity_image_name}/app/singularity_run.log 2>&1 &"
            print(f"Running command: {run_cmd}")
            #this need to be refactored!!!!! Then test DE as well
            
            stdin, stdout, stderr = self.ssh_client.exec_command(run_cmd) 
            stdout.channel.recv_exit_status()
            print(f"Singularity launched in background.")
        except Exception as e:
            print(f"Error while executing singularity image: {e}")
            raise
    
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
    
    def poll_until_complete(
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
            cycle += 1
            print(f"[Polling] Cycle {cycle} (interval={poll_interval:.0f}s)")

            # 1 ── open a fresh SSH connection ────────────────────────────
            try:
                self._connect()
            except Exception as e:
                print(f"[Polling] SSH failed: {e}. Retry in {poll_interval:.0f}s.")
                self._disconnect()
                time.sleep(poll_interval)
                continue

            # 2 ── download and parse the remote JSON ─────────────────────
            try:
                tmp_path = local_json_path + ".tmp"
                self._download_file_via_sftp(remote_json_path, tmp_path)

                with open(tmp_path, "r") as fh:
                    json_data = json.load(fh)

                current_progress = self._parse_overall_progress(json_data)
                print(f"[Polling] Progress: {current_progress}%")

                # 3 ── only replace the local file when progress has changed
                if current_progress != last_progress:
                    shutil.move(tmp_path, local_json_path)
                    print(
                        f"[Polling] {last_progress} → {current_progress}%  "
                        f"(JSON written to {local_json_path})"
                    )
                    last_progress = current_progress
                else:
                    os.remove(tmp_path)

            except Exception as e:
                print(f"[Polling] Error reading remote JSON: {e}. Will retry.")
                self._disconnect()
                time.sleep(poll_interval)
                continue

            # 4 ── check for job completion ────────────────────────────────
            if last_progress is not None and last_progress >= 100:
                print("[Polling] Job complete — collecting outputs …")
                success = self._collect_outputs_and_cleanup(
                    remote_app_dir      = remote_app_dir,
                    local_uploads_dir   = local_uploads_dir,
                    remote_sandbox_path = remote_sandbox_path,
                    remote_tar_path     = remote_tar_path,
                )
                self._disconnect()
                return success

            # 5 ── disconnect, apply back-off, sleep ──────────────────────
            self._disconnect()

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

            sftp = self.ssh_client.open_sftp()
            try:
                for remote_file in output_files:
                    local_dest = os.path.join(local_uploads_dir, Path(remote_file).name)
                    print(f"[Cleanup] ~/{remote_file} → {local_dest}")
                    sftp.get(remote_file, local_dest)
            finally:
                sftp.close()

            print(f"[Cleanup] Removing sandbox : ~/{remote_sandbox_path}")
            self._delete_remote_path(remote_sandbox_path)

            if remote_tar_path:
                print(f"[Cleanup] Removing tar     : ~/{remote_tar_path}")
                self._delete_remote_path(remote_tar_path)

            print("[Cleanup] Done.")
            return True

        except Exception as e:
            print(f"[Cleanup] Error: {e}")
            return False

    def execute(self, method_config: Dict[str, Any], sim_config: Dict[str, Any]):
        self._connect()

        job_id = str(uuid.uuid4())
        image_name = method_config["container_image"].split(":")[0]  # Docker image name without the :latest tag
        tar_image_name = image_name + ".tar"
        local_tar_image_path = os.path.join(os.path.dirname(__file__), tar_image_name)

        self.upload_file_via_sftp(local_tar_image_path, tar_image_name)
        sandbox_name        = f"{image_name}_sif_{job_id}"
        remote_app_dir_path = f"{sandbox_name}/app"
        self.build_singularity_image(image_name + "_sif_" + job_id, tar_image_name)    

        env = sim_config.get("env", {})
        container_json_path = env.get("JSON_PATH")
        json_filename = Path(container_json_path).name
        msh_filename, geo_filename = get_filenames(container_json_path)

        remote_json_path = get_remote_file_path(image_name, job_id, json_filename)
        remote_msh_path = get_remote_file_path(image_name, job_id, msh_filename)
        remote_geo_path = get_remote_file_path(image_name, job_id, geo_filename)

        self.upload_file_via_sftp(container_json_path, remote_json_path)
        self.upload_file_via_sftp(get_local_file_path(container_json_path, msh_filename), remote_msh_path)
        self.upload_file_via_sftp(get_local_file_path(container_json_path, geo_filename), remote_geo_path)
        self.execute_singularity_image(singularity_image_name=image_name + "_sif_" + job_id, input_json=json_filename)
        self._disconnect()
        env               = sim_config.get("env", {})
        local_uploads_dir = str(Path(env.get("JSON_PATH")).parent)  # /app/uploads

        self.poll_until_complete(
            remote_json_path    = f"{remote_app_dir_path}/{json_filename}",
            local_uploads_dir   = local_uploads_dir,
            remote_app_dir      = remote_app_dir_path,
            remote_sandbox_path = sandbox_name,
            remote_tar_path     = tar_image_name,
        )

        return job_id, _CompletedJob()

