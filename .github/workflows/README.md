## Template / automated actions:
- Tests
  - [azdev_linter.yml](azdev_linter.yml)
  - [security_checks.yml](security_checks.yml)
  - [codeql.yml](codeql.yml)
- Build / Release Tasks
  - [ci_build.yml](ci_build.yml)
  - [release_build.yml](release_build.yml)
  - [stage_release.yml](stage_release.yml)
  - [upload_wheel.yml](upload_wheel.yml)
- Scheduled Tasks
  - [Cluster Cleanup](cluster_cleanup.yml)
  <!-- - [update_private_index.yml](update_private_index.yml) -->

## Top-level / triggered workflows:
- ### [Tox tests](tox.yml)
Run unit tests and linter
- ### [Integration tests](int_test.yml)
Run tests (including AIO deployment) against a live cluster.
Uses a scenario-based matrix system defined in [`.github/test-scenarios.yml`](../test-scenarios.yml).
Cluster name, schema registry, and instance name will be auto-populated during the workflow run.
  - Inputs:
    - `resource-group`: `string` - Resource Group to test in
    - `test-scenarios`: `string` - Comma-separated list of scenarios to run (e.g., "rpsaas,upgrade"). If empty, all non-manual scenarios run.
    - `custom-locations-oid`: `string` - Custom Locations OID
    - `runtime-init-args`: `string` - Additional init arguments (beyond cluster name, resource group, schema registry)
    - `runtime-create-args`: `string` - Additional create arguments (beyond cluster name, resource group, instance name)
    - `init-continue-on-error`: `bool` - Continue on error for init integration tests
    - `keep-on-failure`: `number` - Number of minutes to keep cluster(s) active on failure (max 240 min)
  - Available Scenarios:
    - `edge`: Default edge/cluster tests
    - `broker-diagnostics-removal`: Explicit-only, serial edge tests requiring a backend without the retired broker diagnostics Service/pods. Excluded from scheduled/default runs.
    - `insecure-listener`: Tests with insecure listener deployment
    - `rpsaas`: Cloud-side (RPSaaS) tests
    - `upgrade`: Azure IoT Operations upgrade tests (runs serially)
    - `redeploy`: Tests cluster redeployment functionality
    - `trustbundle`: Workload identity federation tests (runs serially)

#### Broker diagnostics removal regression

Run **Integration tests** on a branch containing the PR changes with
`test-scenarios` set to `broker-diagnostics-removal`. The workflow checks out its
selected branch, not an arbitrary fork PR head; use an upstream branch containing
the changes, or a fork configured with the required Azure credentials and OIDC access.

Set `runtime-create-args` to the version/train arguments for the backend release
that removes `aio-broker-diagnostics-service`. The removal release is not pinned
here because it has not yet been identified. Running against an older deployment
with the Service or pods still present fails explicitly; the test does not delete
resources or treat missing prerequisites as a successful skip.

The scenario enables `azext_edge_broker_diagnostics_removal=true` and runs the
existing edge suite, including `test_mq_check_diagnostics_removal`. This focused
test requires a deployed broker, verifies Service/pod absence before and after the
checks, waits up to five minutes for the broker portion of the summary to become
healthy, and validates successful structured output and retained runtime/configuration
checks at all three detail levels. Other services do not have to be healthy for
this focused test. Each CLI/kubectl subprocess has a timeout.

For an already configured local test environment and connected removal-release
cluster, the same regression can be run with:

```bash
azext_edge_broker_diagnostics_removal=true pytest \
  azext_edge/tests/edge/checks/int/test_mq_int.py::test_mq_check_diagnostics_removal -v
```

The focused regression is intentionally skipped outside this explicit scenario.
A passing live run of it covers the corresponding manual checks; collection or a
skipped result does not.

- ### [Cluster Cleanup](cluster_cleanup.yml)
Used to clean up a resource group after AIO deployment testing.
  - Inputs:
    - `cluster_prefix`: `string` - Prefix of cluster / associated resources to delete
    - `resource_group`: `string` - Resource Group to clean up
    - `keyvault_prefix`: `string` - Prefix of keyvault resources to delete
- ### [CI Build and Test](ci_workflow.yml)
CI checks to ensure build / unit test success
  - Jobs:
    - [Build](ci_build.yml)
    - [Tox Test](tox.yml)
    - [AZDev Linter](azdev_linter.yml)
- ### [Build and Publish Release](release_workflow.yml)
Secure build, test, and release pipeline. Requires approval to deploy artifacts to github / storage account.
  - Inputs:
    - `continue_on_error`: `bool` - (Break-Glass scenario) Whether to continue build / release if pre-checks fail.
    - `github_release`: `bool` - whether to [stage github release](stage_release.yml)
    - `upload_wheel`: `bool` - whether to [Upload the wheel to storage](upload_wheel.yml)
  - Jobs (*conditional):
    - [Security Checks](security_checks.yml)
    - [Build](release_build.yml)
    - [Tox Test](tox.yml)
    - [AZDev Linter](azdev_linter.yml)
    - [Draft a github release](stage_release.yml) *
    - [Upload the wheel to storage](upload_wheel.yml) *
