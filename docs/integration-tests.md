We have built our [integration test workflow](#running-our-integration-test-workflow-from-an-external-repo) to be reused by external repositories.

For customers wanting to run their own cluster configuration tests and checks, we have also created [github actions](#using-github-actions-to-independently-connect-a-cluster-to-arc-and-deploy-aio) to both connect your cluster to ARC, and deploy AIO resources to the cluster.

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
  During the tests, resources will be created that cannot be easily cleaned up and are typically hidden from default Azure Portal UI views.

  We also have a scheduled [cleanup workflow](../.github/workflows/cluster_cleanup.yml) that does a best-effort cleanup of all AIO-related resources in a particular resource group - this will attempt to clean up all resources that start with a particular "prefix" or are related to clusters with a similar prefix.

  Our tests use `az-iot-ops-test-cluster` for cluster resources and `opskv` for keyvaults. Without parameters, all resources with these prefixes (or that reference custom locations with these prefixes) will be deleted by the cleanup action.

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
**custom-locations-oid** | *Custom Locations Object ID - used to enable cluster-connect feature.*
**cleanup** | *An optional boolean switch that decides whether to attempt post-test cleanup rather than waiting for a scheduled cleanup job*

### Example workflow

```yaml
name: Run AIO CLI integration tests

on:
  workflow_dispatch:
    inputs:
      resource-group:
        type: string
        default: my-aio-resource-group

permissions: 
    id-token: write
    contents: read

jobs:
    run-integration-tests:
        uses: azure/azure-iot-ops-cli-extension/.github/workflows/int_test.yml@dev
        with:
            resource-group: ${{ inputs.resource-group }}
            custom-locations-oid: "custom-locations-object-id"
        secrets:
            AZURE_CLIENT_ID: ${{ secrets.AZURE_CLIENT_ID }}
            AZURE_SUBSCRIPTION_ID: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
            AZURE_TENANT_ID: ${{ secrets.AZURE_TENANT_ID }}
            AIO_SP_APP_ID: ${{ secrets.AZURE_CLIENT_ID }}
            AIO_SP_OBJECT_ID: ${{ secrets.AZURE_OBJECT_ID }}
            AIO_SP_SECRET: ${{ secrets.AZURE_CLIENT_SECRET }}

```

### Outputs

Currently this pipeline does not output values, it simply displays test pass/fail results.

### Considerations

#### CLI Extension Builds
Currently our pipeline uses the most recent dev branch of the IoT Operations extension to build our extension. The extension repo is cloned from the `dev` branch, the wheel is built from that source, and then added to the agent's CLI extension path.

#### Cleanup
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
  uses: azure/login@v2
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