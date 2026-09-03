import json
import logging
import os
from typing import List, Dict, Any

from config import DefaultConfig

logger = logging.getLogger(__name__)

def discover_methods() -> List[dict]:
    """Discover available simulation methods from configuration.

    Reads ``methods-config.json`` (array format) from the simulation backend, 
    validates that it is a list of method configurations, filters out invalid entries, and returns only the valid
    configurations. A method configuration is considered valid if it defines
    a non-empty ``simulationType`` and a ``containerImage`` field.

    The function logs and prints basic information about the discovered
    methods, including the total count and the list of simulation type IDs.

    Returns:
        list[dict]: A list of valid method configuration dictionaries.
        Returns an empty list if the file is missing, not an array,
        or contains invalid JSON.
    """
    config_path = DefaultConfig.METHODS_CONFIG_PATH

    if(os.path.exists(config_path)):
        logger.info(f"Found methods-config.json at: {config_path}")

    try:
        with open(config_path, 'r') as f:
            methods_array = json.load(f)
        
        # Validate it's an array
        if not isinstance(methods_array, list):
            print("methods-config.json must be an array")
            return []
        
        # Filter valid methods and collect IDs
        valid_methods = []
        ids = []
        
        for cfg in methods_array:
            task_type = cfg.get("simulationType")
            if task_type and "containerImage" in cfg and "entryFile" in cfg:
                valid_methods.append(cfg)
                ids.append(task_type)
        
        # Print ONLY length and IDs
        print(f"Discovered {len(valid_methods)} methods: {ids}")
        return valid_methods  # Return raw filtered array
        
    except FileNotFoundError:
        print("methods-config.json not found")
        return []
    except json.JSONDecodeError as e:
        print(f"Invalid JSON: {e}")
        return []
    
def discover_method_names() -> List[str]:
    """Discover simulation method names from configuration.

    Uses :func:`discover_methods` to load and validate the configuration,
    then extracts and returns the list of ``simulationType`` values for all
    valid methods.

    Returns:
        list[str]: A list of simulation type names for all valid methods.
        Returns an empty list if no valid methods are found.
    """
    valid_methods = discover_methods()
    methods_names = [cfg.get("simulationType") for cfg in valid_methods if cfg.get("simulationType")]
    print(f"Discovered method names: {methods_names}")
    return methods_names

def discover_container_image(simulation_type: str) -> str | None:
    """Discover the container image for a given simulation type.

    Looks up the method configuration for the specified ``simulation_type``
    using :func:`discover_methods` and returns the corresponding
    ``container_image`` value, if present.

    Args:
        simulation_type (str): The simulation type identifier to look up.

    Returns:
        str | None: The container image name for the given simulation type,
        or ``None`` if the simulation type is not found or the field is missing.
    """
    methods = discover_methods()
    print(f"Looking for container image for simulation type: {simulation_type}")
    for cfg in methods:
        if cfg.get("simulationType") == simulation_type:
            return cfg.get("containerImage")
    print(f"No container image found for simulation type: {simulation_type}")
    return None

def discover_entry_file(simulation_type: str) -> str | None:
    """Discover the entry file for a given simulation type.

    Looks up the method configuration for the specified ``simulation_type``
    using :func:`discover_methods` and returns the corresponding
    ``entryFile`` value, if present.

    Args:
        simulation_type (str): The simulation type identifier to look up.

    Returns:
        str | None: The entry file name for the given simulation type,
        or ``None`` if the simulation type is not found or the field is missing.
    """
    methods = discover_methods()
    print(f"Looking for entry file for simulation type: {simulation_type}")
    for cfg in methods:
        if cfg.get("simulationType") == simulation_type:
            return cfg.get("entryFile")
    print(f"No entry file found for simulation type: {simulation_type}")
    return None


if __name__ == "__main__":
    methods = discover_methods()
    print(f"METHODS: {methods}")
