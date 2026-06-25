"""Service: build per-method geometry-issue compatibility.

The simulation backend ships a single baseline file
(``example_settings/baseline_geometry_compatibility.json``) that lists every
geometry issue kind and its default compatibility. Each simulation method may
ship its own override file (referenced by ``geometryCompatibility`` in
``methods-config.json``) that overrides only the fields that differ from the
baseline, per issue kind.

This service loads the baseline, loads each method's override, and returns the
fully-merged compatibility for every discovered method.
"""
import copy
import json
import logging
import os
from typing import Any, Dict, List, Optional

from flask_smorest import abort

from config import DefaultConfig
from app.services.discovery_service import discover_methods

logger = logging.getLogger(__name__)

BASELINE_FILENAME = "baseline_geometry_compatibility.json"


def _load_json(path: str) -> Optional[dict]:
    """Load a JSON file, returning ``None`` if it is missing or invalid."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"Compatibility file not found: {path}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in compatibility file {path}: {e}")
        return None


def _simulation_backend_root() -> str:
    """Root of the simulation backend (the directory holding methods-config.json)."""
    return os.path.dirname(DefaultConfig.METHODS_CONFIG_PATH)


def _load_baseline() -> dict:
    """Load the baseline compatibility file.

    Looks in ``SETTINGS_FILE_FOLDER`` first, then falls back to
    ``<simulation-backend>/example_settings``.
    """
    candidates = [
        os.path.join(DefaultConfig.SETTINGS_FILE_FOLDER, BASELINE_FILENAME),
        os.path.join(_simulation_backend_root(), "example_settings", BASELINE_FILENAME),
    ]
    for path in candidates:
        baseline = _load_json(path)
        if baseline is not None:
            return baseline

    abort(
        500,
        message=(
            f"Baseline geometry compatibility file '{BASELINE_FILENAME}' not found. "
            f"Looked in: {candidates}"
        ),
    )


def _merge_method_override(baseline_issues: dict, override: Optional[dict]) -> dict:
    """Merge a method override on top of the baseline issues, per issue kind.

    Only the fields present in the override replace the baseline fields; every
    other field (and every issue kind not mentioned) is inherited unchanged.
    """
    merged = copy.deepcopy(baseline_issues)
    if not override:
        return merged

    for kind, fields in override.get("issues", {}).items():
        if not isinstance(fields, dict):
            continue
        if kind in merged and isinstance(merged[kind], dict):
            merged[kind].update(fields)
        else:
            merged[kind] = dict(fields)
    return merged


def get_simulation_compatibility() -> Dict[str, Any]:
    """Build the per-method geometry-issue compatibility.

    Returns a payload containing the baseline metadata and, for every
    discovered simulation method, the fully-merged issue compatibility
    (baseline overridden by the method's own override file).
    """
    baseline = _load_baseline()
    baseline_issues = baseline.get("issues", {})
    root = _simulation_backend_root()

    methods: List[Dict[str, Any]] = []
    for cfg in discover_methods():
        sim_type = cfg.get("simulationType")
        rel_path = cfg.get("geometryCompatibility")

        override: Optional[dict] = None
        if rel_path:
            override = _load_json(os.path.join(root, rel_path))

        methods.append(
            {
                "simulationType": sim_type,
                "label": cfg.get("label"),
                "notes": override.get("notes") if override else None,
                "issues": _merge_method_override(baseline_issues, override),
            }
        )

    return {
        "version": baseline.get("version"),
        "compatibilityLevels": baseline.get("compatibilityLevels"),
        "methods": methods,
    }
