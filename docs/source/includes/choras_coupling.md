# Coupling your method to CHORAS

Before following the steps below, make sure you followed the steps in [Installing CHORAS](./installing_choras.md).

To couple the interface you just created to CHORAS, please change the following files:

#### app/models/data/simulation_settings.json

- Add a new entry to the simulation_settings.json list.
In a terminal window, navigate to the `backend` using `cd <your/path/to/CHORAS>/backend/`
- Activate the conda environment:

  ```shell
  conda activate choras
  ```

- Run

  ```shell
  flask reset-db
  ```

  to add the new setting to the database.

#### example_settings/<new_file>.json

Add a new .json to the example_settings folder and define your settings based on the examples.json file. The `id`s should be the same as the ones you used when creating your interface.

#### app/types/Task.py

- Add your method to the TaskType(Enum)

#### app/services/simulation_service.py

- In the `run_solver` function import the method from the interface:

``` python
from simulation_backend.<your_new_interface> import <your_new_interface_method>
```

- Add a case to `match taskType` from which this method will be called.

``` python
case TaskType.<your_new_tasktype>:
    <your_new_interface_method>(json_file_path=json_path)
```

### Install

Finally, in the `choras` environment, run

``` shell
pip install -r requirements.txt
```

to install.
