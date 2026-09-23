# Tox Testing Guide

[Tox](https://tox.wiki/) is a CLI tool used to run various python testing environments with specific dependencies.

## Summary of Tox Environments

Our [current tox config](../tox.ini) contains the following environments, and can be listed by running `tox -av`:

- **lint**: Runs `flake8` and `pylint` for linting the code.
  - Command: `flake8 azext_edge/`, `pylint azext_edge/`

- **python, py3\***: Runs unit tests using a specific python version. `python` will run the default version from your `PATH`
  - Command: `pytest -k _unit ./azext_edge/tests`

- **python-{init,e2e,rpsaas,upgrade,runtime,mgmtactions,livedata,long,wlif,edge,all}-int**: Runs integration tests for specific scenarios.
  - Scenarios:
    - `python-init-int`: Tests for `ops init`/create.
    - `python-e2e-int`: End-to-end pipeline tests.
    - `python-rpsaas-int`: RPSaaS (cloud side) only.
    - `python-upgrade-int`: Azure IoT Operations upgrade tests.
    - `python-runtime-int`: Isolated, serial runtime-channel update/boundary checks.
    - `python-mgmtactions-int`: Azure IoT Operations management actions tests.
    - `python-livedata-int`: Preview Live Data lifecycle and GA rejection/no-mutation tests, run serially.
    - `python-long-int`: Long-running tests.
    - `python-wlif-int`: Workload identity setup required.
    - `python-edge-int`: All non-RPSaaS tests (edge).
    - `python-all-int`: All non-init related tests.
  - Uses the wheel-only integration runner and pytest scenario markers.
  - Requires `azext_edge_wheel` (absolute candidate wheel path) and `azext_edge_wheel_sha256`.
    The candidate is verified and installed into each isolated tox environment; the checkout
    is never installed as the extension under test. Unit-test environments still test source.
  - Set `azext_edge_runtime_channel=stable` or `preview` and the normal `azext_edge_*` target
    environment variables. The runner does not inherit a parent pytest configuration's
    environment overrides, so explicitly export the intended cluster/resource group/instance.
  - Tests are staged alongside the candidate package; reports are written back to the checkout.
    See [dual-channel qualification](integration-tests.md#ga-and-preview-qualification) for baseline upgrade inputs.
  - Optional `azext_edge_junit_path` sets an absolute JUnit report path; otherwise each tox
    environment writes its own report under the checkout's JUnit directory. CI uses separate
    init and redeployment paths so a later failure cannot overwrite the first phase's report.
    Optional `azext_edge_coverage_file` sets the coverage data path for a mounted container
    results directory; by default coverage continues accumulating in the checkout.

  Note: any test without an explicit mark will be grouped into `edge` tests.

- **report**: Generates code coverage reports in JSON, HTML, and terminal formats.
  - Use **tox -e clean** to reset local coverage files, as most tests run with `--cov-append` by default
  - Tox installs `coverage` and runs `coverage report`
  - Pytest version: `pytest -k _unit --cov --cov-report=json --cov-report=html --cov-report=term:skip-covered`

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