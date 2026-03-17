# Developer Guidelines: Adding a new simulation method

If you have an open-source room acoustic simulation method you would like to add to the CHORAS back-end, you have come to the right place! _(Also, if you are reading this in preparation for the CHORAS Developer Workshop, you have found the right document :))_

## Before changing code

#### 1. Create a new Branch 

Use the format `sim/<your_method_name>` for your branch name in simulation-backend submodule so that your changes stay organized and isolated from the main codebase

#### Use SSH for Git (optional) 

If you want to authenticate via ssh (instead of the default https), change the repository URL by running this command in the backend root directory:

```shell
git remote set-url origin git@github.com:choras-org/simulation-backend.git
```

## Including your simulation method

#### 1. Create a new Folder
Add a new folder named `<method_name>_method` inside the **simulation-backend** submodule. This will contain everything related to your simulation method.

#### 2. Add an interface File
Inside your new folder, create a file named `<your_method_name>Interface.py` (see `MyNewMethodInterface.py` for reference).

This file defines the interface between CHORAS and your simulation method. It must include:

- A main interface function, e.g. `<your_method_name>_method()`, which:
  - Accepts the path to a `.json` input file as its argument.
  - Interprets the file data for your method.
  - Reports progress and results back to CHORAS (e.g., % complete, output data).
- A `main()` function that calls the above interface function for testing or standalone runs.

#### 3. Define Dependencies
Add a `requirements.txt` file inside your method's folder. Include your method's dependencies with **explicit version numbers**.

Prefer libraries that are installable via pip  
If your package is hosted in a git repository, you can install it using:

``` shell
git+https://gitprovider.com/user/project.git@{version}
```

Refer to the [Python Packaging Authority guide](https://packaging.python.org/en/latest/tutorials/installing-packages/#installing-from-vcs) for more options. **Note that providing a specific version number is important** to ensure reproducibility (and stability) of the results and CHORAS as a platform. If your method is not yet installable via pip, please refer to [packaging guidelines](https://packaging.python.org/en/latest/flow/) provided by the Python Packaging Authority.

#### 4. Create a Docker File
Add a `Dockerfile` in your folder (see the `MyNewMethod` folder for reference).

This file should define the environment setup required to build your simulation method's Docker image.
Guidelines of creating dockerfile is as follows:
- Specify the python version is being used by your method. Preferably make it with the stable versions
- Set the working directory as `/app`
- Install system dependencies for mesh generation and scientific computing. You can use the following lines to do this step:
``` shell
    RUN apt-get update && apt-get install -y
    git
    build-essential
    gmsh
    && rm -rf /var/lib/apt/lists/*
```

- Copy `requirements.txt` first and install with Docker layer caching
- Include all files your method needs (interface, example input, shared geometry/helpers)
- Define `CMD` command to run the main interface file.

#### 5. Provide an example Input File
Add an example file named `exampleInput_<Method>.json` inside the folder. This file will be used as a reference for the dynamic file being created by the backend itself when simulation is to be executed.

This JSON file demonstrates how CHORAS interacts with your method.
You can follow the example at `exampleInput_MyNewMethod.json`.

The .json file has the following structure:

```json
{
    "absorption_coefficients": {
        "floor": "0.6, 0.69, 0.71, 0.7, 0.63",
        "wall1": "0.6, 0.69, 0.71, 0.7, 0.63",
        "ceiling": "0.6, 0.69, 0.71, 0.7, 0.63",
        "wall2": "0.6, 0.69, 0.71, 0.7, 0.63",
        "wall3": "0.6, 0.69, 0.71, 0.7, 0.63",
        "wall4": "0.6, 0.69, 0.71, 0.7, 0.63"
    },
    "msh_path": "MeasurementRoom.msh",
    "geo_path": "MeasurementRoom.geo",
    "simulationSettings": {
        "mnm_1": 0.5,
        "mnm_2": 50.0
    },
    "results": [
        {
            "percentage": 100,
            "sourceX": 2,
            "sourceY": 2,
            "sourceZ": 1.5,
            "resultType": "MyNewMethod",
            "frequencies": [
                125,
                250,
                500,
                1000,
                2000
            ],
            "responses": [
                {
                    "x": 1,
                    "y": 1,
                    "z": 1.5,
                    "parameters": {
                        "edt": [],
                        "t20": [],
                        "t30": [],
                        "c80": [],
                        "d50": [],
                        "ts": [],
                        "spl_t0_freq": []
                    },
                    "receiverResults": []
                }
            ]
        }
    ]
}
```

#### 7. Add example settings
Add a JSON file describing your method's adjustable parameters in `example_settings/`.
Follow the format of `mynewmethod_setting.json`.

This file would have the following structure:
- At the top level there would be an object with the two fields:
  - `type`: Specified as `"SimulationSettings"`
  - `options`: Array of objects for settings options
- Each object in that array describes one configurable parameter and uses the following fields:
  - `name`: Human‑readable label shown in the UI, e.g. `"MyNewMethod parameter 1"`
  - `id`: Internal identifier used in backend/frontend logic, e.g. `"mnm_1"`. This must be unique per method.
  - `type`: Data type of the parameter value, e.g. `"flkoat"` (other types can be added if the system supports them, such as `"int"`, `"bool"`, `"string"`).
  - `display`: How this parameter is rendered in the UI, e.g. `"text"` for a text/number input field (could be other widgets if supported, such as sliders, dropdowns, etc.).
  - `min`: Minimum allowed value for numeric types. Used for validation and UI constraints.
  - `max`: Maximum allowed value for numeric types. Also used for validation and UI constraints.
  - `default`: Default value if the user does not provide one. Can be `null` if you want to force the user or backend to set it explicitly.
  - `step`: Increment used in the UI for numeric inputs (e.g. how much the value changes when the user uses arrow keys or a slider).
  - `endAdornment` *(optional)*: Optional string shown next to the field in the UI, often for units (e.g. `"dB"`, `"m"`, `"s"`). Empty string if not needed.

## Updating Method Configuration File in `simulation-backend` submodule

Finally, update the root file `method-config.json` in the `simulation-backend` directory.

This file lists all available simulation methods, so CHORAS can recognize yours.

- `simulationType`: The short name of the simulation acting as an identifier
- `containerImage`: Name for the container image to be made
- `envVars`: Dictionary of specific environment variables (if required) for Docker containers
- `label`: Name of the method
- `entryFile`: Python entry point to start execution
- `setting`: Setting file name so that it can be loaded in frontend and backend
- `repositoryURL`: Link to the original repository of the simulation method
- `documentationURL`: Link to the documentation of the simulation method

## Testing the Integration of New Method with CHORAS

Go to root CHORAS.

#### 1.  Docker Image Configuration
Open the `docker-compose.yml` and add your method under `services`:

```yaml
    services:
    # ... existing services ...
    mynew-method:                         # ← Your method name (kept as service name)
        platform: linux/amd64              # ← Keep unchanged
        build:
        context: ./simulation-backend    # ← Keep unchanged
        dockerfile: new_method/Dockerfile  # ← Path to your Dockerfile
        image: mynew_image:latest          # ← EXACTLY match methods-config.json
        profiles:
        - sim_method                     # ← Keep unchanged
```

#### 2. Update the Bash Script
In the root directory, go to the `CHORAS_BUILD.sh ` file and add the following commands based on your method before compose up:

``` bash
    # Export new method image for backend executor
    echo "📦 Exporting MyNewMethod image..."
    docker save -o backend/app/services/executors/mynew_image.tar mynew_image:latest
    echo "✅ Docker image exported: mynew_image.tar"
```

> **Replace**: `mynew_image.tar` & `mynew_image:latest` with your actual image name.


After this, delete the DB volume and container, and run the `CHORAS_BUILD.sh` bash command again.

## Debugging the Simulation Method Execution

If a simulation fails (you see a **"Simulation Failed"** alert at the top of the screen),
you can inspect the underlying container logs.

1. Open `backend/app/services/executors/local_executor.py`.

2. Locate the line that removes the container after execution (for example, a call that
   stops or removes the container when it finishes).

    ```python
    try:
        client = docker.from_env()
        container = client.containers.run(
            image=image,
            environment=env,  # JSON_PATH is the container path, valid in child too
            volumes={
                host_uploads_dir: {
                    "bind": container_uploads_dir,  # same path in child container
                    "mode": "rw",
                }
            },
            detach=True,
            working_dir=self.work_dir,
            name=container_name,
            # remove = True, # ← Comment This one
        )
        return container

    except Exception as e:
        logger.error(f"Failed to start Docker container: {e}")
        raise
    ```

3. Temporarily comment out that line so the container is not removed automatically.

4. Rebuild the image and container. With the container kept alive after the simulation ends, you can open your container
   runtime (e.g., Docker) and inspect the container logs to see detailed error messages
   and tracebacks for the simulation method execution.


## Next steps

If you have not yet run CHORAS fully (including frontend) please go to the [Installing CHORAS](./installing_choras.md) page for instructions on how to install CHORAS locally.

If you have previously installed CHORAS and want to test whether you can control your simulation backend using the CHORAS frontend, please continue to [Coupling your method to CHORAS](./choras_coupling.md).
