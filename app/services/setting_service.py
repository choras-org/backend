import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from flask_smorest import abort

from app.db import db
from app.models.SimulationSetting import SimulationSetting
from config import DefaultConfig, app_dir

# Create logger for this module
logger = logging.getLogger(__name__)


def get_setting_by_type(simulation_type: str) -> Optional[Dict]:
    try:
        setting: Optional[SimulationSetting] = SimulationSetting.query.filter_by(simulationType=simulation_type).first()
        if setting is None:
            logger.error(f"Setting not found by type: {simulation_type}")
            abort(404, f"Setting not found by type: {simulation_type}")

        setting_path = os.path.join(DefaultConfig.SETTINGS_FILE_FOLDER, setting.name)
        with open(setting_path) as json_setting_file:
            setting_json: Dict = json.load(json_setting_file)
            return setting_json

    except Exception as ex:
        logger.error(f"Can not get setting file by type! Error: {ex}")
        abort(400, message=f"Can not get setting file by type: {simulation_type}!")


def get_all_simulation_settings():
    return SimulationSetting.query.order_by(SimulationSetting.simulationType).all()


def insert_initial_settings():
    simulation_settings = get_all_simulation_settings()
    if len(simulation_settings):
        return
    logger.info("Inserting initial setting files...")
    with open(os.path.join(app_dir, "models", "data", "simulation_settings.json")) as json_setting_files:
        initial_setting_files = json.load(json_setting_files)
        try:
            new_setting_files = []
            for setting_file in initial_setting_files:
                new_setting_files.append(
                    SimulationSetting(
                        simulationType=setting_file["simulationType"],
                        name=setting_file["name"],
                        label=setting_file["label"],
                        description=setting_file["description"],
                        repositoryURL=setting_file["repositoryURL"],
                        documentationURL=setting_file["documentationURL"]
                    )
                )

            db.session.add_all(new_setting_files)
            db.session.commit()

        except Exception as ex:
            db.session.rollback()
            logger.error(f"Can not insert initial audio files! Error: {ex}")
            abort(400, f"Can not insert initial audio files! Error: {ex}")

    return {"message": "Initial audio files added successfully!"}


def update_settings():
    with open(os.path.join(app_dir, "models", "data", "simulation_settings.json")) as json_setting_files:
        setting_json_dict: Dict[str, Dict[str, Any]] = {
            setting["simulationType"]: setting for setting in json.load(json_setting_files)
        }
        setting_db_list: List[SimulationSetting] = SimulationSetting.query.all()
        try:
            for setting in setting_db_list:
                if setting.simulationType not in setting_json_dict:
                    db.session.delete(setting)
                else:
                    for key, value in setting_json_dict[setting.simulationType].items():
                        setting.__setattr__(key, value)
                    setting.updatedAt = datetime.now()
                    del setting_json_dict[setting.simulationType]

            for setting in setting_json_dict.values():
                db.session.add(SimulationSetting(**setting))

            db.session.commit()

        except Exception as ex:
            db.session.rollback()
            logger.error(f"Can not update audio files! Error: {ex}")

    return {"message": "Initial audio files added successfully!"}
