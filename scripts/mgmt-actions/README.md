# Management Actions — Quickstart

A fast way to exercise the management actions scenario in Azure IoT Operations.

These scripts provision a complete end-to-end setup (device, endpoint, asset with
management group and action, Event Grid namespace, and management actions enablement)
so you can start invoking management actions in minutes.

## Prerequisites

- An **Azure IoT Operations instance** already deployed on an Arc-connected cluster
- **kubectl** configured to the target cluster (only if deploying the OPC PLC simulator)
- **az login** completed with access to the instance's subscription
- The `azure-iot-ops` CLI extension installed (`az extension add --upgrade -n azure-iot-ops`)

### UAMI Prerequisites

Using a user-assigned managed identity (`user_assigned_mi` / `$userAssignedMI`)
requires **workload identity federation** and the **OIDC issuer** to be enabled on
the Arc-connected cluster. Both can be enabled when connecting the cluster:

```bash
az connectedk8s connect \
    --name $cluster_name \
    --resource-group $rg_name \
    --location $location \
    --enable-oidc-issuer \
    --enable-workload-identity
```

A federated credential must also be configured on the UAMI trusting the cluster's
service account. If these prerequisites are not met, UAMI-based authentication for
the Event Grid dataflow endpoint will fail at runtime.

## Quick Start

### Bash

```bash
# 1. Create your personal config (gitignored)
cp .env.example.sh .env.sh

# 2. Edit .env.sh — at minimum set instance and resource_group
#    vi .env.sh

# 3. Run the quickstart
bash quickstart.sh
```

### PowerShell

```powershell
# 1. Create your personal config (gitignored)
Copy-Item .env.example.ps1 .env.ps1

# 2. Edit .env.ps1 — at minimum set $instance and $resourceGroup
#    notepad .env.ps1

# 3. Run the quickstart
./quickstart.ps1
```

## What the Script Does

1. Discovers **instance and ADR namespace metadata** (namespace ID, location, extended location)
2. **(Optional)** Creates an Event Grid namespace with topic spaces enabled
3. **(Optional)** Deploys the OPC PLC simulator pod on the cluster (OPC UA only)
4. Creates a **device** with an inbound endpoint (protocol-specific)
5. Creates an **asset** with a management group and action
6. **Enables management actions** on the IoT Operations instance, which provisions:
   - **Event Grid namespace**: topic space and permission bindings (pub/sub)
   - **Device Registry namespace**: managed identity and management endpoint entry
   - **IoT Operations instance**: EG dataflow endpoint, dataflow graph, and response dataflow
   - **Role assignments** (unless `--skip-ra`): ADR namespace roles and dataflow identity roles

On completion, the script prints next-step commands you can copy-paste:

```
az iot ops mgmt-actions show ...      # Verify everything is wired up
az iot ops mgmt-actions execute ...   # Invoke an action
az iot ops mgmt-actions disable ...   # Teardown
```

> **Tip:** Run `mgmt-actions show` first to confirm all sub-resources exist
> before attempting `execute`. The dataflow graph and response dataflow may
> take a few seconds to reconcile after `enable` completes.

### Re-running the Script

The script is idempotent — re-running it produces the same result.

## Switching Protocols

The default configuration uses **OPC UA** with the OPC PLC simulator. To switch to
a different protocol (e.g., ONVIF):

1. In the config section, **comment out** the `Protocol: OPC UA` block
2. **Uncomment** the `Protocol: ONVIF` block (or create a new one)
3. Edit the **management groups JSON** in the `Asset + management group + action`
   section of the script to match your protocol's action shape

The device and asset creation are protocol-agnostic;
only the inbound endpoint command and management groups payload differ by protocol.

## Configuration Reference

### Required

| Variable (bash) | Variable (PS) | Description |
|---|---|---|
| `instance` | `$instance` | IoT Operations instance name |
| `resource_group` | `$resourceGroup` | Resource group containing the instance |

### Event Grid

| Variable (bash) | Variable (PS) | Default | Description |
|---|---|---|---|
| `eg_resource_id` | `$egResourceId` | *(empty)* | Full ARM resource ID of an existing EG namespace. If empty, auto-creates `${instance}-egns` in the instance's resource group and location. |

### Protocol Config

| Variable (bash) | Variable (PS) | Default | Description |
|---|---|---|---|
| `protocol` | `$protocol` | `opcua` | Endpoint protocol type (`opcua`, `onvif`) |
| `endpoint_name` | `$endpointName` | `anonymous-endpoint` | Inbound endpoint name on the device |
| `endpoint_address` | `$endpointAddress` | `opc.tcp://opcplc-000000.azure-iot-operations:50000` | Protocol-specific endpoint address |
| `deploy_opc_plc` | `$deployOpcPlc` | `true` | Deploy the OPC PLC simulator pod (OPC UA only) |
| `asset_name` | `$assetName` | `method-call-asset` | Asset resource name |
| `mgmt_group_name` | `$mgmtGroupName` | `managementGroup` | Management group name |
| `action_name` | `$actionName` | `Switch` | Action name (used in next-steps hints) |

### Identity & Security

| Variable (bash) | Variable (PS) | Default | Description |
|---|---|---|---|
| `user_assigned_mi` | `$userAssignedMI` | *(empty)* | Full UAMI resource ID. If empty, uses system MI. See [UAMI prerequisites](#uami-prerequisites). |
| `skip_role_assignments` | `$skipRoleAssignments` | `false` | Skip role assignment creation during enable |

### Other

| Variable (bash) | Variable (PS) | Default | Description |
|---|---|---|---|
| `device_name` | `$deviceName` | `test-device` | Device resource name |
| `add_insecure_listener` | `$addInsecureListener` | `false` | Add a no-auth MQTT listener on port 1883 (see [Debugging with MQTT](#debugging-with-mqtt)) |
| `registry_host` | `$registryHost` | *(empty)* | Non-default container registry hostname |
| `adr_api_version` | `$adrApiVersion` | `2026-04-01` | ADR API version for asset creation |

## Debugging with MQTT

If you set `add_insecure_listener` / `$addInsecureListener` to `true`, the script
creates a no-auth broker listener on port 1883. To access it from your local
machine, port-forward the broker pod:

```bash
kubectl port-forward aio-broker-frontend-0 1883:1883 -n azure-iot-operations
```

You can then subscribe to all broker traffic with a local MQTT client:

```bash
mosquitto_sub -h localhost -p 1883 -t '#' -v
```
