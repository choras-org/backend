import logging
import os
import uuid
import config
import shutil
import json

from flask_smorest import abort
from werkzeug.utils import secure_filename

from app.db import db
from app.models import Model
from config import FeatureToggle, DefaultConfig
from config import app_dir
from datetime import datetime

from app.services import file_service

# Create logger for this module
logger = logging.getLogger(__name__)


def create_new_model(model_data):
    new_model = Model(
        name=model_data["name"],
        projectId=model_data["projectId"],
        sourceFileId=model_data["sourceFileId"],
        outputFileId=model_data["sourceFileId"],
        imagePath=model_data["imagePath"] if "imagePath" in model_data else None,
    )

    if FeatureToggle.is_enabled("enable_geo_conversion"):
        new_model.hasGeo = True

    try:
        db.session.add(new_model)
        db.session.commit()

    except Exception as ex:
        db.session.rollback()
        logger.error(f"Can not create a new model: {ex}")
        abort(400, f"Can not create a new model: {ex}")

    return new_model


def get_model(model_id):
    model = Model.query.filter_by(id=model_id).first()
    if not model:
        logger.error("Model with id " + str(model_id) + "does not exists!")
        abort(404, "Model does not exist")
    return model


def update_model(model_id, model_data):
    model = Model.query.filter_by(id=model_id).first()
    if not model:
        logger.error("Model doesn't exist, cannot update!")
        abort(400, "Model doesn't exist, cannot update!")

    try:
        model.name = model_data["name"]
        model.updatedAt = datetime.now()
        db.session.commit()
    except Exception as ex:
        db.session.rollback()
        logger.error(f"Can not update! Error: {ex}")
        abort(400, message=f"Can not update! Error: {ex}")

    return model


def delete_model(model_id):
    model = Model.query.filter_by(id=model_id).first()
    if not model:
        logger.error("Model doesn't exist, cannot delete!")
        abort(404, "Model doesn't exist, cannot delete!")

    # Attempt to remove associated image asset if present
    if model.imagePath:
        image_path = model.imagePath
        # Build absolute path when a relative uploads path is stored
        if not os.path.isabs(image_path):
            image_path = os.path.join(config.basedir, image_path)
        try:
            if os.path.exists(image_path):
                os.remove(image_path)
        except Exception as ex:
            # Log and continue deleting the model even if file removal fails
            logger.warning(f"Failed to remove image asset '{image_path}': {ex}")

    try:
        db.session.delete(model)
        db.session.commit()
    except Exception as ex:
        db.session.rollback()
        logger.error(f"Error deleting the model!: {ex}")
        abort(500, f"Error deleting the model!: {ex}")


def upload_image(files):
    if 'file' not in files:
        logger.error("No file provided in the request")
        abort(400, message="No file provided")
    
    upload_file = files['file']
    
    if upload_file.filename == "":
        logger.error("No file selected")
        abort(400, message="No file selected")
    
    # Check if file has allowed extension
    allowed_image_extensions = {'png', 'jpg', 'jpeg'}
    if not ('.' in upload_file.filename and 
            upload_file.filename.rsplit('.', 1)[1].lower() in allowed_image_extensions):
        logger.error(f"File type not allowed: {upload_file.filename}")
        abort(400, message="Invalid file type. Allowed types: png, jpg, jpeg")
    
    try:
        # Secure the filename and create unique name
        filename = secure_filename(upload_file.filename)
        file_ext = filename.rsplit(".", 1)[1].lower()
        unique_filename = f"{filename.rsplit('.', 1)[0]}_{uuid.uuid4().hex}.{file_ext}"
        
        # Save the file
        file_path = os.path.join(DefaultConfig.USER_MODEL_IMAGE_FOLDER_NAME, unique_filename)
        upload_file.save(file_path)
        
        # Return the relative path
        return {"imagePath": f"{DefaultConfig.USER_MODEL_IMAGE_FOLDER_NAME}/{unique_filename}"}
    
    except Exception as ex:
        logger.error(f"Error uploading image file: {ex}")
        abort(500, message=f"Error uploading image file: {ex}")


def copy_example_models_to_uploads():
    # 1. Define the path to the example models catalog JSON file
    json_path = os.path.join(app_dir, "models", "data", "example_models.json")
    
    if not os.path.exists(json_path):
        logger.error(f"Catalog JSON not found at: {json_path}")
        abort(404, "Example models catalog file not found.")

    # 2. Read and parse the JSON data
    with open(json_path, "r") as f:
        example_models = json.load(f)

    try:
        # Ensure the main destination uploads folder exists before starting the loop
        os.makedirs(config.DefaultConfig.UPLOAD_FOLDER, exist_ok=True)

        # 3. Loop through each model item in the JSON array
        for model_data in example_models:
            src_relative_path = model_data.get("filePath")
            if not src_relative_path:
                logger.warning(f"Model ID {model_data.get('id')} is missing 'filePath'. Skipping.")
                continue
                
            src_absolute_path = os.path.join(config.basedir, src_relative_path)
            
            # Validate if the source physical file actually exists
            if not os.path.exists(src_absolute_path):
                logger.error(f"Physical file not found at path: {src_absolute_path}")
                abort(404, f"Example file for {model_data['name']} not found.")

            # 4. Extract the file extension (.obj) and the base filename dynamically
            _, file_extension = os.path.splitext(src_relative_path)
            base_name = os.path.basename(src_relative_path).replace(file_extension, "")
            
            unique_name = f"{base_name}{file_extension}"
            dst_absolute_path = os.path.join(config.DefaultConfig.UPLOAD_FOLDER, unique_name)

            # 6. Execute the physical file copy operation
            shutil.copy2(src_absolute_path, dst_absolute_path)
            logger.info(f"Successfully copied {model_data['name']} to: {dst_absolute_path}")

        return {"message": "Initial full projects successfully!"}

    except Exception as ex:
        logger.error(f"Failed to execute example models copying method! Error: {ex}")
        abort(500, f"Failed to process example models: {ex}")


def get_example_models():
    json_path = os.path.join(app_dir, "models", "data", "example_models.json")
    
    if not os.path.exists(json_path):
        logger.error(f"Catalog JSON file not found at: {json_path}")
        abort(404, "Example models catalog file not found.")
        
    try:
        with open(json_path, "r") as f:
            example_models = json.load(f)
            
        # Dynamically map and build the modelUrl for each item
        for model in example_models:
            base_url = file_service.upload_dir().rstrip("/")
            model["modelUrl"] = f"{base_url}/{model['fileName']}"
            
        return example_models
        
    except Exception as ex:
        logger.error(f"Failed to retrieve example models! Error: {ex}")
        abort(500, "Internal server error while fetching example models.")