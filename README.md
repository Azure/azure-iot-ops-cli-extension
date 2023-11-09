# Microsoft Azure IoT Operations extension for Azure CLI

![Python](https://img.shields.io/pypi/pyversions/azure-cli.svg?maxAge=2592000)
![Build](https://github.com/azure/azure-iot-ops-cli-extension/actions/workflows/release_workflow.yml/badge.svg)

The **Azure IoT Operations extension for Azure CLI** aims to accelerate the development, management and automation of Azure IoT Operations solutions. It does this via addition of rich features and functionality to the official [Azure CLI](https://docs.microsoft.com/en-us/cli/azure).
on.

## Pre-requisites

- Applicable services are deployed to CNCF K8s cluster
- This azure-iot-ops extension requires az cli `2.42.0` or higher. If you don't have az cli installed, follow [these instructions](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli).

## Install az iot ops extension

🌟 Windows, macOS and common Linux environments are supported.

❗ Please uninstall the private preview `az edge` extension with `az extension remove --name azure-edge` if you have it installed.

The current IoT Ops CLI is available via https://aka.ms/aziotopscli-latest.

You can download the `.whl` and install against your local copy, or use one of these fast install examples:

bash
```bash
az extension add --source $(curl -w "%{url_effective}\n" -I -L -s -S https://aka.ms/aziotopscli-latest -o /dev/null) -y
```

pwsh
```pwsh
az extension add --source ([System.Net.HttpWebRequest]::Create('https://aka.ms/aziotopscli-latest').GetResponse().ResponseUri.AbsoluteUri) -y
```

After install, the root command group `az iot ops` should be available and ready for use.

- List installed extensions with `az extension list`
- Remove an installed extension with `az extension remove --name <extension-name>`

## Connecting to a K8s cluster

👉 To maintain minimum friction between K8s tools, the `az iot ops` edge side commands are designed to make use of your existing kube config (typically located at `~/.kube/config`).

All k8s interaction commands include an optional `--context` param. If none is provided `current_context` as defined in the kube config will be used.

## Available Functionality

🚀 Always start with the `--help` flag to understand details about command groups, their containing commands & subgroups.

Comprehensive documentation is available in the [Wiki](https://github.com/Azure/azure-iot-ops-cli-extension/wiki/Azure-IoT-Ops-Reference).

## Contributing

Please refer to the [Contributing](CONTRIBUTING.md) page for developer setup instructions and contribution guidelines.

## Feedback

We are constantly improving and are always open to new functionality or enhancement ideas. Submit your feedback in the project [issues](https://github.com/Azure/azure-iot-ops-cli-extension/issues).

## Code of Conduct

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).
For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or
contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.
