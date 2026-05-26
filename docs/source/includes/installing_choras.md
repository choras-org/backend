# Installing CHORAS

To run CHORAS, three processes need to be active:

- The frontend (`npm run dev`)
- The backend (`flask run`)
- Celery (`celery -A app.celery worker --loglevel=info -P eventlet`)

Don't worry about the commands above (yet). These are for future reference.

The following steps will guide you through the process of setting up and running these processes.
Please refer to the [Getting Started](./getting_started.md) guide to for setting up the environment and required python packages if you have not done so already.

Note that the order in which the backend and frontend applications are started does not matter.
The frontend application is not even required to be running for the backend to work.

## Creating the database

1. Navigated to the `backend` folder and with the `choras` environment active, create the database by running `flask create-db` (you only have to do this once).

## Running the backend processes

### Starting the database server

Navigated to the `backend` folder and with the `choras` environment active, run the application by running

``` shell
flask run
```

You have succeeded in running the backend if you see something like this in the command window:

``` shell
WARNING: This is a development server. Do not use it in a production deployment. Use a production WSGI server instead.
 * Running on http://127.0.0.1:5001
Press CTRL+C to quit
 * Restarting with watchdog (fsevents)
 * Debugger is active!
 * Debugger PIN: 903-417-292
```

Note that in order to run the application correctly, this command window should remain open with the `flask run` process running.

### Running Celery (open a new command window)

Celery is a package that allows for distributed task queueing. In the case of CHORAS, it allows to offload the simulation to a separate "worker" so that other processes (such as queueing other tasks) will not be blocked.

To run Celery:

1. Open a new command window and navigate to the `backend` folder.
2. Activate the previously created environment by running `conda activate choras`.
3. Run Celery by running:

``` shell
celery -A app.celery worker --loglevel=info -P eventlet
```

4. You should see something like:

``` shell
 -------------- celery@TUE031950 v5.4.0 (opalescent)
--- ***** -----
-- ******* ---- Windows-10-10.0.19045-SP0 2025-02-02 14:47:11
- *** --- * ---
- ** ---------- [config]
- ** ---------- .> app:         ui_backend:0x2bc5d65f640
- ** ---------- .> transport:   sqla+sqlite:///C:\Users\20225896\repositories\CHORAS\backend\celerydb.sqlite
- ** ---------- .> results:     sqlite:///C:\Users\20225896\repositories\CHORAS\backend\celerydb.sqlite
- *** --- * --- .> concurrency: 12 (eventlet)
-- ******* ---- .> task events: OFF (enable -E to monitor tasks in this worker)
--- ***** -----
 -------------- [queues]
                .> celery           exchange=celery(direct) key=celery


[tasks]
  . app.services.simulation_service.run_solver

[2025-02-02 14:47:11,628: INFO/MainProcess] Connected to sqla+sqlite:///C:\Users\20225896\repositories\CHORAS\backend\celerydb.sqlite
[2025-02-02 14:47:11,645: INFO/MainProcess] celery@TUE031950 ready.
```

## Running the frontend

Please refer to <https://github.com/choras-org/CHORAS/blob/dev/README.md#frontend-installation-open-a-new-command-window> for instructions on how to install and launch the frontend. 
