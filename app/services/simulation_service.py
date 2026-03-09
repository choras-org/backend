import json
import logging
from datetime import datetime
from pathlib import Path
from unittest import case

from celery import shared_task  # , current_task
from flask_smorest import abort
from sqlalchemy.orm import joinedload, scoped_session, sessionmaker

from app.db import db
from app.factory.export_factory.ExportHelper import ExportHelper
from app.models import Export, Simulation, SimulationRun, Task
from app.services import file_service, material_service, model_service
from app.services.auralization_service import auralization_calculation, auralization_calculation_DG
from app.types import Status, TaskType
from config import CustomExportParametersConfig

"""Services for managing simulations.

This module exposes helpers for creating, updating, deleting and
querying simulation records as well as orchestrating solver tasks via
Celery. It coordinates with other service layers (model_service,
file_service, etc.) and updates database models such as
:class:`~app.models.Simulation` and :class:`~app.models.SimulationRun`.
"""

# Create logger for this module
logger = logging.getLogger(__name__)

# If you want to run the simulation methods locally to be able to set breakpoints, set this to True
debug_celery = False

def create_new_simulation(simulation_data):
    """
    Persist a new :class:`~app.models.Simulation` instance.

    Parameters
    ----------
    simulation_data : dict
        Key/value pairs used to construct the Simulation object.

    Returns
    -------
    Simulation
        The database object that was created.

    Raises
    ------
    HTTPException
        Aborts with ``400`` if the insert fails.
    """
    new_simulation = Simulation(**simulation_data)

    try:
        db.session.add(new_simulation)
        db.session.commit()

    except Exception as ex:
        db.session.rollback()
        logger.error(f"Can not create a new model: {ex}")
        abort(400, message=f"Can not create a new model: {ex}")

    return new_simulation


def update_simulation_by_id(simulation_data, simulation_id):
    """
    Apply a partial update to an existing simulation.

    Parameters
    ----------
    simulation_data : dict
        Fields to update on the simulation.
    simulation_id : int
        Primary key of the simulation to modify.

    Returns
    -------
    Simulation
        The updated simulation object.

    Raises
    ------
    HTTPException
        Aborts with ``400`` on commit failure or if the simulation does
        not exist.
    """
    simulation = get_simulation_by_id(simulation_id)

    try:
        for key, value in simulation_data.items():
            setattr(simulation, key, value)

        simulation.updatedAt = datetime.now()
        db.session.commit()

    except Exception as ex:
        db.session.rollback()
        logger.error(f"Can not update the simulation: {ex}")
        abort(400, message=f"Can not update the simulation: {ex}")

    return simulation


def get_simulation_by_model_id(model_id):
    """
    Retrieve all simulations that belong to a given model.

    Parameters
    ----------
    model_id : int
        Identifier of the model.

    Returns
    -------
    list[Simulation]
        List of simulations sorted by ``updatedAt`` descending.
    """
    return (
        Simulation.query.filter_by(modelId=model_id)
        .order_by(Simulation.updatedAt.desc())
        .all()
    )


def get_simulation_run():
    """
    Fetch all simulation run records and refresh their status from the
    underlying JSON result file.

    Returns
    -------
    list[SimulationRun]
        All :class:`~app.models.SimulationRun` instances.
    """
    result = (
        SimulationRun.query.options(joinedload(SimulationRun.simulation))
        .filter(SimulationRun.simulation)
        .all()
    )

    for simulation_run in result:
        update_simulation_run_status(simulation_run, simulation_run.simulation)

    return result


def get_simulation_run_by_id(simulation_run_id):
    """
    Return a single simulation run by its primary key.

    Parameters
    ----------
    simulation_run_id : int
        The id of the simulation run to retrieve.

    Returns
    -------
    SimulationRun
        The matching simulation run.

    Raises
    ------
    HTTPException
        Aborts with ``400`` if no record is found.
    """
    simulation_run = SimulationRun.query.filter_by(id=simulation_run_id).first()
    if not simulation_run:
        logger.error(
            "Simulation Run with id " + str(simulation_run_id) + "does not exist!"
        )
        abort(400, message="Simulation Run doesn't exist!")
    return simulation_run


def delete_simulation(simulation_id):
    """
    Remove a simulation and any associated run from the database.

    Parameters
    ----------
    simulation_id : int
        Primary key of the simulation to delete.
    
    Raises
    ------
    HTTPException
        Aborts with ``500`` if an error occurs during deletion.
    """
    try:
        simulation = Simulation.query.filter_by(id=simulation_id).one()
        SimulationRun.query.filter_by(id=simulation.id).delete()
        Simulation.query.filter_by(id=simulation.id).delete()

        db.session.commit()

    except Exception as ex:
        db.session.rollback()
        logger.error(f"Error deleting the simulation: {ex}")
        abort(500, message=f"Error deleting the simulation: {ex}")


def delete_simulation_run(simulation_run_id):
    """
    Delete a single simulation run record.

    Parameters
    ----------
    simulation_run_id : int
        Primary key of the run to remove.

    Raises
    ------
    HTTPException
        Aborts with ``500`` if an error occurs during deletion.
    """
    try:
        SimulationRun.query.filter_by(id=simulation_run_id).delete()
        db.session.commit()

    except Exception as ex:
        db.session.rollback()
        logger.error(f"Error deleting the previous simulation run: {ex}")
        abort(500, message=f"Error deleting the previous simulation run: {ex}")


def get_simulation_by_id(simulation_id):
    """
    Retrieve a simulation by its identifier, aborting if absent.

    Parameters
    ----------
    simulation_id : int
        The simulation's primary key.

    Returns
    -------
    Simulation
        The found simulation instance.

    Raises
    ------
    HTTPException
        Aborts with ``400`` if no record is found.
    """
    simulation = Simulation.query.filter_by(id=simulation_id).first()
    if not simulation:
        logger.error("Simulation with id " + str(simulation_id) + " does not exist!")
        abort(400, message="Simulation doesn't exist!")
    return simulation


def create_source_task(task_type, source_id):
    """
    Helper that creates a ``Task`` object associated with a source location.

    This is used when initializing a new simulation run; it does not
    persist the task in the run record itself but returns a status
    dictionary to the caller.

    Parameters
    ----------
    task_type : TaskType
        The type of solver task (e.g. ``DE``, ``DG``).
    source_id : Any
        Identifier for the source point.

    Returns
    -------
    dict
        Status information to include in a simulation run payload.

    Raises
    ------
    HTTPException
        Aborts with ``500`` if an error occurs during task creation.

    """
    try:
        task = Task(taskType=task_type, status=Status.Created)
        db.session.add(task)
        db.session.commit()

    except Exception as ex:
        db.session.rollback()
        logger.error(f"Error creating the task: {ex}")
        abort(500, message=f"Error creating the task: {ex}")

    return {
        "id": task.id,
        "taskType": task.taskType.value,
        "status": task.status.value,
        "message": task.message,
        "percentage": 0,
        "sourcePointId": source_id,
    }


def create_result_source_object(source, receivers, result_type):
    """
    Construct the skeleton of a result entry for a source/receiver pair.

    Parameters
    ----------
    source : dict
        Source point metadata.
    receivers : Any
        List of receiver metadata dictionaries.
    result_type : TaskType
        Indicates which solver results will be stored.

    Returns
    -------
    dict
        A template JSON object that will be populated by the solver.
    """
    responses_obj = []

    for receiver in receivers:
        responses_obj.append(
            {
                "label": receiver["label"],
                "orderNumber": receiver["orderNumber"],
                "x": receiver["x"],
                "y": receiver["y"],
                "z": receiver["z"],
                "pointId": receiver["id"],
                "parameters": {
                    "edt": [],
                    "t20": [],
                    "t30": [],
                    "c80": [],
                    "d50": [],
                    "ts": [],
                    "spl_t0_freq": [],
                },
                "receiverResults": [],
            }
        )

    return {
        "label": source["label"],
        "orderNumber": source["orderNumber"],
        "percentage": 0,
        "sourcePointId": source["id"],
        "sourceX": source["x"],
        "sourceY": source["y"],
        "sourceZ": source["z"],
        "resultType": result_type,
        "frequencies": [125, 250, 500, 1000, 2000],
        "responses": responses_obj,
    }


def start_solver_task(simulation_id):
    """
    Initialize a :class:`~app.models.SimulationRun` and enqueue the
    solver task via Celery.

    This method prepares the JSON input file, computes absorption
    coefficients, and updates the database state for both the simulation
    and the newly created run. If ``debug_celery`` is enabled the
    solver is invoked synchronously for easier breakpoint debugging.

    Parameters
    ----------
    simulation_id : int
        Primary key of the simulation to run.

    Returns
    -------
    SimulationRun
        The newly created simulation run record.
    """
    simulation = get_simulation_by_id(simulation_id)

    if simulation.simulationRunId:
        delete_simulation_run(simulation.simulationRunId)

    model = model_service.get_model(simulation.modelId)
    json_path = file_service.get_file_related_path(
        model.outputFileId, simulation_id, extension="json"
    )
    msh_path = file_service.get_file_related_path(
        model.outputFileId, simulation_id, extension="msh"
    )
    geo_path = file_service.get_file_related_path(
        model.outputFileId, simulation_id, extension="geo"
    )
    sources_tasks = []
    results_container = []

    for source in simulation.sources:
        task_statuses = []
        task_statuses.append(create_source_task(simulation.taskType.value, source["id"]))
        results_container.append(
            create_result_source_object(
                source, simulation.receivers, simulation.taskType.value
            )
        )

        sources_tasks.append(
            {
                "label": source["label"],
                "orderNumber": source["orderNumber"],
                "percentage": 0,
                "sourcePointId": source["id"],
                "taskStatuses": task_statuses,
            }
        )

    new_simulation_run = SimulationRun(
        sources=sources_tasks,
        receivers=simulation.receivers,
        taskType=simulation.taskType,
        settingsPreset=simulation.settingsPreset,
        layerIdByMaterialId=simulation.layerIdByMaterialId,
        solverSettings=simulation.solverSettings,
        status=Status.Created,
    )

    try:
        simulation.completedAt = ""
        simulation.status = Status.Created

        db.session.add(new_simulation_run)
        db.session.commit()

        simulation.simulationRunId = new_simulation_run.id
        db.session.commit()

    except Exception as ex:
        db.session.rollback()
        logger.error(f"Can not create a new simulation run: {ex}")
        abort(400, message=f"Can not create a new simulation run: {ex}")

    # Run the background task asynchronously
    absorption_coefficients = {}
    for layer, material_id in simulation.layerIdByMaterialId.items():
        material = material_service.get_material_by_id(material_id)
        # Ignore the lower frequencies in [63, 125, 250, 500, 1000, 2000, 4000]
        absorption_coefficients[layer] = ", ".join(
            map(str, material.absorptionCoefficients[1:-1])
        )

    with open(json_path, "w") as json_result_file:
        json_result_file.write(
            json.dumps(
                {
                    "absorption_coefficients": absorption_coefficients,
                    "msh_path": msh_path,
                    "geo_path": geo_path,
                    "results": results_container,
                    "should_cancel": False,
                    "task_id": -1,
                },
                indent=4,
            )
        )

    # If the debug_celery flag is true, run the solver right here so we can debug (put breakpoints and such)
    if debug_celery:
        run_solver(new_simulation_run.id, json_path)
    else:
        task = run_solver.delay(new_simulation_run.id, json_path)

        result_container = {}
        if json_path is not None:
            with open(json_path, "r") as json_file:
                result_container = json.load(json_file)

        result_container["task_id"] = task.id

        if json_path is not None:
            with open(json_path, "w") as json_task_id:
                json_task_id.write(json.dumps(result_container, indent=4))
        if json_path is not None:
            with open(json_path, "r") as json_file:
                test = json.load(json_file)
            print("Task id from JSON")
            print(test["task_id"])

        try:
            simulation.status = Status.Queued
            new_simulation_run.status = Status.Queued
            db.session.commit()
        except Exception as ex:
            db.session.rollback()
            logger.error(f"Can not update the new simulation run status: {ex}")
            abort(400, message=f"Can not update a new simulation run status: {ex}")

        return new_simulation_run


@shared_task
def run_solver(simulation_run_id: int, json_path: str):
    """
    Celery task entry point to execute a solver method.

    The function loads the provided JSON file, determines the task type,
    calls the appropriate backend implementation, and handles post-
    processing including xlsx export, auralization, and updating
    database status fields. Errors transition the run and simulation to
    ``Status.Error``.

    Parameters
    ----------
    simulation_run_id : int
        Identifier of the run being executed.
    json_path : str
        Filesystem path to the JSON payload used by the solver.
    """

    from simulation_backend.DGinterface import dg_method
    from simulation_backend.DEinterface import de_method
    from simulation_backend.MyNewMethodInterface import mynewmethod_method

    from app.db import db
    from app.models import SimulationRun
    from app.types import Status

    # Create logger for this module
    logger.info(f"Running solver task for simulation_run_id: {simulation_run_id}")

    # Scoped session factory to ensure proper session management
    session_factory = sessionmaker(bind=db.engine)
    session = scoped_session(session_factory)()  # Create a new session for this thread

    try:
        simulation_run = session.query(SimulationRun).get(simulation_run_id)
        if simulation_run is None:
            logger.error(f"SimulationRun with id {simulation_run_id} not found")
            return

        logger.info(f"SimulationRun found: {simulation_run}")
        simulation = (
            session.query(Simulation)
            .filter_by(simulationRunId=simulation_run.id)
            .first()
        )

        if simulation_run:
            simulation_run.status = Status.Queued

        if simulation:
            simulation.status = Status.Queued
        session.commit()
        logger.info(f"Simulation(run) status updated to {simulation_run.status}")

        try:
            if simulation_run:
                simulation_run.status = Status.InProgress
            simulation.status = Status.InProgress
            session.commit()
            logger.info(f"SimulationRun status updated to {simulation_run.status}")

            result_container = {}
            if json_path is not None:
                with open(json_path, "r") as json_file:
                    result_container = json.load(json_file)

            taskType = TaskType(result_container["results"][0]["resultType"])
            logger.info(f"{taskType}")

            # save the simulation solver settings
            try:
                solverSettings = simulation.solverSettings
                with open(json_path, "r", encoding="utf-8") as file:
                    data = json.load(file)
                data["simulationSettings"] = solverSettings["simulationSettings"]
                data["settingsPreset"] = simulation.settingsPreset.value

                with open(json_path, "w", encoding="utf-8") as file:
                    json.dump(data, file, indent=4)
            except Exception as ex:
                logger.error(f"Error saving the simulation solver settings: {ex}")
                raise Exception(f"Error saving the simulation solver settings {ex}")

            match taskType:
                case TaskType.DE:
                    logger.info("DE method")
                    de_method(json_file_path=json_path)

                case TaskType.DG:
                    # DG METHOD
                    dg_method(json_file_path=json_path)
                    logger.info("DG method")

                case TaskType.MyNewMethod:
                    # MyNewMethod METHOD
                    mynewmethod_method(json_file_path=json_path)
                    logger.info("MyNewMethod")

                case _:
                    raise Exception("The selected tasktype is not valid!")

            if json_path is not None:
                with open(json_path, "r") as json_file_to_check:
                    data = json.load(json_file_to_check)

                # Update the specified field value
                if "should_cancel" in data:
                    if data["should_cancel"] == True:
                        logger.info("Cancelled: do not save to xlsx")
                    else:
                        logger.info("Saving to xlsx...")

                        # save the simulation result json to xlsx
                        if not ExportHelper.parse_json_file_to_xlsx_file(
                            json_path, json_path.replace(".json", ".xlsx")
                        ):
                            logger.error("Error saving the result to xlsx")
                            raise "Error saving the result to xlsx"

                        # db - save the xlsx file path
                        export = Export(
                            name=Path(json_path).name.replace(".json", ".xlsx"),
                            simulationId=simulation.id,
                        )
                        session.add(export)

                        # auralization: generate impulse response wav file
                        match taskType:
                            case TaskType.DE:
                                imp_tot, fs = auralization_calculation(
                                    None,
                                    json_path.replace(".json", "_pressure.csv"),
                                    json_path.replace(".json", ".wav"),
                                )
                            case TaskType.DG:
                                imp_tot, fs = auralization_calculation_DG(
                                    None,
                                    json_path.replace(".json", "_pressure.csv"),
                                    json_path.replace(".json", ".wav"),
                                )

                        # auralization: save the impulse response to xlsx
                        if not ExportHelper.write_data_to_xlsx_file(
                            json_path.replace(".json", ".xlsx"),
                            CustomExportParametersConfig.impulse_response,
                            {f"{fs}Hz": imp_tot},
                        ):
                            logger.error(
                                "Error saving the impulse response to xlsx"
                            )
                            raise "Error saving the impulse response to xlsx"
                                

                        
            result_container = {}
            if json_path is not None:
                with open(json_path, "r") as json_file:
                    result_container = json.load(json_file)

            if simulation_run:
                if result_container["should_cancel"]:
                    simulation_run.status = Status.Cancelled
                    simulation_run.completedAt = ""
                    simulation.status = Status.Cancelled
                    simulation.completedAt = ""
                else:
                    simulation_run.status = Status.Completed
                    simulation_run.completedAt = datetime.now()
                    simulation.status = Status.Completed
                    simulation.completedAt = datetime.now()

            simulation_run.updatedAt = datetime.now()
            simulation.updatedAt = datetime.now()

            session.commit()
            logger.info(f"SimulationRun status updated to {simulation_run.status}")
        except Exception as ex:
            simulation_run.status = Status.Error
            simulation.status = Status.Error
            session.commit()
            logger.error(f"Cannot run the method because: {ex}")

    except Exception as ex:
        session.rollback()
        logger.error(f"Cannot update simulation run: {ex}")

    finally:
        session.close()  # Ensure the session is closed after use
        logger.info(f"Session closed for simulation_run_id: {simulation_run_id}")


def get_simulation_result_by_id(simulation_id):
    """
    Fetch the raw result object stored for a completed simulation.

    Parameters
    ----------
    simulation_id : int
        Primary key of the simulation.

    Returns
    -------
    list
        ``results`` array from the JSON data.

    Raises
    ------
    HTTPException
        Aborts with ``400`` if the result file cannot be read.
    """
    simulation = get_simulation_by_id(simulation_id)
    model = model_service.get_model(simulation.modelId)
    json_path = file_service.get_file_related_path(
        model.outputFileId, simulation_id, extension="json"
    )

    try:
        with open(json_path, "r") as json_file:
            result_container = json.load(json_file)
    except Exception as ex:
        logger.warning(msg=f"No result available")
        abort(400, message=f"No result available")

    return result_container["results"]


def update_simulation_run_status(simulation_run, simulation):
    """
    Synchronize the ``percentage`` field of a run from its JSON file.

    Parameters
    ----------
    simulation_run : SimulationRun
        The run object to update.
    simulation : Simulation
        The parent simulation, used to locate the JSON path.
    """
    # TODO: update source percentage later
    model = model_service.get_model(simulation.modelId)
    json_path = file_service.get_file_related_path(
        model.outputFileId, simulation.id, extension="json"
    )
    with open(json_path, "r") as json_file:
        try:
            result_container = json.load(json_file)
            simulation_run.percentage = result_container["results"][0]["percentage"]
            db.session.commit()
        except Exception as ex:
            db.session.rollback()
            logger.warning(msg=f"Can not update percentage of the simulation run: {ex}")
            abort(400, message=f"Can not update percentage of the simulation run: {ex}")


def get_simulation_run_status_by_id(simulation_run_id):
    """
    Helper that returns a run and refreshes its percentage status.

    Parameters
    ----------
    simulation_run_id : int
        Identifier of the simulation run.

    Returns
    -------
    SimulationRun
        The updated run object with current percentage.
    """
    simulation = Simulation.query.filter_by(simulationRunId=simulation_run_id).first()
    if not simulation:
        logger.error(
            f"Simulation for the simulation run id {str(simulation_run_id)} does not exist!"
        )
        abort(400, message="Simulation doesn't exist!")

    simulation_run = SimulationRun.query.filter_by(id=simulation_run_id).first()
    if not simulation_run:
        abort(400, message="Simulation run doesn't exist!")

    update_simulation_run_status(simulation_run, simulation)

    return simulation_run


def cancel_solver_task(simulation_id):
    """
    Signal a running solver task to cancel and mark the JSON payload
    accordingly.

    The Celery task is revoked and the ``should_cancel`` flag in the
    JSON file is toggled so downstream logic avoids writing outputs.

    Parameters
    ----------
    simulation_id : int
        Identifier of the simulation whose task should be cancelled.

    Returns
    -------
    dict
        Message indicating cancellation request status.
    """
    simulation = get_simulation_by_id(simulation_id)

    if not simulation:
        logger.error(
            f"Simulation for the simulation id {str(simulation_id)} does not exist!"
        )
        abort(400, message="Simulation doesn't exist!")

    model = model_service.get_model(simulation.modelId)
    json_path = file_service.get_file_related_path(
        model.outputFileId, simulation_id, extension="json"
    )

    if json_path is not None:
        with open(json_path, "r") as json_file:
            data = json.load(json_file)
    else:
        logger.error(f"JSON file not found for simulation {simulation_id}")
        abort(400, message="Simulation data file doesn't exist!")

    taskID = data["task_id"]
    print(f"Canceling task: {taskID}")

    # Use current_app for better connection handling
    from celery import current_app

    try:
        # This is more reliable for revoking tasks in Flask
        current_app.control.revoke(taskID, terminate=True, signal="SIGKILL")
        logger.info(f"Successfully sent revoke command for task {taskID}")
    except Exception as e:
        logger.error(f"Error revoking task {taskID}: {str(e)}")
        # Continue execution to at least update the flag

    # Update the specified field value
    if "should_cancel" in data:
        data["should_cancel"] = True
    else:
        data["should_cancel"] = True  # Create the field if it doesn't exist

    print("should_cancel = " + str(data["should_cancel"]))
    print("json path: " + json_path)

    with open(json_path, "w") as json_result_file:
        json_result_file.write(json.dumps(data))

    return {"message": f"Cancellation request sent for task {taskID}"}
