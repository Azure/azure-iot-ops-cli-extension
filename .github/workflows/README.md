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
    - `test-scenarios`: `string` - Comma-separated list of scenarios to run (e.g., "rpsaas,upgrade"). If empty, all scenarios run.
    - `custom-locations-oid`: `string` - Custom Locations OID
    - `runtime-init-args`: `string` - Additional init arguments (beyond cluster name, resource group, schema registry)
    - `runtime-create-args`: `string` - Additional create arguments (beyond cluster name, resource group, instance name)
    - `init-continue-on-error`: `bool` - Continue on error for init integration tests
    - `keep-on-failure`: `number` - Number of minutes to keep cluster(s) active on failure (max 240 min)
  - Available Scenarios:
    - `edge`: Default edge/cluster tests
    - `insecure-listener`: Tests with insecure listener deployment
    - `rpsaas`: Cloud-side (RPSaaS) tests
    - `upgrade`: Azure IoT Operations upgrade tests (runs serially)
    - `redeploy`: Tests cluster redeployment functionality
    - `trustbundle`: Workload identity federation tests (runs serially)
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
