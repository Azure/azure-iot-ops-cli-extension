# Welcome to the Azure IoT Operations CLI Extension codespace!

This codespace has everything you need to get started developing with python and the Azure CLI.

Included VSCode Extensions:

- [Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)
- [Black Formatter](https://marketplace.visualstudio.com/items?itemName=ms-python.black-formatter)
- [Python isort](https://marketplace.visualstudio.com/items?itemName=ms-python.isort)
- [VSCode Github Actions](https://marketplace.visualstudio.com/items?itemName=GitHub.vscode-github-actions)
- [YAML](https://marketplace.visualstudio.com/items?itemName=redhat.vscode-yaml)

Included Azure CLI extensions:

- [azure-devops](https://github.com/Azure/azure-devops-cli-extension)
- [connectedk8s](https://github.com/Azure/azure-cli-extensions/tree/main/src/connectedk8s)
- [connectedmachine](https://github.com/Azure/azure-cli-extensions/tree/main/src/connectedmachine)
- [k8s-extension](https://github.com/Azure/azure-cli-extensions/tree/main/src/k8s-extension)

Additional software:

- **Azure CLI** (and a locally installed copy of this extension)
- **k3d** for hosting a local k3s cluster
- **k9s** for browsing and editing cluster resources

## Validate codespace setup:

<details>
<summary>
Validate local dev extension configuration
</summary>

- Ensure your local python virtual environment is active:

  `az -v` should show you a local `Python location` path in your `env` folder:

  `/workspaces/azure-iot-ops-cli-extension/env/bin/python`

- Ensure your development extension is added to the CLI:

  `az extension list -o table` should show your installed extensions.
  
  Look for the extension `azure-iot-ops`, with `/workspaces/azure-iot-ops-cli-extension` as the `Path` and `dev` as the `ExtensionType`

- Ensure you can lint and unit test your local code:

  `tox` will run these checks, more info in our [tox guide](../docs/tox-testing.md)

</details>

<details>
<summary>
Validate local cluster environment and tools
</summary>

- Ensure you have a local cluster running:

  `k3d cluster list` will allow you to see if you have a k3s cluster running.

  Running `k9s` will launch an interactive console in the terminal that allows you to browse your cluster resources. Use `ctrl+c` to exit.

- Ensure you can run commands from the extension that connect to your local cluster:

  `az iot ops check` should run correctly and verify your local cluster meets AIO requirements.

</details>

<details open>
<summary>Validate CLI login and Azure connection</summary>

- Login to azure CLI (choose one):

  1. Login with `az login --use-device-code`
  2. Open codespace in desktop: `Ctrl/Cmd + Shift + P > Codespaces: Open in VS Code Desktop` and run `az login`

- Ensure you have a valid subscription selected:

  `az account show -o table`

- List all AIO instances in your subscription:

  `az iot ops list -o table`

</details>

## Connect your cluster to AIO

- Connect your new cluster to Azure Arc:

  `az connectedk8s connect -n $CLUSTER_NAME -g $RESOURCE_GROUP`

- Initialize your cluster with AIO prerequisites:

  `az iot ops init --cluster $CODESPACE_NAME -g $RESOURCE_GROUP`

- Create a schema registry using an existing storage account ID (or skip to the next step to use an existing registry):

  `az iot ops schema registry create -n {name} -g $RESOURCE_GROUP --registry-namespace
{namespace} --sa-resource-id $STORAGE_ACCOUNT_RESOURCE_ID`

- Query schema registry ID:

  `$SCHEMA_REGISTRY_ID=${az iot ops schema registry show -n {name} -g $RESOURCE_GROUP --query "id" -o tsv}`

- Create an AIO instance on your cluster

  `az iot ops create --cluster "$CODESPACE_NAME" -g $RESOURCE_GROUP --name {name} --sr-resource-id $SCHEMA_REGISTRY_ID`

## Verify AIO deployment and cluster status

- Run service summary checks on your cluster: `az iot ops check`