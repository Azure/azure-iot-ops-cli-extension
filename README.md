# Microsoft Azure IoT Operations extension for Azure CLI

![Python](https://img.shields.io/pypi/pyversions/azure-cli.svg?maxAge=2592000)
![Build](https://github.com/azure/azure-iot-ops-cli-extension/actions/workflows/release_workflow.yml/badge.svg)

The **Azure IoT Operations extension for Azure CLI** aims to accelerate the development, management and automation of Azure IoT Operations solutions. It does this via addition of rich features and functionality to the official [Azure CLI](https://learn.microsoft.com/en-us/cli/azure).

## Pre-requisites

- An Azure Arc-enabled CNCF K8s cluster.
- Azure CLI `2.67.0` or greater. If you don't have az cli installed, follow [these instructions](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli).

## Install az iot ops extension

🌟 Windows, macOS and common Linux environments are supported.

❗ Please uninstall the private preview `az edge` extension with `az extension remove --name azure-edge` if you have it installed.

The IoT Ops CLI is part of the Azure CLI extension index. Installation is as simple as:

```
az extension add --upgrade --name azure-iot-ops
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

### Management actions on existing instances

Management-actions enablement selects the newest CLI-supported stable API enabled for its
required resource types on the instance's custom location.
Selection uses enabled resource types, not an AIO-version-to-API table.
Missing or invalid custom-location IDs are rejected before any external writes.

Capability discovery is optional and does not introduce a required permission. When
available, it checks compatibility before Event Grid, Device Registry, or child-resource
writes. If discovery is denied, unavailable, or empty, enablement preserves existing
access and negotiates older CLI-supported stable APIs only after an explicit HTTP 400/404
`MissingAzureKubernetesMapping` rejection of a JSON child PUT. It does not downgrade on
authorization, unrelated service, or transport errors, or replay accepted operations.

Show and disable retain their existing resource-provider read/delete paths. They do
not perform custom-location capability discovery or require this additional permission.

When discovery is unavailable, compatibility cannot be guaranteed before writes.
This preflight does not make multi-resource workflows transactional: later service
failures can still leave partial state. Other child-resource commands and explicit
runtime API selection for deployment and upgrade workflows are unchanged.

### Fairfax deployment configuration

With `AzureUSGovernment` selected as the Azure CLI cloud, `iot ops init` uses the shared Cert Manager and
Secret Store defaults. `iot ops create` uses the same generated instance template as Public GA while selecting
the Fairfax AIO version, train, Schema Registry endpoints, and chart cloud settings. No additional cloud flag
is required, and Public GA/preview deployment defaults are unchanged.

Fairfax instance deployment is restricted to `usgovvirginia`. `--use-preview` and Public preview-runtime-only
operations are not supported. The current profile deploys `1.5.77` on the `stable` train, with `1.5.46` on
`stable` retained as a reviewed upgrade source. Required Fairfax chart settings reject conflicting `--ops-config`
values, and upgrade planning repairs those settings without removing unrelated extension settings.

Create, runtime discovery, update, and upgrade planning use the Fairfax runtime catalog and dedicated values
from the shared instance template. GDS Manager remains excluded. Follow the
[Fairfax refresh procedure](.github/skills/sync-aio-bicep-templates/references/runtime-profiles.md#fairfax-policy-refresh)
when updating these inputs.

These inputs remain subject to the final AIO release handoff and live qualification; their presence does not
claim that a Fairfax release has been published or qualified.

## Contributing

Please refer to the [Contributing](CONTRIBUTING.md) page for developer setup instructions and contribution guidelines.

## Feedback

We are constantly improving and are always open to new functionality or enhancement ideas. Submit your feedback in the project [issues](https://github.com/Azure/azure-iot-ops-cli-extension/issues).

## Code of Conduct

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).
For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or
contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.
