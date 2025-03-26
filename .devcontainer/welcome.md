👋 Welcome to the Azure IoT Operations CLI Extension repo!

   It has everything you need to get started developing with python and the Azure CLI.

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

🖥️ To login to Azure CLI, you can:

    1. Login with `az login --use-device-code`
    2. Open this codespace in VS Code desktop: Ctrl/Cmd + Shift + P > Codespaces: Open in VS Code Desktop


Get started with CLI development:
- List all AIO instances
    - `az iot ops list -o table`
- Run cluster pre-checks:
    - `az iot ops check --pre`
- Create a schema registry:
    - `az iot ops schema registry create -n [name] -g $RESOURCE_GROUP --registry-namespace schemas --sa-resource-id $STORAGE_ACCOUNT_RESOURCE_ID`

Get started with AIO:
- Initialize your cluster with AIO prerequisites
    - `az iot ops init --cluster $CODESPACE_NAME

📎 Connect your new cluster to Azure Arc:
   
   az login
   az account set -s $SUBSCRIPTION_ID
   az connectedk8s connect -n $CLUSTER_NAME -g $RESOURCE_GROUP -l $LOCATION


Next steps:

- Initialize your cluster
- Create an AIO instance