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
  - Inputs:
    - `resource_group`: `string` - Resource Group to test in
    - `cleanup`: `bool` - Attempt to clean up test resources after integration tests complete
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
