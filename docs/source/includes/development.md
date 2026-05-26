# Developer Guidelines: Adding a new simulation method

If you have an open-source room acoustic simulation method you would like to add to the CHORAS back-end, you have come to the right place! _(Also, if you are reading this in preparation for the CHORAS Developer Workshop, you have found the right document :))_

## Before changing code

1. Please create a branch of this repository (`sim/<your_method_acronym>`) so that you can work on this freely.

2. If you want to authenticate via ssh (instead of the default https), run the following command (navigated to the root of the `backend` repository) to change the url:

``` shell
git remote set-url origin git@github.com:choras-org/backend.git
```

## Including your simulation method

1. Add your repository as a submodule to the root of the `backend` repository. Make sure that the repository is public so that others will be able to clone/use it too.

2. Add your method to the requirements.txt list using `-e` ("editable"), meaning changes to the code will immediately reflect without the need to reinstall.

3. Add a file to the `simulation-backend/simulation_backend` folder called `<your_method_acronym>interface.py`. _(Please refer to `MyNewMethodInterface.py` in the same folder for an example.)_

    This file will contain the interface between CHORAS and your simulation method and will contain two main parts:

    - **a function** (`<your_method_acronym>_method()`) **describing the interface between the contents of a .json file and your simulation method**. The function _must_ take as its argument the .json path with the user data. This will also be used to communicate information (% done, results, etc.) back to the user. Eventually, this function will be called by `app/services/simulation_service.py`, but for now, it will be called by...
    - ...**a main function** that can call the aforementioned function.

4. In the `simulation-backend/simulation_backend/__init__.py` file import everything from the interface file in the simulation-backend package \_\_init\_\_.py file:

    ```python
    from <your_method_acronym>interface import <your_method_acronym>_method
    ```

5. Navigated to the `backend` folder run

    ``` shell
    conda activate choras
    pip install -r requirements.txt
    ```

    to install.

## Input file

If you navigate to `simulation-backend/simulation_backend/headless_backend/input/`, you'll find several .json files. These files are used as input for the headless backend and have the same format as the .json files used by CHORAS to communicate with the simulation methods.

The .json file has the following structure:

- Absorption coefficients (we deliberately changed the unique identifier to human-readable identifiers)
  - `"unique identifier": "125Hz, 250Hz, 500Hz, 1000Hz, 2000Hz"`
- Geometry file names
  - The files live in `simulation-backend/simulation_backend/headless_backend/input/`
- Simulation settings. These are the simulation-specific settings defined in the `backend/example_settings` folder
  - `"id": value`
- Results (* these fields get filled by the simulation method)
  - Percentage*: how far is the simulation along
  - Source position: `sourceX`, `sourceY`, `sourceZ`
  - Result type: this is your method acronym
  - Frequency band to simulate
  - Responses
    - Receiver position: `x`, `y`, `z`
    - Room-acoustic parameters*: `edt`, `t20`, `t30`, `c80`, `d50`, `ts`, `spl_t0_freq`
    - Impulse response*: `receiverResults`

Below is the `exampleInput_MyNewMethod.json` file (in `simulation-backend/simulation_backend/headless_backend/input/`). In the same folder, please create a new `exampleInput_<your_method_acronym>.json` file based on this file:

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

That's it! You are now ready to create the interface between CHORAS and your simulation method. For those of you who are familiar with CHORAS, you will notice that you don't need any processes (`npm`, `flask`, `celery`) to run in order to test the interface.

## Next steps

If you have not yet run CHORAS fully (including frontend) please go to the [Installing CHORAS](./installing_choras.md) page for instructions on how to install CHORAS locally.

If you have previously installed CHORAS and want to test whether you can control your simulation backend using the CHORAS frontend, please continue to [Coupling your method to CHORAS](./choras_coupling.md).
