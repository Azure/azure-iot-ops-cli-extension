# Tox Testing Guide

[Tox](https://tox.wiki/) is a CLI tool used to run various python testing environments with specific dependencies.

## Summary of Tox Environments

Our [current tox config](../tox.ini) contains the following environments, and can be listed by running `tox -av`:

- **lint**: Runs `flake8` and `pylint` for linting the code.
  - Command: `flake8 azext_edge/`, `pylint azext_edge/`

- **python, py38, py39, py310, py311, py312**: Runs unit tests using a specific python version. `python` will run the default version from your `PATH`
  - Command: `pytest -k _unit ./azext_edge/tests`

- **python-{init,e2e,rpsaas,wlif,edge,all}-int**: Runs integration tests for specific scenarios.
  - Scenarios:
    - `python-init-int`: Tests for `ops init`/create.
    - `python-e2e-int`: End-to-end pipeline tests.
    - `python-rpsaas-int`: RPSaaS (cloud side) only.
    - `python-wlif-int`: Workload identity setup required.
    - `python-edge-int`: All non-RPSaaS tests (edge).
    - `python-all-int`: All non-init related tests.
  - Command: `pytest -k "_int.py" -m {SCENARIO}` (uses pytest markers to determine tests)

- **coverage**: Generates code coverage reports in JSON, HTML, and terminal formats.
  - Command: `pytest -k _unit --cov --cov-report=json --cov-report=html --cov-report=term:skip-covered`

## Running Tox Locally
In order to run tox testing environments as currently configured, you must install tox, either as part of the dev requirements (`pip -r dev_requirements.txt`) or on your machine / virtualenv with `pip install tox`.

Specific test run / environment strings can be passed to tox with `-e "env"` for a single environment, or `-e "env1, env2"` for multiple environments.

If you need to add additional inputs to `pytest` - you can do so by using `--` as a separator, like below (only last failing tests [--lf], very verbose [-vv]):
 
  `tox -e "python" -- --lf -vv`

## Notes
- The first time you run a new environment in tox, it will perform some setup tasks and dependency installation which will incur some overhead, but ensuing test runs will be able to skip this step.

- Tox virtual environments are each created under the `./.tox` folder - be cautious of having too many of these locally because they can eat disk space with copies of dependencies if not maintained.

- Tox can detect dependency / command changes in tox.ini and other related settings, but does not check files external to tox (code, dev_requirements, etc). 

- In order to rebuild a tox environment, you need to run tox with the `-r` switch.