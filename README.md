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

### Azure US Government deployment configuration

With `AzureUSGovernment` selected in Azure CLI, `iot ops init` uses Government-specific Cert Manager and
Secret Store version/train defaults from the full Government enablement blueprint. `iot ops create` selects
the full Government instance blueprint, including its parameters, resources, Schema Registry ARM endpoint/audience,
and top-level chart cloud settings. No additional cloud flag is required.
These settings configure deployed components separately from the CLI's own cloud-aware management clients.
Public GA/preview deployment defaults are unchanged.

Government instance deployment is restricted to `usgovvirginia`; accepted display-form location values are
normalized to the source-declared region before use. `--use-preview` and Public preview-runtime-only
operations are not supported there. The FF release's artifact train is independent of this eligibility:
the current source deploys `1.5.42` on the `stable` train without enabling Public preview
features. Required Government chart settings reject conflicting `--ops-config` values. Upgrade
planning repairs those settings independently of optional configuration-sync modes without removing unrelated
extension settings. Explicit dependency version/train override options retain their existing behavior.

Government blueprints use the same generated `TemplateBlueprint` format as GA and preview, from a separately
pinned FF Bicep export through the template-sync skill. Create, runtime discovery, update, and upgrade planning
use a cloud-specific runtime catalog; Public release inputs are not substituted into Government deployments.
Only the exact bundled FF artifact identity is currently mapped; normal upgrade planning requires reviewed mappings
for additional installed FF baselines. The existing internal stable-upgrade compatibility bypass is unchanged;
it does not qualify an FF migration or allow unreviewed target version/train overrides.
GDS Manager is excluded from both Government blueprints.
Follow the [FF refresh procedure](.github/skills/sync-aio-bicep-templates/references/runtime-profiles.md#fairfax-policy-refresh)
to update them without replacing Public templates.

The current Government inputs are provisional pending the final AIO release handoff and live qualification;
this configuration support is not a claim that an FF release has been published or qualified.

## Contributing

Please refer to the [Contributing](CONTRIBUTING.md) page for developer setup instructions and contribution guidelines.

## Feedback

We are constantly improving and are always open to new functionality or enhancement ideas. Submit your feedback in the project [issues](https://github.com/Azure/azure-iot-ops-cli-extension/issues).

## Code of Conduct

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).
For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or
contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.
