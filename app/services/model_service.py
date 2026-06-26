import logging
import os
import uuid
import config

from celery import shared_task
from flask_smorest import abort
from sqlalchemy.orm import scoped_session, sessionmaker
from werkzeug.utils import secure_filename

from app.db import db
from app.models import Model, File, ModelIssue
from app.types import DetectionStage, RepairStatus, GeometryProcessingStatus
from config import FeatureToggle, DefaultConfig
from datetime import datetime
from app.services import file_service
from app.services.geometry_service import (
    run_inspect_for_file_upload,
    run_repair_pipeline
)
# Create logger for this module
logger = logging.getLogger(__name__)

def create_new_model(model_data):
    logger.warning(f"Creating new model with data: {model_data}")
    new_model = Model(
        name=model_data["name"],
        projectId=model_data["projectId"],
        sourceFileId=model_data["sourceFileId"],
        outputFileId=model_data["sourceFileId"],
        imagePath=model_data["imagePath"] if "imagePath" in model_data else None,
    )

    db.session.add(new_model)
    try:
        db.session.flush()

        dispatch_geometry = False
        if FeatureToggle.is_enabled("enable_geo_conversion"):
            file = File.query.filter_by(id=model_data["sourceFileId"]).first()
            if file:
                file_name, _ = os.path.splitext(os.path.basename(file.fileName))

                # Create the .geo File row up front so it persists even if the
                # background pipeline crashes; the actual .geo content is
                # produced by the repair task.
                file_geo = File(fileName=f"{file_name}.geo")
                new_model.hasGeo = True
                db.session.add(file_geo)

                # Mark the model as queued for background geometry processing.
                new_model.geometryStatus = GeometryProcessingStatus.Pending
                new_model.geometryProgress = 0
                dispatch_geometry = True

        # Commit the model (and the .geo File) immediately so a slow or failing
        # pipeline can never roll back the model creation.
        db.session.commit()
    except Exception as ex:
        db.session.rollback()
        logger.error(f"Can not create a new model: {ex}")
        abort(400, f"Can not create a new model: {ex}")

    # Dispatch the heavy inspect + repair pipeline to a background Celery task
    # so the HTTP request returns immediately (avoids the gunicorn worker
    # timeout). The task updates geometryStatus/geometryProgress as it runs.
    if dispatch_geometry:
        process_model_geometry.delay(new_model.id)

    return new_model


def reprocess_model_geometry(model_id):
    """Re-run the background geometry pipeline for a model.

    Intended for models whose pipeline previously failed. Clears any stale
    ModelIssue rows and the repair decision, resets the status to ``Pending``
    and dispatches the task again.
    """
    model = get_model(model_id)

    if not model.hasGeo:
        logger.error(f"Model {model_id} has no geometry to process")
        abort(400, message="This model has no geometry to process")

    if model.geometryStatus == GeometryProcessingStatus.Processing:
        logger.warning(f"Model {model_id} is already processing")
        abort(409, message="Geometry processing is already running for this model")

    try:
        # Idempotency: drop any partial results from a previous run so the task
        # does not create duplicate ModelIssue rows.
        ModelIssue.query.filter_by(modelId=model.id).delete()
        model.repairStatus = None
        model.geometryStatus = GeometryProcessingStatus.Pending
        model.geometryProgress = 0
        model.updatedAt = datetime.now()
        db.session.commit()
    except Exception as ex:
        db.session.rollback()
        logger.error(f"Can not reset model {model_id} for reprocessing: {ex}")
        abort(400, message=f"Can not reprocess geometry: {ex}")

    process_model_geometry.delay(model.id)
    return model


@shared_task
def process_model_geometry(model_id: int):
    """Run the inspect + repair geometry pipeline for a model in the background.

    Mirrors the ``run_solver`` task pattern: a fresh scoped session, all errors
    caught, and ``geometryStatus``/``geometryProgress`` updated as the pipeline
    advances. Writes the ``AfterUpload`` and ``AfterRepair`` ``ModelIssue`` rows
    and sets ``repairStatus = Pending`` when a repaired geometry is available.
    """
    logger.info(f"Running geometry pipeline task for model_id: {model_id}")

    session = scoped_session(sessionmaker(bind=db.engine))()

    def _set_progress(model, pct):
        model.geometryProgress = pct
        session.commit()

    try:
        model = session.query(Model).get(model_id)
        if model is None:
            logger.error(f"Model with id {model_id} not found")
            return

        source_file = session.query(File).get(model.sourceFileId)
        if source_file is None:
            logger.error(f"Source file {model.sourceFileId} not found for model {model_id}")
            model.geometryStatus = GeometryProcessingStatus.Failed
            session.commit()
            return

        file_name, _ = os.path.splitext(os.path.basename(source_file.fileName))
        directory = DefaultConfig.UPLOAD_FOLDER
        base_url = file_service.upload_dir()

        model.geometryStatus = GeometryProcessingStatus.Processing
        _set_progress(model, 5)

        # Idempotency: remove any issue rows from a previous (failed/retried)
        # run so this task never produces duplicates.
        session.query(ModelIssue).filter_by(modelId=model.id).delete()
        session.commit()

        # --- inspect (AfterUpload) ---
        inital_issue_path = os.path.join(directory, f"{file_name}_inspect_issue.json")
        _, issue_count = run_inspect_for_file_upload(file_name, directory)

        initial_issue_url = f"{base_url}/{os.path.basename(inital_issue_path)}"
        initial_model_path = os.path.join(directory, f"{file_name}.zip")
        initial_model_url = f"{base_url}/{os.path.basename(initial_model_path)}"
        session.add(
            ModelIssue(
                modelId=model.id,
                fileUrl=initial_issue_url,
                issueCount=issue_count,
                detectionStage=DetectionStage.AfterUpload,
                modelFileUrl=initial_model_url,
            )
        )
        _set_progress(model, 35)

        # --- repair (AfterRepair) ---
        obj_path = os.path.join(directory, f"{file_name}.obj")
        issue_path = os.path.join(directory, f"{file_name}_remaining_issue.json")
        _, remaining_issue_count = run_repair_pipeline(
            obj_path,
            directory,
            volume_name="RoomVolume",
        )

        issue_url = f"{base_url}/{os.path.basename(issue_path)}"
        repaired_model_path = os.path.join(directory, f"{file_name}_repaired.zip")
        repaired_model_url = f"{base_url}/{os.path.basename(repaired_model_path)}"
        session.add(
            ModelIssue(
                modelId=model.id,
                fileUrl=issue_url,
                issueCount=remaining_issue_count,
                detectionStage=DetectionStage.AfterRepair,
                modelFileUrl=repaired_model_url,
            )
        )
        _set_progress(model, 90)

        # A repaired geometry is available but the user has not yet accepted or
        # rejected it.
        model.repairStatus = RepairStatus.Pending
        model.geometryStatus = GeometryProcessingStatus.Completed
        _set_progress(model, 100)
        logger.info(f"Geometry pipeline completed for model {model_id}")
    except Exception as ex:
        session.rollback()
        logger.exception(f"Geometry pipeline failed for model {model_id}: {ex}")
        try:
            model = session.query(Model).get(model_id)
            if model is not None:
                model.geometryStatus = GeometryProcessingStatus.Failed
                session.commit()
        except Exception:
            session.rollback()
    finally:
        session.close()

def get_model(model_id):
    model = Model.query.filter_by(id=model_id).first()
    if not model:
        logger.error("Model with id " + str(model_id) + "does not exists!")
        abort(404, "Model does not exist")
    return model


def set_repair_decision(model_id, accept):
    """Accept or reject the repaired geometry for a model.

    When accepted, the model's ``outputFileId`` is switched to a File row
    representing the repaired 3DM so that both the viewer URL and the
    simulation geometry (.geo/.msh) resolve to the repaired files. When
    rejected, ``outputFileId`` is reset to the original ``sourceFileId``.
    """
    model = get_model(model_id)

    if model.repairStatus is None:
        logger.error(f"Model {model_id} has no repaired geometry to decide on")
        abort(400, message="No repaired geometry is available for this model")

    if accept:
        source_file = file_service.get_file_by_id(model.sourceFileId)
        stem, _ = os.path.splitext(os.path.basename(source_file.fileName))

        directory = DefaultConfig.UPLOAD_FOLDER
        repaired_geo = os.path.join(directory, f"{stem}_repaired.geo")
        repaired_zip = os.path.join(directory, f"{stem}_repaired.zip")
        if not os.path.exists(repaired_geo) or not os.path.exists(repaired_zip):
            logger.error(
                f"Repaired geometry files missing for model {model_id}: "
                f"{repaired_geo} / {repaired_zip}"
            )
            abort(400, message="Repaired geometry files are not available")

        repaired_file_name = f"{stem}_repaired.3dm"
        repaired_file = File.query.filter_by(fileName=repaired_file_name).first()
        if not repaired_file:
            repaired_file = File(fileName=repaired_file_name)
            db.session.add(repaired_file)
            db.session.flush()

        model.outputFileId = repaired_file.id
        model.repairStatus = RepairStatus.Accepted
    else:
        model.outputFileId = model.sourceFileId
        model.repairStatus = RepairStatus.Rejected

    model.updatedAt = datetime.now()

    try:
        db.session.commit()
    except Exception as ex:
        db.session.rollback()
        logger.error(f"Can not update the repair decision: {ex}")
        abort(400, message=f"Can not update the repair decision: {ex}")

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
