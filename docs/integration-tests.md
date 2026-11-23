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

  Our tests use `az-iot-ops-test-cluster` prefixes for cluster resources and `opskv` for keyvaults.

- #### Understanding the test scenario matrix

  The integration test workflow uses a scenario-based matrix system defined in [`.github/test-scenarios.yml`](../.github/test-scenarios.yml). Each scenario represents a specific test configuration with its own tox environment, initialization arguments, and runtime settings.

  Note: Any test without an exclusive mark will be marked as `edge`.

  ##### **Available Scenarios**

  - **edge**: Default edge/cluster tests (non-cloud)
  - **broker-diagnostics-removal**: Explicit-only, serial broker checks and support-bundle tests requiring absent retired diagnostics resources; see the [regression guide](../.github/workflows/README.md#broker-diagnostics-removal-regression)
  - **insecure-listener**: Tests with insecure listener deployment
  - **rpsaas**: Cloud-side (RPSaaS) tests
  - **upgrade**: Azure IoT Operations upgrade tests (runs serially)
  - **runtime-channel**: Shared update and cross-channel refusal tests (runs serially)
  - **upgrade-path**: Actual older-to-newer upgrade tests; explicitly selected with pinned baselines
  - **mgmtactions**: Azure IoT Operations management actions tests (runs serially)
  - **livedata**: Live Data rejection tests on stable and lifecycle tests on preview (runs serially)
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
  - `manual_only`: Whether explicit selection is required (excluded from default/scheduled runs)
  - `env`: Custom environment variables for the scenario

  ##### **Selecting Scenarios**

  Use the `test-scenarios` input to run specific scenarios (comma-separated):
  ```yaml
  with:
    test-scenarios: "rpsaas,upgrade"
  ```

  If not specified, all standard scenarios run on both channels. The `upgrade-path`
  scenario requires explicit selection and baseline definitions.
  The `broker-diagnostics-removal` scenario also requires explicit selection.

### GA and preview qualification

The workflow expands each selected scenario into independent **stable** and **preview**
jobs by default. These labels mean the intended runtime channel; the actual deployment
train can still be `integration` for an internal candidate. Each job provisions its own
temporary k3s/Arc cluster and separately named instance, storage, schema registry and
ADR namespace. No existing cluster is converted between channels.

The CI setup creates the ADR namespace in `australiaeast`, independently of the cluster
region. ADR live-data support is unavailable in `westus2`, and `eastus` is a hybrid
RPaaS/DirectRP region where namespaces created with the existing API can be delayed
replicating to DirectRP. `australiaeast` is a fully VNext region recommended by the ADR
team; the namespace creation command and API remain unchanged for both runtime channels.
Namespaced devices inherit the namespace region, and namespaced assets
inherit their device's region. Storage and schema registry locations are unchanged.
This override applies to CI setup; local init tests retain their existing location defaults.

- `runtime-channels: "stable,preview"` runs both channels; select one explicitly for troubleshooting.
- `init` is identical on both channels. Only preview **create** receives `--use-preview --yes`.
- Extra init/create arguments must not contain `--use-preview`, `--ops-version`, or `--ops-train`;
  the matrix owns runtime selection. Existing feature-mode arguments remain independent.
- Shared scenario tests run unchanged on both deployments. The serial `runtime-channel`
  scenario checks shared update behavior and rejects cross-channel upgrades, including with force.
  It also verifies that connector list and show succeed on preview and are rejected on stable
  with the specific preview-runtime error. An unrelated CLI or service error fails the test.
  Show is tested directly with a known metadata reference without first invoking list.
  The preview list path also inspects returned first-party metadata references using the same instance target.
- The `livedata` scenario runs on both channels: stable tests verify that all three commands
  fail with the preview-runtime restriction and leave instance/runtime configuration unchanged;
  preview tests exercise enable, show, disable, idempotency and role assignments.
  Stable jobs do not create Live Data Event Grid resources or identities.
- Create and each subsequent suite verify the **installed** `currentVersion`, release train,
  runtime channel, associations and readiness. Qualification assertions are hard failures,
  even when the legacy `init-continue-on-error` option is set.
- Results, coverage and cleanup are isolated by scenario and channel. Running both channels
  roughly doubles runtime-dependent jobs; jobs can be scheduled sequentially to reduce peak cost.

Both `az iot ops connector list` and `show` require an instance and resource group and
independently check the installed runtime's preview eligibility and readiness. Show fetches
the supplied `--ref` directly; no earlier list invocation, purchase or connector deployment is required.
Connector listing uses the
installed CLI's bundled preview profile for its management API version and first-party
connector metadata compatibility version. Both commands accept valid
preview `integration` identities without requiring their version to match the bundled
create/upgrade target. This opt-in does not change other commands' qualification rules.
The cluster version is not used to select connector metadata. Results reflect compatibility
with the CLI's preview target, not a guarantee of compatibility with an older installed runtime;
live API and connector compatibility must be verified separately.

For internal upgrade validation, `--ops-train integration` or `--ops-train dev` may
change the deployment train within the installed runtime channel. `--ops-version`
is optional: without it, the CLI uses its bundled target without downgrading an
installed newer version. Use an explicit version to target an unbundled main build,
for example `--ops-version 1.6.999-main.20261114.12 --ops-train dev`.
`--force` bypasses GA version compatibility checks, not GA/preview boundaries.
Dev builds use the GA upgrade profile; integration builds retain their GA or preview
classification. This does not grant Public Preview capabilities to dev builds or
qualify a production upgrade path.
Preview boundaries, cluster readiness, foundation compatibility and manual upgrade
ownership (`autoUpgradeMinorVersion=false`) remain enforced.

For opt-in live GA-to-dev and dev-to-dev validation, use a dedicated Public Azure
GA instance with automatic upgrades disabled. Set `azext_edge_instance`,
`azext_edge_rg`, and `azext_edge_internal_upgrade_versions` to two published,
ascending dev versions separated by a comma. Leave `azext_edge_runtime_channel`
and `azext_edge_upgrade_args` unset and run
`tox -e python-upgrade-int -- -k test_internal_dev_upgrades`
using the existing wheel/SHA256 inputs. The test upgrades the same
instance twice and verifies each installed version/train and readiness.
It intentionally leaves the instance on the second dev build; do not use a
shared GA/preview qualification instance. Ordinary runs skip this test.

#### Workload identity scheduling

Workload-identity jobs (`python-wlif-int`, the `trustbundle` scenario) do not use
cross-run concurrency locks. Jobs use the configured shared test resource group,
with independent clusters and instances. The OPC UA certificate fixtures generate
stable per-instance SecretSync names and pass `--secret-sync-name` to every add,
show, and remove command. This isolates the resource-group-scoped ARM resources
as well as their Kubernetes secret references. Without this option, existing CLI
certificate resource names and behavior are preserved.

The configured resource group is never created or deleted by the runner. Existing
deployment and role-assignment permissions on that group remain necessary; no new
subscription-wide RBAC administration grant is required by this test isolation.
Cleanup remains limited to the attempt's resources. Stable/preview jobs and
independent runs can execute in parallel; `parallel: false` still runs tests
sequentially within each instance.

Published release-monitor pipelines (`release-monitor*.yml`) test frozen wheels
that predate `--secret-sync-name` and still create the fixed-name SecretSync
resources. Release-monitor `TrustBundle` stages therefore keep `maxParallel: 1`,
and Public Azure runs sharing `ops-cli-int-test-rg` serialize the stage across
tracks via the `ops-wlif-a386d5ea-ea90-441a-8263-d816368c84a1-ops-cli-int-test-rg`
environment **Exclusive lock** (`TrustBundleLock`). Retain that environment check
while any release-monitor track tests a pre-`--secret-sync-name` wheel. Distinct
resource names do not isolate subscription quotas, throttling, or scheduled cleanup.

Each integration attempt remains responsible for cleaning its own resources.
Scenario teardown skips its fallback Azure CLI login only when an offline proof
step verifies the runner's completed cleanup state against its task-output digest,
current run, attempt, row, candidate, and successful ownership checks. The runner
emits that digest only after owned-resource cleanup, local cluster shutdown, and
the final state write succeed. Missing, changed, foreign, or incomplete evidence
retains fallback cleanup; cancellation always retains it. Test and authentication
failures remain failures even when cleanup succeeds.

`Cluster Resource Cleanup` is explicit maintenance, not a scheduled job: its
whole-group sweep can delete in-flight instances even when their names are unique.
Run it only when the selected resource group is idle. If the default branch still
contains the old schedule, keep that workflow disabled until the no-schedule
revision is merged.

For manual Azure Pipelines Integration runs, select **Cluster region** (default
`westus2`). The frozen plan uses this region for Arc cluster creation and the run
title, for example `ops-integration-123 (eastus2) (edge) (preview)`. The runner checks
that the connected cluster is in the selected region. Health continues to use its
Library profile, and release children explicitly select `westus2`. Storage, schema
registry, and namespace location behavior is unchanged.

The ADO runner captures hook Job status, namespace Pod status, and bounded current
and previous container logs for hooks and unhealthy Pods while tests run, before
Helm rollback can remove them. On failure it also attempts namespace events and the
owned K3s unit journal before cleanup. Event snapshots prioritize warnings and recent
events, retain complete JSON records within the size limit, and report omitted counts.
Failed attempts also retain Pod/container security contexts, bound volume metadata,
and read-only permission inspection of verified, owned local-path volume directories.
The collector never changes filesystem permissions.
Sanitized snapshots are
published early as `ops-diagnostics-<row>-<attempt>` artifacts and retained under
`diagnostics` in the normal attempt artifact. Secrets, kubeconfig contents, pod
environment values and Helm values are not collected. Collection errors are warnings;
they never replace the original test failure or prevent cleanup. The selected
scenario execution budget remains enforced, with separate outer-job headroom for
preparation, diagnostics and teardown. Hard agent termination can still prevent
the final upload; already-published snapshots remain available.

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

#### ADO retry dependencies and Branch Health

Native integration, Release Health, and Branch Health publish `dependencies-<row>-<stage>-<job>`
before provisioning. Each snapshot binds the run, definition, automation commit, candidate
SHA256, Python minor version, platform and matrix row. The host and candidate extension
have **separate** name/version constraints and METADATA hashes; an upgrade baseline has a
third environment. Conflicting host/extension versions are intentional and are not merged.
The connectedk8s tool and its dependencies are retained as a hash-verified installed-tree
artifact, rather than rediscovered on retry. Candidate reinstalls verify the original
inventory before every test phase. A missing, conflicting or mismatched snapshot fails
closed: start a new run instead of silently resolving new packages. These are run-scoped
locks, not permanent dependency pins or wheelhouse guarantees.

The fixed definitions in [branch-health.json](../.azure-devops/branch-health.json) belong in
`\official\branch-health`, alongside `\official\release-health`:

* **Azure IoT Operations CLI - Branch Health (Public GA)** — stable runtime.
* **Azure IoT Operations CLI - Branch Health (Fairfax GA)** — stable runtime.
* **Azure IoT Operations CLI - Branch Health (Public Preview)** — preview runtime.

There is no supported Fairfax Preview definition and no `Runtime` suffix. Definition YAML
may run from the reviewed automation branch, but the product is always `refs/heads/dev`.
Prepare freezes its SHA once per run; Build checks out that SHA independently, builds one
wheel, and publishes it before planning tests. Build retries restore that exact wheel.
The source bundle records the real branch, product/test SHA, separate automation SHA,
cloud/runtime profile, source inventory and wheel digest. Source and wheel product bytes
must match; only explicitly audited test-only compatibility may be applied.
Branch compatibility has two tiers, computed after acquiring the selected source.
A digest of non-unit `azext_edge/tests/**` plus `.github/test-scenarios.yml` matching the
reviewed v2.11.2 tree permits the existing corrections: Public gets only SecretSync;
Fairfax also gets the four reviewed file replacements and four ADR case exclusions.
Other test trees receive **no replacements**: Public runs natively, and Fairfax retains
only the four exclusions if their file hashes still match and AST inspection confirms
the default ADR API is `2026-04-01`. API/excluded-file drift fails Prepare for re-review.
Thus rewritten fixtures run natively rather than receiving stale automation copies.
The frozen manifest records the tree digest, reviewed baseline and excluded-file hashes.
Bundle verification recomputes the plan, staging checks original files, and pytest requires
the staged `AZEXT_OPS_TEST_COMPATIBILITY` receipt instead of inferring branch skips from a
commit ID. Product bytes are never patched. Published-release rules remain commit-specific;
pytest additionally checks their receipt exclusions against those existing rules.

Dry run performs acquisition/build/lint/unit without Azure integration. Integration mode
additionally gates native scenarios, serialized Trust Bundle and final evidence on the
selected source's lint/unit results. Fixed wrappers expose mode, Python and applicable
Public region controls, never source/cloud/runtime overrides. Existing manual pipeline
164 remains available for PR/ad-hoc source. Release Health support slots `v1/v2/v3/preview`
continue to consume published wheels unchanged.

Definition setup requires authorizing the existing `iotupx-ops-integration` pool,
`sc-iot-ops-cli-public-it` (Public) or `sc-iot-ops-cli-fairfax-it` (Fairfax) service connection,
and Public's existing shared Trust Bundle environment/exclusive lock. Profiles reuse
the current subscriptions and resource groups, including Fairfax's `v1` group. No new
secret variables are required. The reviewed Public daily schedules and held Fairfax
plans are listed in [Contributing](../CONTRIBUTING.md#released-version-monitors).
Retain all run artifacts through retries.
Health-only definitions use repository property `reportBuildStatus: 'false'`: results
remain in ADO/the dashboard instead of attaching health status to the automation commit.
Normal PR CI, manual integration 164 and release 165 keep their existing status reporting.
Storage fixtures already explicitly disable blob public access; their existing network
and shared-key settings are independent and are preserved.

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
**test-scenarios** | *Comma-separated scenarios (e.g., "rpsaas,upgrade"). Empty selects standard scenarios, excluding opt-in upgrade-path and broker-diagnostics-removal.*
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

#### Device Registry API version
Generic ADR reads and cleanup commands for the GA integration path explicitly use
`2026-04-01`, matching the extension's ADR client. Azure CLI can otherwise select
a newer advertised API instead of the provider's `defaultApiVersion`, which can
make GA-created resources appear missing during the ADR v2 rollout. Mixed-resource
cleanup applies this pin only to `Microsoft.DeviceRegistry`; other providers and
explicitly versioned preview calls are unchanged. Changing regions is not a
substitute for keeping the API version consistent across the resource lifecycle.

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