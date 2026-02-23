import json
import logging
import os
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

def discover_methods() -> List[dict]:
    """
    Reads methods-config.json (array format) and returns the raw array.
    Prints length and IDs only.
    """
    config_path = "/app/simulation-backend/methods-config.json"

    
    logger.error(f"Looking for: {config_path}")
    logger.error(f"Exists? {os.path.exists(config_path)}")
    
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
            if task_type and "container_image" in cfg:
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

if __name__ == "__main__":
    methods = discover_methods()
    print(f"METHODS: {methods}")
