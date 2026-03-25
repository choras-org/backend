# CHORAS — Test Results Document
## CHORAS Scalability Project - EngD 2026

**Version:** 2.0
**Status:** Draft
**Date:** 2026-03-17
**Related Documents:** `Testing Strategy.md`, `Test Design v6.md`
**Maintained by:** Test Manager
**CI Environment:** GitHub Actions · Ubuntu Latest · Python 3.10.20 · pytest 9.0.2
**Database:** PostgreSQL 15 (CI) · PostgreSQL (Local Docker)

---

## 1. Summary

| Metric | Value |
|---|---|
| **Total Tests Collected** | 120 |
| **Passed** | 120 |
| **Failed** | 0 |
| **Expected Failures (xfail)** | 1 |
| **Unexpected Passes (xpassed)** | 2 |
| **Skipped** | 0 |
| **Last Run Date** | 2026-03-17 |
| **Last Run Duration** | ~7s |

> **Note on xpassed:** B12 and B13 in `test_cloud_executor_final.py` are marked
> `xfail` for known bugs (no stall timeout, no `POLL_MAX_FAILED_CYCLES`). They
> unexpectedly pass because the `time.sleep` side-effect trick forces the loop
> to exit. The `xfail` markers must remain until the real fixes are implemented.

---

## 2. Results by Test File

### 2.1 `tests/integration/test_cloud_executor.py`

**Purpose:** Original bad day tests for `CloudExecutor.execute()`.

| # | Test Name | Partition | Status |
|---|---|---|---|
| 1 | `test_ssh_authentication_fails` | EP-S2 | ✅ Pass |
| 2 | `test_sftp_upload_tar_fails_halfway` | EP-S4 | ✅ Pass |
| 3 | `test_build_singularity_image_fails` | EP-S5 | ✅ Pass |
| 4 | `test_remote_json_never_reaches_100` | EP-P5 | ✅ Pass |
| 5 | `test_remote_json_always_corrupt` | EP-P4 | ✅ Pass |
| 6 | `test_cancel_flag_created_before_polling` | EP-P6 | ✅ Pass |
| 7 | `test_collect_outputs_and_cleanup_fails_mid_download` | EP-S4 | ✅ Pass |
| 8 | `test_build_fails_when_remote_sandbox_already_exists` | EP-S6 | ✅ Pass |

**File Total: 8 passed, 0 failed**

---

### 2.2 `tests/integration/test_cloud_executor_final.py`

**Purpose:** Full coverage of all `CloudExecutor` internal methods.

| # | Test Name | Partition | Status |
|---|---|---|---|
| 1 | `TestParseOverallProgress::test_multiple_results_returns_minimum` | EP-P1 | ✅ Pass |
| 2 | `TestParseOverallProgress::test_single_result_at_100` | EP-P2 | ✅ Pass |
| 3 | `TestParseOverallProgress::test_empty_results_list_returns_none` | EP-C5 | ✅ Pass |
| 4 | `TestParseOverallProgress::test_results_entry_missing_percentage_key` | EP-C5 | ✅ Pass |
| 5 | `TestParseOverallProgress::test_results_is_not_a_list_returns_none` | EP-C5 | ✅ Pass |
| 6 | `TestGetFilenames::test_full_paths_stripped_to_filenames` | EP-C1 | ✅ Pass |
| 7 | `TestGetFilenames::test_missing_msh_path_raises_key_error` | EP-C5 | ✅ Pass |
| 8 | `TestGetFilenames::test_missing_geo_path_raises_key_error` | EP-C5 | ✅ Pass |
| 9 | `TestShouldCancel::test_returns_false_when_no_cancel_flag` | EP-P1 | ✅ Pass |
| 10 | `TestShouldCancel::test_returns_true_when_cancel_flag_exists` | EP-P6 | ✅ Pass |
| 11 | `TestRunRemoteCommand::test_successful_command_returns_stdout` | EP-S1 | ✅ Pass |
| 12 | `TestRunRemoteCommand::test_ssh_authentication_fails_raises_ssh_command_error` | EP-S2 | ✅ Pass |
| 13 | `TestRunRemoteCommand::test_ssh_connection_timeout_raises_ssh_command_error` | EP-S3 | ✅ Pass |
| 14 | `TestRunRemoteCommand::test_non_zero_exit_status_raises_ssh_command_error` | EP-S1 | ✅ Pass |
| 15 | `TestUploadFileViaSftp::test_successful_upload_calls_sftp_put` | EP-S1 | ✅ Pass |
| 16 | `TestUploadFileViaSftp::test_sftp_upload_fails_halfway_raises_exception` | EP-S4 | ✅ Pass |
| 17 | `TestBuildSingularityImage::test_successful_build_runs_correct_command` | EP-S1 | ✅ Pass |
| 18 | `TestBuildSingularityImage::test_disk_full_on_remote_raises_ssh_command_error` | EP-S5 | ✅ Pass |
| 19 | `TestBuildSingularityImage::test_sandbox_already_exists_raises_ssh_command_error` | EP-S6 | ✅ Pass |
| 20 | `TestExecuteSingularityImage::test_launches_singularity_in_background` | EP-S1 | ✅ Pass |
| 21 | `TestExecuteSingularityImage::test_command_includes_entry_file` | EP-S1 | ✅ Pass |
| 22 | `TestPollUntilComplete::test_progress_reaches_100_calls_cleanup_and_returns_true` | EP-P1, EP-P2 | ✅ Pass |
| 23 | `TestPollUntilComplete::test_json_only_written_locally_when_progress_changes` | EP-P1 | ✅ Pass |
| 24 | `TestPollUntilComplete::test_corrupt_json_retries_then_recovers` | EP-P3 | ✅ Pass |
| 25 | `TestPollUntilComplete::test_cancel_flag_before_polling_exits_immediately` | EP-P6 | ✅ Pass |
| 26 | `TestPollUntilComplete::test_cancel_flag_mid_polling_stops_at_next_cycle` | EP-P7 | ✅ Pass |
| 27 | `TestPollUntilComplete::test_progress_stuck_raises_runtime_error` | EP-P5 | ⚠️ xpassed — DEF-001 |
| 28 | `TestPollUntilComplete::test_json_always_corrupt_raises_runtime_error` | EP-P4 | ⚠️ xpassed — DEF-002 |
| 29 | `TestCollectOutputsAndCleanup::test_downloads_only_json_and_csv_ignores_others` | EP-O1 | ✅ Pass |
| 30 | `TestCollectOutputsAndCleanup::test_cleanup_called_after_successful_download` | EP-O1 | ✅ Pass |
| 31 | `TestCollectOutputsAndCleanup::test_sftp_download_failure_returns_false_no_cleanup` | EP-S4 | ✅ Pass |
| 32 | `TestExecuteHappyPath::test_execute_returns_completed_job` | EP-S1, EP-M2 | ✅ Pass |
| 33 | `TestExecuteHappyPath::test_execute_calls_poll_until_complete` | EP-S1 | ✅ Pass |
| 34 | `TestExecuteHappyPath::test_execute_uploads_tar_file` | EP-S1 | ✅ Pass |
| 35 | `TestExecuteHappyPath::test_execute_strips_tag_from_sandbox_name` | EP-S1 | ✅ Pass |
| 36 | `TestCancel::test_cancel_kills_processes_and_cleans_up` | EP-S1 | ✅ Pass |
| 37 | `TestCancel::test_cancel_constructs_correct_sandbox_name` | EP-S1 | ✅ Pass |

**File Total: 35 passed, 0 failed, 2 xpassed**

---

### 2.3 `tests/integration/test_executor_factory.py`

**Purpose:** Tests `executor_factory()` routing and edge cases.

| # | Test Name | Partition | Status |
|---|---|---|---|
| 1 | `test_invalid_resource_type_raises_value_error` | EP-E3 | ✅ Pass |
| 2 | `test_discover_container_image_none_calls_cloud_executor` | EP-M5 | ✅ Pass |
| 3 | `test_discover_entry_file_none_cloud_executor_entry_file_none` | EP-M6 | ✅ Pass |

**File Total: 3 passed, 0 failed**

---

### 2.4 `tests/integration/test_local_executor.py`

**Purpose:** Original bad day tests for `LocalExecutor.execute()`.

| # | Test Name | Partition | Status |
|---|---|---|---|
| 1 | `test_docker_image_not_found` | EP-D2 | ✅ Pass |
| 2 | `test_docker_socket_not_available` | EP-D2 | ✅ Pass |
| 3 | `test_json_path_missing` | EP-C2 | ✅ Pass |
| 4 | `test_no_matching_mount` | EP-D4 | ✅ Pass |
| 5 | `test_container_exits_nonzero_obj_missing` | EP-D5 | ✅ Pass — documents known bug |
| 6 | `test_duplicate_container_name_conflict` | EP-D3 | ✅ Pass |

**File Total: 6 passed, 0 failed**

---

### 2.5 `tests/integration/test_local_executor_final.py`

**Purpose:** Full coverage of all `LocalExecutor` methods.

| # | Test Name | Partition | Status |
|---|---|---|---|
| 1 | `TestGetHostPathForContainerPath::test_resolves_exact_mount_destination` | EP-D1 | ✅ Pass |
| 2 | `TestGetHostPathForContainerPath::test_resolves_subdirectory_of_mount` | EP-D1 | ✅ Pass |
| 3 | `TestGetHostPathForContainerPath::test_raises_when_no_mount_covers_path` | EP-D4 | ✅ Pass |
| 4 | `TestGetHostPathForContainerPath::test_raises_when_docker_client_fails` | EP-D2 | ✅ Pass |
| 5 | `TestGetHostPathForContainerPath::test_uses_hostname_to_identify_container` | EP-D1 | ✅ Pass |
| 6 | `TestGetHostPathForContainerPath::test_normalises_backslashes_to_forward_slashes` | EP-D1 | ✅ Pass |
| 7 | `TestLocalExecutorInit::test_default_work_dir_from_env` | EP-D1 | ✅ Pass |
| 8 | `TestLocalExecutorInit::test_default_work_dir_fallback` | EP-D1 | ✅ Pass |
| 9 | `TestLocalExecutorInit::test_explicit_work_dir` | EP-D1 | ✅ Pass |
| 10 | `TestLocalExecutorExecuteHappyPath::test_returns_container_object` | EP-D1, EP-M2 | ✅ Pass |
| 11 | `TestLocalExecutorExecuteHappyPath::test_passes_correct_image_to_containers_run` | EP-D1 | ✅ Pass |
| 12 | `TestLocalExecutorExecuteHappyPath::test_passes_env_to_containers_run` | EP-D1, EP-C1 | ✅ Pass |
| 13 | `TestLocalExecutorExecuteHappyPath::test_volume_mount_uses_resolved_host_path` | EP-D1 | ✅ Pass |
| 14 | `TestLocalExecutorExecuteHappyPath::test_container_runs_detached` | EP-D1 | ✅ Pass |
| 15 | `TestLocalExecutorExecuteHappyPath::test_de_method_on_simple_geometry` | EP-M1, EP-G1 | ✅ Pass |
| 16 | `TestLocalExecutorExecuteHappyPath::test_dg_method_on_moderate_geometry` | EP-M2, EP-G2 | ✅ Pass |
| 17 | `TestLocalExecutorExecuteHappyPath::test_new_method_on_complex_geometry` | EP-M3, EP-G3 | ✅ Pass |
| 18 | `TestLocalExecutorExecuteHappyPath::test_containers_run_called_exactly_once` | EP-D1 | ✅ Pass |
| 19 | `TestLocalExecutorCancel::test_cancel_kills_and_removes_running_container` | EP-D1 | ✅ Pass |
| 20 | `TestLocalExecutorCancel::test_cancel_container_not_found_does_not_raise` | EP-D2 | ✅ Pass |

**File Total: 20 passed, 0 failed**

---

### 2.6 `tests/integration/test_missing_cases.py`

**Purpose:** Gap coverage for tests not in original files.

| # | Test Name | Partition | Status |
|---|---|---|---|
| 1 | `TestGetLocalFilePath::test_joins_dirname_and_filename` | EP-C1 | ✅ Pass |
| 2 | `TestGetLocalFilePath::test_works_with_nested_directory` | EP-C1 | ✅ Pass |
| 3 | `TestGetRemoteFilePath::test_constructs_correct_remote_path` | EP-C1 | ✅ Pass |
| 4 | `TestCompletedJob::test_wait_returns_zero_status_code` | EP-O1 | ✅ Pass |
| 5 | `TestCompletedJob::test_logs_returns_bytes` | EP-O1 | ✅ Pass |
| 6 | `TestCloudExecutorInit::test_stores_all_constructor_parameters` | EP-S1 | ✅ Pass |
| 7 | `TestCloudExecutorInit::test_local_cancel_flag_path_initially_none` | EP-S1 | ✅ Pass |
| 8 | `TestLocalExecutorInitJobs::test_jobs_dict_initialised_empty` | EP-D1 | ⚠️ xfail — `_jobs` not in `__init__` |
| 9 | `TestDownloadFileViaSftp::test_successful_download_calls_sftp_get` | EP-S1 | ✅ Pass |
| 10 | `TestListRemoteFiles::test_returns_full_paths_and_excludes_hidden_files` | EP-O1 | ✅ Pass |
| 11 | `TestListRemoteFiles::test_returns_empty_list_for_empty_directory` | EP-O1 | ✅ Pass |
| 12 | `TestDeleteRemotePath::test_runs_rm_rf_command` | EP-S1 | ✅ Pass |
| 13 | `TestDeleteRemotePath::test_delete_propagates_ssh_error` | EP-S5 | ✅ Pass |
| 14 | `TestExecuteSingularityImageBadDay::test_raises_when_exec_command_fails` | EP-S5 | ✅ Pass |
| 15 | `TestExecuteSingularityImageBadDay::test_raises_when_ssh_connection_drops_mid_launch` | EP-S5 | ✅ Pass |

**File Total: 14 passed, 0 failed, 1 xfail**

---

### 2.7 `tests/unit/services/test_discovery_service.py`

**Purpose:** Tests all `discovery_service.py` functions.

| # | Test Name | Partition | Status |
|---|---|---|---|
| 1 | `test_discover_methods_real_config` | EP-DS1 | ✅ Pass |
| 2 | `test_discover_method_names` | EP-DS1 | ✅ Pass |
| 3 | `test_discover_container_image` | EP-DS1, EP-M5 | ✅ Pass |
| 4 | `test_discover_entry_file` | EP-DS1, EP-M6 | ✅ Pass |
| 5 | `test_discover_methods_config_structure_validation` | EP-DS4 | ✅ Pass |
| 6 | `test_discover_methods_settings_files_exist` | EP-DS4 | ✅ Pass |

**File Total: 6 passed, 0 failed**

---

### 2.8 `tests/unit/services/test_run_solver.py`

**Purpose:** Tests `run_solver()` including bad day, known bugs, and database scenarios.

| # | Test Name | Partition | Status |
|---|---|---|---|
| 1 | `test_simulation_run_not_found_early_return` | EP-DB2 | ✅ Pass |
| 2 | `test_simulation_none_crash` | EP-DB3 | ✅ Pass |
| 3 | `test_solver_settings_none_sets_error_status` | EP-C6 | ✅ Pass |
| 4 | `test_json_unreadable_sets_error_status` | EP-C4 | ✅ Pass |
| 5 | `test_json_path_nonexistent_sets_error_status` | EP-C3 | ✅ Pass |
| 6 | `test_solver_settings_malformed_sets_error_status` | EP-C7 | ✅ Pass |
| 7 | `test_auralization_fails_error_status_orphaned_xlsx` | EP-O7 | ✅ Pass |
| 8 | `test_export_false_sets_error_status` | EP-O4 | ✅ Pass |
| 9 | `test_container_non_zero_exit_marked_completed` | EP-D5 | ✅ Pass — documents DEF-003 |

**File Total: 9 passed, 0 failed**

---

### 2.9 `tests/unit/services/test_remaining_cases.py`

**Purpose:** Final gap coverage — EP-DB4, EP-DS3, EP-M4.

| # | Test Name | Partition | Status |
|---|---|---|---|
| 1 | `RunSolverDBFailureTests::test_db_commit_fails_on_status_update` | EP-DB4 | ✅ Pass |
| 2 | `RunSolverDBFailureTests::test_db_commit_fails_does_not_propagate_exception` | EP-DB4 | ✅ Pass |
| 3 | `DiscoveryServiceRemovedMethodTests::test_removed_method_does_not_appear_in_discovery` | EP-DS3 | ✅ Pass |
| 4 | `DiscoveryServiceRemovedMethodTests::test_unknown_method_returns_none_from_discover_container_image` | EP-M4 | ✅ Pass |
| 5 | `DiscoveryServiceRemovedMethodTests::test_unknown_method_returns_none_from_discover_entry_file` | EP-M4, EP-M6 | ✅ Pass |

**File Total: 5 passed, 0 failed**

---

## 3. Known Bugs Captured by Tests

| ID | Severity | Test | Description | Status |
|---|---|---|---|---|
| DEF-001 | 🔴 Critical | B12 (xpassed) | No stall timeout in `_poll_until_complete` — crashed remote job hangs forever | Open |
| DEF-002 | 🔴 Critical | B13 (xpassed) | No `POLL_MAX_FAILED_CYCLES` — corrupt JSON loops forever | Open |
| DEF-003 | 🔴 Critical | RS9 | `container.wait()` exit code ignored — failed run marked `Completed` | Open |
| DEF-004 | 🟠 High | RS8 | `raise "Error saving..."` is invalid Python — `TypeError` raised | Open |
| DEF-005 | 🟠 High | — | SSH failure mid-execute leaves remote sandbox unclean | Open |
| DEF-006 | 🟡 Medium | — (commented out) | `match` block silently skips auralization for methods beyond DE/DG | Open |
| DEF-007 | 🟡 Medium | — not tested | only .json and .csv files are considered as output files | Open |
| DEF-008 | 🟠 High | - | end to end cloud execution for accounts with passphrase asscoiated with keys not accomplished | Open |
---

## 4. Coverage by Equivalence Partition

| Partition | Description | Status | Test(s) |
|---|---|---|---|
| EP-M1 | DE (cheap method) | ✅ | I-LE-DE |
| EP-M2 | DG (expensive method) | ✅ | I-LE-DG, I14-exec |
| EP-M3 | MyNewMethod | ✅ | I-LE-NEW |
| EP-M4 | Method not in discovery | ✅ | REM4, REM5 |
| EP-M5 | `container_image` is `None` | ✅ | EF2, DS3 |
| EP-M6 | `entry_file` is `None` | ✅ | EF3, DS4, REM5 |
| EP-E1 | Local execution | ✅ | All LocalExecutor tests |
| EP-E2 | Cloud execution | ✅ | All CloudExecutor tests |
| EP-E3 | Invalid resource type | ✅ | EF1 |
| EP-G1 | Simple geometry | ✅ | I-LE-DE |
| EP-G2 | Moderate geometry | ✅ | I-LE-DG |
| EP-G3 | Complex geometry | ✅ | I-LE-NEW |
| EP-C1 | Valid config | ✅ | U6, I18-LE, U5-MC, U6-MC, U7-MC |
| EP-C2 | `JSON_PATH` missing | ✅ | B-LE-json |
| EP-C3 | `JSON_PATH` non-existent | ✅ | RS5 |
| EP-C4 | JSON unreadable | ✅ | RS4 |
| EP-C5 | JSON malformed | ✅ | U3–U5, U7–U8 |
| EP-C6 | `solverSettings` is `None` | ✅ | RS3 |
| EP-C7 | `solverSettings` malformed | ✅ | RS6 |
| EP-D1 | Docker running, image present | ✅ | All LocalExecutor happy path |
| EP-D2 | Docker daemon down | ✅ | U20, B6-LE, I11-LE |
| EP-D3 | Duplicate container name | ✅ | B-LE-dup |
| EP-D4 | Mount unresolvable | ✅ | B4-LE, B-LE-mnt |
| EP-D5 | Container exits non-zero | ✅ | B-LE-D5, RS9 |
| EP-S1 | SSH healthy | ✅ | I1, I5, I7, I10–I19 |
| EP-S2 | SSH auth fails | ✅ | I2, B1-orig |
| EP-S3 | SSH timeout | ✅ | I3 |
| EP-S4 | SFTP upload fails | ✅ | I6, I19, B2-orig, B7-orig |
| EP-S5 | Remote disk full | ✅ | I8, I9-MC, B5-MC, B3-orig |
| EP-S6 | Sandbox already exists | ✅ | I9, B8-orig |
| EP-P1 | Progress increments to 100% | ✅ | I12, I13 |
| EP-P2 | Progress 100% on first poll | ✅ | I12, U2 |
| EP-P3 | JSON temporarily corrupt | ✅ | I14 |
| EP-P4 | JSON always corrupt | ✅ | B13 (xpassed), B5-orig |
| EP-P5 | Progress stuck forever | ✅ | B12 (xpassed), B4-orig |
| EP-P6 | Cancel flag before polling | ✅ | I15, U-SC2, B6-orig |
| EP-P7 | Cancel flag mid-polling | ✅ | I16 |
| EP-O1 | Outputs present | ✅ | I17, I18, U8-MC, U9-MC, I8-MC |
| EP-O4 | XLSX export fails | ✅ | RS8 |
| EP-O7 | Auralization fails after XLSX | ✅ | RS7 |
| EP-DB1 | `SimulationRun` exists | ✅ | Implicit in all RS tests with mocked session |
| EP-DB2 | `SimulationRun` not in DB | ✅ | RS1 |
| EP-DB3 | `Simulation` not found | ✅ | RS2 |
| EP-DB4 | DB commit fails | ✅ | REM1, REM2 |
| EP-DS1 | All methods well-formed | ✅ | DS1–DS4 |
| EP-DS3 | Method removed from repo | ✅ | REM3 |
| EP-DS4 | Malformed method definition | ✅ | DS5, DS6 |

---

## 5. CI Run History

| Run Date | Branch | Total | Pass | Fail | xfail | xpassed | Duration |
|---|---|---|---|---|---|---|---|
| 2026-03-17 | `testing/test-suite` | 120 | 116 | 0 | 1 | 2 | ~7s |
| 2026-03-16 | `testing/test-suite` | 118 | 114 | 0 | 1 | 2 | ~7s |
| 2026-03-15 | `testing/test-suite` | 116 | 112 | 1 | 1 | 2 | ~7s |
| 2026-03-14 | `testing/test-suite` | 116 | 109 | 4 | 1 | 2 | ~7s |

> **2026-03-17** — Added RS5 (`EP-C3`) and RS6 (`EP-C7`) to `test_run_solver.py`.
>
> **2026-03-16** — Final CI stabilisation. All 118 collected, 0 failed.
>
> **2026-03-15** — Failed `test_discover_methods_settings_files_exist` due to
> missing `SETTINGS_FILE_FOLDER` env var. Fixed by adding it to CI workflow.
>
> **2026-03-14** — Failed 4 discovery/run_solver tests due to
> `PRAGMA foreign_keys=OFF` being incompatible with PostgreSQL. Fixed by making
> PRAGMA conditional on `dialect.name == "sqlite"`.