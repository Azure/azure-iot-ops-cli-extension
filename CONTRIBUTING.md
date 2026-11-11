# Contributing

This guide will assist you in setting up a local development environment for this extension.

## Fairfax ADO integrations

Use the existing integration pipeline with `cloud: AzureUSGovernment`,
`clusterRegion: usgovvirginia` and `runtimeChannels: [stable]`. Supply a Fairfax
ARM service connection, test subscription, dedicated resource group and the
Fairfax tenant's custom-locations service-principal object ID. The public-cloud
defaults for those inputs are not Fairfax credentials. Use an automation identity
with the required fixture and role-assignment permissions, not an interactive
user password stored in pipeline variables.

The same native ITs run unchanged. Planning rejects preview runtime and release
candidate qualification in Fairfax. Storage, schema registry and namespace
fixtures are placed explicitly in `usgovvirginia`, and observed resource locations
are required in the results. Plans, execution state and cleanup bind the cloud
as well as the approved subscription/group and exact attempt-owned resources.

Runtime and upgrade assertions use the Fairfax catalog. Local tox runs preserve
`AZURE_CONFIG_DIR`, `KUBECONFIG`, `REQUESTS_CA_BUNDLE` and `SSL_CERT_FILE`; use a
dedicated test cluster and isolated Azure profile. This enables execution but
does not establish that a particular service connection or runtime deployment
has passed live qualification.

We also regularly utilize GitHub Codespaces, and have automated this environment setup in our [devcontainer config](./.devcontainer/devcontainer.json)

## Released-version monitors

`.azure-devops/release-monitor.yml` is shared by six independent definitions:
`Azure IoT Operations CLI - Release Health (<Public|Fairfax> <v1|v2|v3>)`.
The slots mean newest, previous and third explicitly supported milestone, not CLI
version numbers. `.azure-devops/release-monitors.json` currently maps `v1` to `1.5`,
`v2` to `1.4` and `v3` to `1.3`. Update that reviewed mapping when support changes;
pipeline IDs, names, dashboard references and configured resource groups stay stable.
Discovery selects the newest published CLI patch for each configured stable runtime
family. A newer milestone does not automatically move or invalidate the selected
support window. Run titles and manifests record the slot and actual CLI/runtime versions.

Each run verifies GitHub's wheel SHA256, metadata, runtime profile and exact
released source. It uses that release's scenario configuration, tests and fixtures
with current native orchestration. The deployed AIO extension version/train must
match the selected cloud's bundled runtime. All planned scenarios, their latest
attempts, JUnit and cleanup must pass; monitor evidence cannot qualify a release.
No AIO Mooncake definitions are generated. Older releases without Fairfax profiles
are explicitly blocked, never redirected to the Public profile. Fairfax currently
supports only `v1`; `v2` and `v3` stay disabled and are rejected before acquisition.
The released Fairfax test-helper catalog is bound to the active cloud in every
pytest worker, without modifying product files or weakening runtime assertions.

Generate disabled definition payloads using an existing same-repository definition:

```bash
az pipelines build definition show --id 167 --org https://dev.azure.com/azureiotdevxp \
  --project 9c543948-e573-4146-832a-bf16b1531204 > baseline.json
python tools/release_monitor.py definitions \
  --configuration .azure-devops/release-monitors.json --baseline baseline.json \
  --branch refs/heads/<reviewed-automation-branch> --output definitions.json
```

Apply each payload through the ADO build-definitions API after the reviewed branch
exists. Reuse definition **167** for Public v1; update matching definitions rather
than creating duplicates. Integration **164** and Release **165** stay separate.
Payloads use `\official\release-health`,
disabled queueing, no triggers/schedules, and non-overridable variables. The runner
also checks definition name, repository and every configured target variable.
Never store personal account passwords or tokens in these files.

Keep all definitions disabled until an owner approves automation connections,
resource scopes/RBAC, capacity and live qualification. Each scenario attempt uses
the configured, pre-created resource group and distinct resources. All scenarios,
including Trust Bundle, can run concurrently without a cross-run lock. The runner
never creates or deletes a resource group. Cleanup must target only the attempt's
owned resources, including resources created by its test fixtures.
An administrator must provision the configured groups once and grant the service
identity the resource-specific deployment and RBAC operations needed within them;
do not grant subscription-wide Owner merely to make the pipeline pass.
Then enable queueing. Every health run executes the selected integration scenarios
and requires their results and cleanup evidence. Retries reuse
the first published release selection. No recurring schedule is supplied before
live execution and capacity are approved; apply the same schedule policy to the
IoT and AIO monitor sets. Fairfax needs its own ARM connection, subscription and
tenant-specific custom-locations object ID; a source PR does not qualify older wheels.
Historical source-health runs retained on definition 167 are not released-version evidence.

### Fixed-group isolation and recovery

Current ADO native, release-triggered and release-health attempts share only the
pre-created group, not their resource names. Main fixtures use a fresh 15-hex suffix;
released test helpers retain deterministic xdist collection but generate independent
runtime names. The pre-provisioning state artifact binds ownership to the cloud,
subscription, group, build, source/wheel, scenario, locations and retry attempt.
Legacy GitHub workflows and local tox execution are unchanged.

The test harness records creation intents before ARM writes and adds reserved
`cliTestOwner` metadata: tags on tracked roots, descriptions on role assignments,
and a parameter on ARM deployments. Only this metadata is hidden from test-visible
responses, preserving the selected tests' user-tag assertions and installed product
bytes. Ownership failures cannot qualify as expected-negative test successes.
Inline incremental deployments undergo ownership checks using ARM what-if.
That check is not atomic with the deployment; unique names minimize the remaining
collision window, and a pre-existing foreign owner is never adopted.

Cleanup rechecks each exact owner before deletion, waits for dependency ordering and
absence, and fails explicitly for unfinished creation or cleanup. It does not delete
the group or sweep unrelated resources. This cannot guarantee immediate deletion
after agent loss or an Azure outage. After the original attempt has stopped, retain
its state and event artifacts and retry exact-owner recovery with the approved
cloud profile and RG-scoped permissions:

```bash
python tools/owned_resources.py cleanup --manifest <original-state.json> \
  --cloud <AzureCloud-or-AzureUSGovernment> --subscription <original-subscription> \
  --resource-group <original-fixed-group>
```

Server-side ownership markers permit recovery of fixture resources even if the final
journal upload was lost. Recheck after outstanding Azure operations settle; recovery
is not release qualification. Never substitute a different attempt's manifest.

## Cloud-aware management clients

Pass the active cloud's ARM endpoint when constructing management clients through
the factories in `edge/util/az_client.py`. These factories derive the credential
scope from an explicit `endpoint` when `credential_scopes` is omitted.
Explicit scopes are preserved when the required token audience differs from the
endpoint. Without an endpoint override, generated clients retain their public-Azure defaults.
Constructing generated SDK clients directly with only an endpoint does not derive
the scope and can still produce an audience mismatch.

Providers derived from `Queryable` should use `_get_client_kwargs()`, including
for `PermissionManager` and `register_providers`. Other callers can pass
`CloudConfig(cmd).arm_client_kwargs` alongside the target subscription ID.
Preserve subscription IDs from resource references for cross-subscription operations.
These settings are for ARM clients only; Key Vault and other data-plane clients
must retain their service-specific scopes.

For Event Grid MQTT in Azure Government, the broker hostname uses
`*.eventgrid.azure.us`, but the token audience remains `https://eventgrid.azure.net`
(`https://eventgrid.azure.net/.default` for user-assigned managed identity scopes).
Resolve this through `CloudConfig.eventgrid_audience`; do not derive the audience
from the broker hostname. This does not change the Government authentication authority.
Existing endpoints with a `.us` audience need their authentication settings updated;
installing the fixed CLI alone does not repair deployed endpoints.

The request-level tests in
[`test_arm_cloud_unit.py`](./azext_edge/tests/edge/orchestration/test_arm_cloud_unit.py)
verify request hosts and requested credential scopes with mocked transport.
China endpoint coverage verifies configuration only, not live AIO service availability.
The permission-preflight helper coverage exercises the helper directly; it is not
currently called by the deployment workflow.

## Instance and child-resource APIs

Management-actions enablement uses `Instances.use_child_api()` before any external
write. Selection intersects the custom
location's enabled APIs for every required resource type with CLI-supported stable
APIs. Do not infer support from the runtime version or union unrelated types' APIs.
Validate the instance's custom-location ID before optional discovery or cache reuse.
Missing or invalid `extendedLocation.name` must fail before any external write;
invalid required instance state is not an optional-discovery failure.

Discovery uses `Microsoft.ExtendedLocation/customLocations/enabledResourceTypes/read`
when available, preserving the referenced subscription and active cloud endpoint.
Denied, unavailable, malformed, or empty discovery must not add a required permission
or block a previously authorized enablement. Never cache partial discovery results.
Validate collection, entry, and provider-namespace shapes before accepting discovery;
mixed valid/malformed metadata must discard the entire result, not imply missing support.
Validate each page envelope before SDK iterator flattening, including continuation-link
types and cycles. Cache capabilities only after all pages finish successfully.

The shared `Instances` client and the enablement client use the SDK retry-policy
seam to negotiate older supported stable APIs only for initial JSON instance or
child PUTs rejected with HTTP 400/404
`MissingAzureKubernetesMapping`. Do not parse error-message text, downgrade on unrelated
errors, replay accepted operations, or alter read/delete or deployment/upgrade clients.
Bound negotiation by the existing supported API enum, not a runtime-version table.
Keep negotiation inside one SDK retry lifecycle: preserve caller retry limits,
already-consumed retry budgets, and the remaining timeout across API transitions.
Without readable capabilities, pre-write compatibility verification is not guaranteed.

Show and disable preserve the baseline resource-provider reads/deletes without
capability discovery or additional permissions. Do not impose enablement's child-write
preflight on these paths or add speculative API-downgrade retries.

Other providers using `Instances` inherit rejected-PUT negotiation without adding
capability-discovery reads or permissions. This includes identity assignment,
instance updates, registry endpoints, connector templates and dataflow resources.
Management-actions enable retains its optional pre-write capability discovery.
Explicit `use_runtime_profile()` clients for deployment and upgrade disable
negotiation, even when the profile API matches the default. Preview and unknown
APIs are not negotiated to stable APIs. Adding an API to
`IoTOpsMgmtApiVersion` requires verifying generated operations and payload compatibility.
Description updates distinguish omitted (`None`, preserve) from explicitly empty
(`""`, clear), including restoration after runtime-channel integration checks.

The request-level regressions in
[`test_instance_api_unit.py`](./azext_edge/tests/edge/orchestration/test_instance_api_unit.py)
exercise real discovery and management-actions orchestration with mocked transport.
The existing management-actions payload tests mock discovery only; they do not prove
API compatibility. Live backward-compatibility testing must pair the candidate CLI
with an older, unupgraded AIO instance, not only a freshly deployed current runtime.


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

To assist in local development, it's suggested to utilize a local clone of the core [azure-cli](https://github.com/Azure/azure-cli) repository.

You may also utilize `azdev setup` (explained in [this later section](#install-and-configure-azure-cli-dev-tools)) to customize your local CLI installation, some options will download a version of CLI core on your behalf.

> IMPORTANT: When cloning the repositories and environments, ensure they are all siblings to each other. This makes things much easier down the line.

Example folder structure:
```text
source/
|-- .env3/
|-- azure-cli/
|-- azure-iot-ops-cli-extension/
|-- extensions/
```

The `extensions/` folder is optional, but allows you to isolate your installed extensions with an environment variable named `AZURE_EXTENSION_DIR` that points to it:

```powershell
$env:AZURE_EXTENSION_DIR="path/to/source/extensions"
```

Otherwise, you can utilize the default extension path `~/.azure/cliextensions`, but note that **this may cause conflicts** if your machine has an existing installation of `az` CLI and/or other CLI extensions.

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

    You should see `Extensions directory` with the value you set for `AZURE_EXTENSION_DIR`, or `~/.azure/cliextensions`:

    ```powershell
    Extensions directory 'path/to/source/extensions'
    ```

## Install dev extension

Inside your `azure-iot-ops-cli-extension` directory, run

```powershell
(env) pip install -U --target $env:AZURE_EXTENSION_DIR/azure-iot-ops
```

> Note, if you did not setup the `AZURE_EXTENSION_DIR` variable in the previous step, this value is `~/.azure/cliextensions`

### Verify environment is setup correctly

Run a command that is present in the iot extension space

```powershell
az iot ops -h
```

If this works, then you should now be able to make changes to the extension and have them reflected immediately in your `az` CLI.

## Unit and integration Testing


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

### Tox

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

## Pull requests

Pull request titles **must** follow the [conventional commits specification](https://www.conventionalcommits.org/en/v1.0.0/#specification) before merging. This ensures that our production-ready branches can be easily parsed and processed by downstream tooling and aids us in creating effective release notes.

Pull requests should be opened in `DRAFT` mode unless they are considered ready for review to prevent churn on code that is still changing.

To simulate most of the CI checks running against your code, you can run [`tox`](#tox) locally to check the linters and unit tests in an isolated environment.

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
