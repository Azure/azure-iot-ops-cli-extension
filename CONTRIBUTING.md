# Contributing

This guide will assist you in setting up a local development environment for this extension.

We also regularly utilize GitHub Codespaces, and have automated this environment setup in our [devcontainer config](./.devcontainer/devcontainer.json)


> You can run all commands in this setup in `bash` or `cmd` environments, this documentation just shows the `powershell` flavor.

## Dev Setup

1. Get Python 3: https://www.python.org/downloads/

## Install and initialize a virtual environment

1. Create a virtual environment (example, named 'env3')

    ```powershell
    python -m venv env3
    ```


2. Activate your virtual environment

    Windows:

    ```powershell
    ./env3/Scripts/activate
    ```
    
    Unix: 
    
    ```bash
    source ./env3/bin/activate
    ```

> IMPORTANT: Ensure you keep this Python virtual environment. It is required for development.

## Local repository clones

### [azure-iot-ops-cli-extension](https://github.com/Azure/azure-iot-ops-cli-extension)


```powershell
git clone https://github.com/Azure/azure-iot-ops-cli-extension
```
### [azure-cli](https://github.com/Azure/azure-cli)

```powershell
git clone https://github.com/Azure/azure-cli
```

> IMPORTANT: When cloning the repositories and environments, ensure they are all siblings to each other. This makes things much easier down the line.

```text
source-directory/
|-- azure-cli/
|-- azure-iot-ops-cli-extension/
|-- .env3/
```

To assist in local development, it's suggested to utilize a local clone of the core [azure-cli](https://github.com/Azure/azure-cli) repository.

You may also utilize `azdev setup` (explained in the next section) to customize your local CLI installation.

## Install and configure [Azure CLI dev tools](https://github.com/Azure/azure-cli-dev-tools)

With your **virtual environment activated**:

1.  ```powershell
    (env) pip install azdev
    ```

2.  ```powershell
    (env) azdev setup -c ./path_to/azure-cli
    ```

    `azdev setup` can utilize your local copy of the `azure-cli` repository, or it can download one for you:
    - `azdev setup -c ./path_to/azure-cli` will use your local copy of the `azure-cli` repo
    - `azdev setup -c EDGE` will install the current dev branch of the `azure-cli` repo
    - `azdev setup` with no arguments provides an interactive setup experience
    - `azdev setup -h` will display other configuration options.

3. Verify your CLI is configured correctly:

    ```powershell
    (env) az -v
    ```

    You should see `Python location` with a Python executable in your local `env3` path:

    ```powershell
    Python location 'C:\src\azure-iot-ops-cli-extension\env3\Scripts\python.exe'
    ```

## Install dev extension

You can isolate your development extensions in a separate folder to aid in debugging.

Create a new folder for your extensions, and create an environment variable named `AZURE_EXTENSION_DIR` that points to it:

```powershell
mkdir "/path/to/source/extensions"
$env:AZURE_EXTENSION_DIR="path/to/source/extensions"
```

Otherwise, you can utilize the default extension path `~/.azure/cliextensions`, but note that **this may cause conflicts** if your machine has an existing installation of `az` CLI and/or other CLI extensions.

Inside your `azure-iot-ops-cli-extension` directory, run

```powershell
(env) pip install -U --target $env:AZURE_EXTENSION_DIR/azure-iot-ops
```

#### Verify environment is setup correctly

Run a command that is present in the iot extension space

```powershell
az iot ops -h
```

If this works, then you should now be able to make changes to the extension and have them reflected immediately in your `az` CLI.

## Unit and Integration Testing


Our tests are located inside `azext_edge/tests/`:
- `azext_edge/tests/edge` - core functionality tests
- `azext_edge/tests/utility` - utility unit tests

Inside `azext_edge/tests/edge` - the tests are broken up by category:

- `checks` - Check tests
- `init` - Init tests
- `mq` - Tests for MQTTBroker
- `orchestration` - Init/Create/Clone orchestration tests
- `rpsaas` - Cloud resource provider tests
- `support` - Support bundle tests

We support running tests locally using [Tox](https://tox.wiki/) - our [Tox testing guide](./docs/tox-testing.md) has more detailed information on our configuration.


Tox can be installed as part of our [`dev requirements`](./dev_requirements.txt), which are required to run tests locally:

```powershell
pip install -r path/to/source/dev_requirements.txt
```

To see available tox environments:

```powershell
tox -av
```

To run linters and unit test checks inside their own virtual environments, simply run:

```powershell
tox 
```

### Unit Tests


Unit tests end in `_unit.py` so execute the following command to run all unit tests:
```powershell
pytest -k "_unit.py"
```

Execute the following command to run the support bundle unit tests:

```powershell
pytest azext_edge/tests/edge/support -k "_unit.py"
```

### Integration Tests

> Integration tests are run against Azure resources and depend on various configured environment variables. Some tests also require a connection to a connected cluster with Azure IoT Operations deployed.

You can create a local `pytest.ini` using our [example file](./pytest.ini.example) by running:

```powershell
cp ./pytest.ini.example ./pytest.ini
```

Integration tests end in `_int.py` so execute the following command to run all integration tests,
```powershell
pytest -k "_int.py"
```

Example int tests runs:

_Init:_
```powershell
pytest azext_edge/tests/edge/init/int/test_init_int.py
```

_All support bundle int tests:_
```powershell
pytest azext_edge/tests/edge/support/create_bundle_int -k "_int.py"
```

You can also target specific test functions in any test file, such as:

```powershell
pytest azext_edge/tests/edge/checks/int/test_dataflow_int.py::test_dataflow_check
```
## Suggested tools and IDE configuration


### VSCode setup

1. Install VSCode

2. Install the required extensions
    * [`ms-python.python`](https://marketplace.visualstudio.com/items?itemName=ms-python.python) is recommended
    * [`python black`](https://marketplace.visualstudio.com/items?itemName=ms-python.black-formatter) for linting and auto-formatting


3. Set up `settings.json`

    ```json
    {
        "python.pythonPath": "path/to/source/env3/Scripts/python.exe",
        "python.venvPath": "path/to/source/",
        "python.linting.pylintEnabled": true,
        "python.autoComplete.extraPaths": [
            "path/to/source/env3/Lib/site-packages"
        ],
        "python.linting.flake8Enabled": true,
        "python.linting.flake8Args": [
            "--config=setup.cfg"
        ],
    }
    ```

4. Set up `launch.json`
    ```json
    {
        "version": "0.2.0",
        "configurations": [
            {
                "name": "Azure CLI Debug (Integrated Console)",
                "type": "python",
                "request": "launch",
                "pythonPath": "${config:python.pythonPath}",
                "program": "${workspaceRoot}/../azure-cli/src/azure-cli/azure/cli/__main__.py",
                "cwd": "${workspaceRoot}",
                "args": [
                    "--help"
                ],
                "console": "integratedTerminal",
                "debugOptions": [
                    "WaitOnAbnormalExit",
                    "WaitOnNormalExit",
                    "RedirectOutput"
                ],
                "justMyCode": false
            }
        ]
    }
    ```

    * launch.json was derived from [this](https://raw.githubusercontent.com/Azure/azure-cli/dev/.vscode/launch.json) file

    * Note: your "program" path might be different if you did not set up the folder structure as siblings as recommended above

    * Note: when passing args, ensure they are all comma separated.

    Correct:

    ```json
    "args": [
        "--a", "value", "--b", "value"
    ],
    ```

    Incorrect:

    ```json
    "args": [
        "--a value --b value"
    ],
    ```
5. You should now be able to place breakpoints in VSCode and see execution halt as the code hits them.

### Python command-line debugging

https://docs.python.org/3/library/pdb.html

1. `pip install pdbpp`
2. If you need a breakpoint, put `import pdb; pdb.set_trace()` in your code
3. Run your command, it should break execution wherever you put the breakpoint.

## Microsoft CLA

This project welcomes contributions and suggestions.  Most contributions require you to agree to a
Contributor License Agreement (CLA) declaring that you have the right to, and actually do, grant us
the rights to use your contribution. For details, visit https://cla.microsoft.com.

When you submit a pull request, a CLA-bot will automatically determine whether you need to provide
a CLA and decorate the PR appropriately (e.g., label, comment). Simply follow the instructions
provided by the bot. You will only need to do this once across all repos using our CLA.
