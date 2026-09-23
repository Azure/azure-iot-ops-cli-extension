We have built our [integration test workflow](#running-our-integration-test-workflow-from-an-external-repo) to be reused by external repositories.

For customers wanting to run their own cluster configuration tests and checks, we have also created [github actions](#using-github-actions-to-independently-connect-a-cluster-to-arc-andor-deploy-aio) to both connect your cluster to ARC, and deploy AIO resources to the cluster.

## Running our integration test workflow from an external repo

We have an [integration test pipeline](./.github/workflows/int_test.yml) that other (public or private) repositories can utilize in order to trigger our CLI tests against a live cluster.

There are, however, some prerequisites and caveats that users should be made aware of.

### Prerequisites

- #### Service Principal and Federated Pipeline Permissions

  Our pipeline runs CLI commands to create and destroy resources using OpenID Connect.
  You will need to create or update an Entra application in Azure and configure it to federate a service principal connection from the repo/branch you plan to run your tests from.
  This service principal should also have correct permissions on the resource group you run these tests against.

  More information can be found in the following links:
  - [Use GitHub Actions to connect to Azure](https://learn.microsoft.com/en-us/azure/developer/github/connect-from-azure?tabs=azure-portal%2Clinux#use-the-azure-login-action-with-openid-connect)
  - [Configuring OpenID Connect in Azure](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-azure)


- #### Dedicated Resource Group for Testing
  You should provide a dedicated resource group for these testing resources.
  During the tests, resources will be created that may not be automatically cleaned up and are typically hidden from default Azure Portal UI views.

  The integration and container-test workflows default to **ops-cli-int-test-centralus-rg**.
  This dedicated group must exist in **centralus** in the pipeline's subscription, with the federated pipeline
  identity granted the required permissions. The workflows do not provision the group.
  Apply `DO_NOT_DELETE=true` to match the persistent test-group convention; this tag only affects external cleanup
  automation that explicitly honors it and is not an Azure deletion lock.

  New resources use the existing location defaults: ADR namespaces and schema registries inherit the group's
  location, while custom locations and AIO instances follow the Arc cluster's location. No ADR-specific overrides
  are needed, including for resources created independently by tests. Verify actual resource locations on a live run.
  The smoke-test asset query uses the selected group's location.

  Central US is a regional workaround for the mixed ADR v1/v2 routing reported in West US during the direct-RP
  cutover; API versions are unchanged. To use another supported region, select a dedicated test group there through
  the `resource-group` input. Moving existing resources between groups does not change their locations.

  The scheduled [cleanup workflow](../.github/workflows/cluster_cleanup.yml) targets the same default group and
  deletes **all resources** in it. Do not share the group with non-test workloads or overlap tests with cleanup.
  Post-test and scheduled cleanup preserve the group itself, so it does not need to be recreated before each run.
  These workflows do not check preservation tags. Remaining resources in the previous group need separate cleanup;
  that group is no longer targeted by scheduled cleanup. For a custom group, use the `resource_group` cleanup input.

  Our tests use `az-iot-ops-test-cluster` prefixes for cluster resources and `opskv` for keyvaults.

- #### Understanding the test scenario matrix

  The integration test workflow uses a scenario-based matrix system defined in [`.github/test-scenarios.yml`](../.github/test-scenarios.yml). Each scenario represents a specific test configuration with its own tox environment, initialization arguments, and runtime settings.

  Note: Any test without an exclusive mark will be marked as `edge`.

  ##### **Available Scenarios**

  - **edge**: Default edge/cluster tests (non-cloud)
  - **insecure-listener**: Tests with insecure listener deployment
  - **rpsaas**: Cloud-side (RPSaaS) tests
  - **upgrade**: Azure IoT Operations upgrade tests (runs serially)
  - **runtime-channel**: Shared update and cross-channel refusal tests (runs serially)
  - **upgrade-path**: Actual older-to-newer upgrade tests; explicitly selected with pinned baselines
  - **mgmtactions**: Azure IoT Operations management actions tests (runs serially)
  - **livedata**: Preview Live Data lifecycle and GA rejection/no-mutation checks (runs serially)
  - **redeploy**: Tests cluster redeployment functionality
  - **trustbundle**: Workload identity federation tests

  ##### **Scenario Configuration**
  Each scenario in `test-scenarios.yml` can specify:
  - `tox_env`: The tox environment to run (e.g., `python-rpsaas-int`)
  - `init_args`: Additional `az iot ops init` arguments
  - `create_args`: Additional `az iot ops create` arguments
  - `needs_trust`: Whether trust bundle setup is required
  - `test_redeploy`: Whether to test redeployment
  - `parallel`: Whether tests run in parallel (default: true)
  - `env`: Custom environment variables for the scenario

  ##### **Selecting Scenarios**

  Use the `test-scenarios` input to run specific scenarios (comma-separated):
  ```yaml
  with:
    test-scenarios: "rpsaas,upgrade"
  ```

  If not specified, all standard scenarios run on both channels. The `upgrade-path`
  scenario requires explicit selection and baseline definitions.

### GA and preview qualification

The workflow expands each selected scenario into independent **stable** and **preview**
jobs by default. These labels mean the intended runtime channel; the actual deployment
train can still be `integration` for an internal candidate. Each job provisions its own
temporary k3s/Arc cluster and separately named instance, storage, schema registry and
ADR namespace. No existing cluster is converted between channels.

- `runtime-channels: "stable,preview"` runs both channels; select one explicitly for troubleshooting.
- `init` is identical on both channels. Only preview **create** receives `--use-preview --yes`.
- Extra init/create arguments must not contain `--use-preview`, `--ops-version`, or `--ops-train`;
  the matrix owns runtime selection. Existing feature-mode arguments remain independent.
- Shared scenario tests run unchanged on both deployments. The serial `runtime-channel`
  scenario checks shared update behavior and rejects cross-channel upgrades, including with force.
  The serial `livedata` scenario exercises preview-only `enable`, `show` and `disable`:
  preview runs the lifecycle with system/user-assigned identities and role-scope checks;
  GA rejects all three commands and compares configuration before/after without using
  the restricted `live-data show` command for setup. Future preview-only features should
  follow the same success/rejection pattern. These tests cover provisioning, not DOE-owned
  streaming sessions.
- Create and each subsequent suite verify the **installed** `currentVersion`, release train,
  runtime channel, associations and readiness. Qualification assertions are hard failures,
  even when the legacy `init-continue-on-error` option is set.
- Results, coverage and cleanup are isolated by scenario and channel. Running both channels
  roughly doubles runtime-dependent jobs; jobs can be scheduled sequentially to reduce peak cost.

#### The same candidate wheel everywhere

One `build-candidate` job builds the wheel and publishes its SHA256. Every integration job
downloads that exact artifact and verifies its digest and installed package bytes. Both
workflow CLI commands and tox environments use it; tox never rebuilds the checkout.
The test runner stages only test sources alongside the installed package, changes to an
isolated working directory and checks the CLI extension path to prevent source-tree shadowing.
The candidate fingerprint is included with each job's JUnit artifact.
Init and redeployment write separate JUnit reports. Final coverage and result uploads run
after all test stages and cleanup, even on failure, so redeployment evidence is retained.

For local integration runs, first build a candidate wheel, then set `azext_edge_wheel`
to its absolute path and `azext_edge_wheel_sha256` to its SHA256 digest. Set
`azext_edge_runtime_channel` to `stable` or `preview`, along with the normal cluster,
resource-group and instance settings. The existing tox environments remain available;
`python-runtime-int` selects the isolated channel tests. Local test runs still create
and modify real Azure resources—collection and unit tests do not qualify a live runtime.

#### Containerized end-to-end tests

The [container workflow](../.github/workflows/container_int_test.yml) also accepts
`runtime-channels` (default `stable,preview`). It builds one candidate wheel per workflow
invocation, then provisions independent clusters/resources for its two channel jobs.
The host uses that verified wheel for setup; each test container receives the same wheel
through a read-only mount, together with its digest, runtime channel and target instance.
The image contains the test harness, not a separately rebuilt extension under test.
Shared `init` is unchanged; only preview `create` receives the selector and consent flags.

Container exit failures fail the job. Channel-labelled artifacts retain JUnit, coverage
data and the candidate fingerprint even when tests fail. Direct use of the test image
likewise requires mounting a candidate wheel and supplying `azext_edge_wheel` (the path
inside the container), `azext_edge_wheel_sha256`, `azext_edge_runtime_channel`, and the
normal target/authentication/kubeconfig inputs. Mount a results directory and set
`azext_edge_junit_path` and `azext_edge_coverage_file` to paths inside it to retain reports.

#### Actual version upgrades versus reconciliation

The default `upgrade` scenario tests same-version reconciliation/configuration updates.
It is **not** evidence of an older-to-newer upgrade.

Select `test-scenarios: "upgrade-path"` explicitly for actual upgrades and provide
`upgrade-baselines`, a JSON object keyed by each selected channel. Each definition requires:

| Field | Meaning |
|---|---|
| `wheel_url` | Credential-free HTTPS URL of the pinned older CLI wheel; no signed query strings |
| `sha256` | Exact baseline wheel digest |
| `version` | Expected installed source runtime version |
| `train` | Actual source deployment train |
| `create_args` | Explicit create arguments understood by that older CLI, including any required consent |

The candidate initializes the shared foundation. The isolated baseline CLI provisions the
older instance; candidate assertions then verify that the expected source runtime is really
installed. Only the **candidate wheel** executes upgrade and verifies that the installed
version advanced to its bundled target without changing channel/train or instance identity.

Baseline versions must be older, same-channel and same-train. Historical `integration`
identities must already have an explicit reviewed mapping in the candidate catalog; inputs
cannot inject mappings or bypass production upgrade protections. No baseline versions are
guessed, and omitted definitions fail an explicitly requested upgrade-path job rather than
silently substituting a current-version deployment. Supply migration-specific assertions
when a release handoff requires them. Baseline downloads/installation are separate from
candidate qualification; no baseline artifact replaces the candidate in other tests.

The default scenario selection excludes `upgrade-path` until baseline inputs are supplied
and that scenario is explicitly selected. Release qualification must include both ordinary
channel jobs and the approved upgrade paths; a default green run alone does not prove upgrades.

### Inputs

#### In order to run our integration test pipline from your repo, you must provide the following secrets to our workflow in order to use the federated Azure login action:
  | Secret | Description |
  |---|---|
  **AZURE_CLIENT_ID** | *Entra Application client ID*
  **AZURE_TENANT_ID** | *Azure Tenant ID*
  **AZURE_SUBSCRIPTION_ID** | *Azure Subscription ID*

#### The following values are also required in order to run the `az iot ops init` command, which uses this service principal to deploy AIO to a cluster:
| Secret | Description |
|---|---|
**AIO_SP_APP_ID** | *Entra Application client ID*
**AIO_SP_OBJECT_ID** | *Entra Application Object ID*
**AIO_SP_SECRET** | *Entra Application Client Secret*

#### Test input values:
| Input | Description |
|---|---|
**resource-group** | *The resource group to run tests in*
**test-scenarios** | *Comma-separated scenarios (e.g., "rpsaas,upgrade"). Empty selects standard scenarios, excluding opt-in upgrade-path.*
**runtime-channels** | *Comma-separated channels; defaults to stable,preview with independent clusters.*
**upgrade-baselines** | *Pinned baseline definitions keyed by channel; required when selecting upgrade-path.*
**custom-locations-oid** | *Custom Locations Object ID - used to enable cluster-connect feature.*
**runtime-init-args** | *Additional init arguments (beyond cluster name, resource group, schema registry)*
**runtime-create-args** | *Additional create arguments (beyond cluster name, resource group, instance name)*
**init-continue-on-error** | *Continue on error for init integration tests.*
**keep-on-failure** | *Number of minutes to keep the cluster(s) active on failure (max 240 min).*

### Example workflow

```yaml
name: Run AIO CLI integration tests

on:
  workflow_dispatch:
    inputs:
      resource-group:
        type: string
        default: my-aio-resource-group
      test-scenarios:
        type: string
        description: "Comma-separated scenarios (e.g., 'rpsaas,upgrade')"
        default: ""

permissions:
    id-token: write
    contents: read

jobs:
    run-integration-tests:
        uses: azure/azure-iot-ops-cli-extension/.github/workflows/int_test.yml@dev
        with:
            resource-group: ${{ inputs.resource-group }}
            test-scenarios: ${{ inputs.test-scenarios }}
            custom-locations-oid: "custom-locations-object-id"
        secrets:
            AZURE_CLIENT_ID: ${{ secrets.AZURE_CLIENT_ID }}
            AZURE_SUBSCRIPTION_ID: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
            AZURE_TENANT_ID: ${{ secrets.AZURE_TENANT_ID }}

```

### Outputs

Currently this pipeline does not output values, it simply displays test pass/fail results.

### Considerations

#### CLI Extension Builds
The workflow builds one candidate wheel from its checked-out source revision and shares the
hash-verified artifact across all runtime-channel jobs. Integration tox environments require
that artifact instead of installing from the source tree.

## Using github actions to independently connect a cluster to ARC and/or deploy AIO

We have two custom actions for [connecting a kubernetes cluster to ARC](../.github/actions/connect-arc/action.yml), and for [deploying AIO resources](../.github/actions/deploy-aio/action.yml).
Both actions assume you have already logged into azure in your agent.

If a `config` value is provided, it will be written to disk as `~/.kube/config` and used to connect to your cluster. Otherwise, your local `~/.kube/config` file will be used.

- ### connect-arc
  This action is used to connect your kubernetes cluster to Azure ARC using `az connectedk8s connect`. It will add the connectedk8s Azure CLI extension if not already installed.

  If your logged-in azure principal doesn't have access to query graph, you'll also need to provide the `Custom Locations OID` in order to enable the `custom-locations` feature on your cluster.

- ### deploy-aio
  This action is used to deploy Azure IoT Operations resources to an existing ARC-connected cluster using the `azure-iot-ops` CLI extension.
  It will attempt to install our latest extension version from the public index using `az extension add` if not already installed in the agent.


### Example workflow steps

First, create a local cluster and store the kubeconfig in an environment variable:
```yaml
- name: "Create local k3s cluster"
  run: |
    sudo apt install nfs-common
    curl -sfL https://get.k3s.io | K3S_KUBECONFIG_MODE="644" INSTALL_K3S_EXEC="server" sh -s -
- name: "Store kubeconfig in environment variable"
  id: kubeconfig
  run: |
    {
      echo 'CONFIG<<EOF'
      sudo k3s kubectl config view --raw
      echo EOF
    } >> "$GITHUB_ENV"
```
Next, login to azure and connect your local cluster to ARC using inputs named `resource-group` and `cluster-name` (as well as your custom locations OID and a reference to your kubeconfig environment variable):
```yaml
- name: "Azure login"
  uses: azure/login@v3
  with:
    client-id: ${{ secrets.AZURE_CLIENT_ID }}
    tenant-id: ${{ secrets.AZURE_TENANT_ID }}
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
- name: "ARC connect cluster"
  uses: azure/azure-iot-ops-cli-extension/.github/actions/connect-arc@dev
  with:
    cluster-name: ${{ inputs.cluster-name }}
    resource-group: ${{ inputs.resource-group }}
    config: ${{ env.CONFIG }}
    custom-locations-oid: 51dfe1e8-70c6-4de5-a08e-e18aff23d815
```

Finally, deploy AIO to the connected cluster using your previous inputs as well as the resource ID of your Key Vault and your Service Principal secrets:
```yaml
- name: "Deploy AIO"
  uses: azure/azure-iot-ops-cli-extension/.github/actions/deploy-aio@dev
  with:
    cluster: ${{ inputs.cluster-name }}
    resource-group: ${{ inputs.resource-group }}
    config: ${{ env.CONFIG }}
    keyvault-id: ${{ secrets.KV_ID }}
    sp-app-id: ${{ secrets.AZURE_CLIENT_ID }}
    sp-object-id: ${{ secrets.AZURE_OBJECT_ID }}
    sp-secret: ${{ secrets.AZURE_CLIENT_SECRET }}
```