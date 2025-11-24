# Getting Started

Here you will see what you need to do to run the backend application.

## Pre-requisites

1. The latest version of git: <https://git-scm.com/downloads>
2. Conda: <https://www.anaconda.com/download>

## Initialising this repository

Gentle reminder: you are currently in the `backend` repository, not the `CHORAS` parent repository. The instructions below therefore refer to the `backend` repository and neither involve the `CHORAS` nor `frontend` repositories.

1. Clone [the backend repository](https://github.com/choras-org/backend) to a location of your choice.
2. In the command window / terminal, navigate (`cd`) to the (`backend`) repository.
3. Run the following line of code to check out the correct versions of the (nested) submodules:

``` shell
git submodule update --init --recursive
```

4. The repository should now have the latest (correct) state.
5. Every time you make changes to submodules, remember to run

``` shell
git submodule update --recursive
```

to include the correct commits of all the submodules.

## Setting up the environment

1. In the command window, navigate (`cd`) to navigate to the `backend` folder.
2. Create a new environment and install all the requirements by running the following (this will take a minute)

```shell
conda create -n choras python=3.11
conda activate choras
pip install -r requirements.txt
```

## Running example code

You are now ready to run some example code!

1. Navigate (`cd`) to `backend/simulation-backend/simulation_backend`.
2. Make sure you are in the correct environment by running

```shell
conda activate choras
```

3. Run

```shell
python MyNewMethodInterface.py
```

4. The command window should show a counter running from 0 to 100.
5. Try some of the other interface files (e.g. `DGinterface.py`) and see what happens.

## Next steps
If you are only interested in coupling your simulation method to the CHORAS backend, (i.e., avoiding the CHORAS frontend) please proceed to [Developer Guidelines: Adding a new simulation method](./development.md). 

Otherwise please proceed to the next page.