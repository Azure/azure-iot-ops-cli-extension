# Running integration tests from an external repo

We have an [integration test pipeline](./.github/workflows/int_test.yml) that other (public or private) repositories can utilize in order to trigger our CLI tests against a live cluster.

There are, however, some prerequisites and caveats that users should be made aware of.

## Prerequisites

### Service Principal and Federated Pipeline Permissions

Our pipeline runs CLI commands to create and destroy resources using OpenID Connect.
You will need to configure an Entra application in Azure and configure it to allow a service principal connection from the repo/branch you plan to run your tests from.

More information can be found in the following links:
- [Use GitHub Actions to connect to Azure](https://learn.microsoft.com/en-us/azure/developer/github/connect-from-azure?tabs=azure-portal%2Clinux#use-the-azure-login-action-with-openid-connect)
- [Configuring OpenID Connect in Azure](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-azure)


### Dedicated Resource Group for Testing
You should provide a dedicated resource group for these testing resources.
During the tests, resources will be created that cannot be easily cleaned up and are typically hidden from default Azure Portal UI views.

We also have a scheduled [cleanup workflow](../.github/workflows/cluster_cleanup.yml) that does a best-effort cleanup of all AIO-related resources in a particular resource group - this will attempt to clean up all resources that start with a particular "prefix" or are related to clusters with a similar prefix.

Our tests use `az-iot-ops-test-cluster` for cluster resources and `opstestkv` for keyvaults. Without parameters, all resources with these prefixes (or that reference custom locations with these prefixes) will be deleted by the cleanup action.

## Inputs

In order to run these tests, you must provide the following service principal values to our pipeline in order to use the federated Azure login:
| Secret | Description |
|---|---|
**AZURE_CLIENT_ID** | *Entra Application client ID*
**AZURE_TENANT_ID** | *Azure Tenant ID*
**AZURE_SUBSCRIPTION_ID** | *Azure Subscription ID*

The following values are also required in order to run the `az iot ops init` command, using the same service principal in order to deploy AIO to a cluster:
| Secret | Description |
|---|---|
**AIO_SP_APP_ID** | *Entra Application client ID*
**AIO_SP_OBJECT_ID** | *Entra Application Object ID*
**AIO_SP_SECRET** | *Entra Application Client Secret*

The final set of inputs are more traditional workflow inputs:
| Input | Description |
|---|---|
**resource-group** | *The resource group to run tests in*
**cleanup** | *An optional boolean switch that decides whether to attempt post-test cleanup rather than waiting for a scheduled cleanup job*

## Outputs

Currently this pipeline does not output values, but it does store cluster support bundles as workflow artifacts

## Considerations

### CLI Extension Builds
Currently our pipeline uses the most recent dev branch of the IoT Operations extension to build our extension. The extension repo is cloned from the `dev` branch, the wheel is built from that source, and then added to the agent's CLI extension path.

### Cleanup
As mentioned [above](#dedicated-resource-group-for-testing), these tests create resources that cannot be easily cleaned up (besides deleting and recreating the entire resource group).

Please use the [cleanup workflow](../.github/workflows/cluster_cleanup.yml) for cleaning up leftover resources.
You can call this workflow automatically after the integration tests by including setting the `cleanup` input to `True`, or you can schedule / invoke the workflow as you wish.

#### **Important**

Running cleanup from the integration test workflow will **only delete resources created in that test run**.

Calling cleanup on a schedule will  **delete all resources with our given prefixes**.

Calling the [cleanup workflow](../.github/workflows/cluster_cleanup.yml) as a reusable workflow requires the following inputs and secrets, and similar permissions as described [above](#service-principal-and-federated-pipeline-permissions)

| Input | Description |
|---|---|
**cluster_prefix** | *prefix of clusters to delete*
**resource_group** | *resource group to delete resources in*
**keyvault_prefix** | *prefix of keyvaults to delete*

| Secret | Description |
|---|---|
**AZURE_CLIENT_ID** | *Entra Application client ID*
**AZURE_TENANT_ID** | *Azure Tenant ID*
**AZURE_SUBSCRIPTION_ID** | *Azure Subscription ID*