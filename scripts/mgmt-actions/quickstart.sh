#!/usr/bin/env bash
# =============================================================================
# Management Actions — Quickstart
#
# Provisions a complete management actions scenario: device, endpoint,
# asset (with management group + action), and enables management actions.
#
# Steps:
#   1. Discovers instance and ADR namespace metadata (namespace ID, location, extended location)
#   2. (Optional) Creates an Event Grid namespace
#   3. (Optional) Deploys the OPC PLC simulator on the cluster
#   4. Creates device (with endpoint) and asset (with mgmt group + action)
#   5. Enables management actions on the IoT Operations instance
#
# Prerequisites:
#   - An AIO instance must already exist
#   - kubectl configured to the target cluster (if deploying the OPC PLC simulator)
#   - az login completed
#
# Usage:
#   Review the CONFIGURATION section below, adjust values, then run:
#     bash quickstart.sh
# =============================================================================

set -euo pipefail
SECONDS=0

# =============================================================================
# CONFIGURATION — Edit this section, or override values via .env.sh
#
# To use a personal env file (gitignored):
#   1. Copy .env.example.sh to .env.sh
#   2. Fill in your values
#   3. Run the script — .env.sh is sourced automatically
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/.env.sh" ]; then
    echo ">> Loading overrides from .env.sh"
    # shellcheck source=/dev/null
    source "$SCRIPT_DIR/.env.sh"
fi

# --- IoT Operations instance (required) ---
instance="${instance:-my-aio-instance}"
resource_group="${resource_group:-my-resource-group}"

# --- Event Grid namespace ---
# If you already have an EG namespace, set eg_resource_id in .env.sh.
# If left empty, the script auto-creates one in the instance's resource group
# and location, named "${instance}-egns".
eg_resource_id="${eg_resource_id:-}"

# --- Insecure broker listener (debugging) ---
# Set to "true" to add a no-auth listener on port 1883 for debugging.
# Useful for observing MQTT traffic with tools like mosquitto_sub.
add_insecure_listener="${add_insecure_listener:-false}"
insecure_listener_name="${insecure_listener_name:-debuglistener}"

# --- Identity for EG dataflow endpoint ---
# Leave empty to use the system-assigned managed identity (default).
# Set to a full UAMI resource ID to use a user-assigned managed identity instead.
# Example: "/subscriptions/.../resourceGroups/.../providers/Microsoft.ManagedIdentity/userAssignedIdentities/my-uami"
user_assigned_mi="${user_assigned_mi:-}"

# --- Role assignments ---
# Set to "true" to skip role assignment creation during enable.
# Useful if role assignments were pre-configured or you lack permissions.
skip_role_assignments="${skip_role_assignments:-false}"

# --- Device name ---
device_name="${device_name:-test-device}"

# --- Protocol: OPC UA (default) ---
# To use a different protocol, comment out this block and uncomment another below.
protocol="${protocol:-opcua}"
endpoint_name="${endpoint_name:-anonymous-endpoint}"
endpoint_address="${endpoint_address:-opc.tcp://opcplc-000000.azure-iot-operations:50000}"
deploy_opc_plc="${deploy_opc_plc:-true}"   # OPC PLC simulator pod
asset_name="${asset_name:-method-call-asset}"
mgmt_group_name="${mgmt_group_name:-managementGroup}"
action_name="${action_name:-Switch}"             # Used in next-steps hints

# --- Protocol: ONVIF (uncomment to switch) ---
# protocol="${protocol:-onvif}"
# endpoint_name="${endpoint_name:-onvif-endpoint}"
# endpoint_address="${endpoint_address:-http://onvif-simulator:8080}"
# asset_name="${asset_name:-onvif-mgmt-asset}"
# mgmt_group_name="${mgmt_group_name:-managementGroup}"
# action_name="${action_name:-TBD}"

# --- Registry config ---
# If a non-default container registry is needed for the dataflow graph asset,
# set the hostname here. Leave empty to skip registry endpoint creation.
registry_host="${registry_host:-}"
registry_endpoint_name="${registry_endpoint_name:-stagingregistry}"

# --- ADR API version ---
adr_api_version="${adr_api_version:-2026-04-01}"

# =============================================================================
# EXECUTION — No changes needed below this line
# =============================================================================

# ---------- Discover instance metadata ----------
# Extract ADR namespace ID and extended location from the instance.
# Location is resolved from the ADR namespace (devices and assets must be co-located).
# Runs early so location is available for EG auto-creation and asset body.
echo ""
echo ">> Discovering instance metadata..."
instance_meta=$(az iot ops show -n "$instance" -g "$resource_group" \
    --query "[properties.adrNamespaceRef.resourceId, extendedLocation.name]" -o tsv)
{ read -r ns_id; read -r ext_loc_name; } <<< "$instance_meta"

# ADR namespace location — devices and assets must be co-located
location=$(az resource show --ids "$ns_id" --query location -o tsv)

echo "   Namespace:  $ns_id"
echo "   Location:   $location"
echo "   ExtLoc:     $ext_loc_name"

# ---------- Event Grid namespace ----------
if [ -z "$eg_resource_id" ]; then
    eg_name="${instance}-egns"
    az extension add --upgrade -n eventgrid -y
    echo ""
    echo ">> Creating Event Grid namespace '$eg_name'..."
    az eventgrid namespace create \
        -n "$eg_name" \
        -g "$resource_group" \
        -l "$location" \
        --topic-spaces-configuration '{"state":"Enabled","maximumClientSessionsPerAuthenticationName":8}' \
        --sku '{"name":"Standard","capacity":1}'

    eg_resource_id=$(az eventgrid namespace show \
        -n "$eg_name" \
        -g "$resource_group" \
        --query id -o tsv)

    echo "   EG namespace: $eg_resource_id"
fi

# ---------- Insecure broker listener (debugging) ----------
if [ "$add_insecure_listener" = "true" ]; then
    echo ""
    echo ">> Adding insecure broker listener '$insecure_listener_name' on port 1883..."
    az iot ops broker listener port add \
        --port 1883 \
        --listener "$insecure_listener_name" \
        -i "$instance" \
        -g "$resource_group"
fi

# ---------- Registry endpoint (non-default registry) ----------
if [ -n "$registry_host" ]; then
    echo ""
    echo ">> Creating registry endpoint '$registry_endpoint_name'..."
    az iot ops registry create \
        -n "$registry_endpoint_name" \
        -i "$instance" \
        -g "$resource_group" \
        --host "$registry_host" \
        --no-auth
fi

# ---------- Device ----------
echo ""
echo ">> Creating device '$device_name'..."
az iot ops ns device create \
    -n "$device_name" \
    -i "$instance" \
    -g "$resource_group"

# ---------- Simulator + inbound endpoint (protocol-specific) ----------
if [ "$protocol" = "opcua" ]; then
    if [ "$deploy_opc_plc" = "true" ]; then
        echo ""
        echo ">> Deploying OPC PLC simulator..."
        kubectl apply -f https://raw.githubusercontent.com/Azure-Samples/explore-iot-operations/main/samples/quickstarts/opc-plc-deployment.yaml
    fi

    echo ""
    echo ">> Adding OPC UA inbound endpoint '$endpoint_name' to device..."
    az iot ops ns device endpoint inbound add opcua \
        --name "$endpoint_name" \
        --device "$device_name" \
        -i "$instance" \
        -g "$resource_group" \
        --address "$endpoint_address" \
        --ac true \
        --ad false

elif [ "$protocol" = "onvif" ]; then
    echo ""
    echo ">> Adding ONVIF inbound endpoint '$endpoint_name' to device..."
    az iot ops ns device endpoint inbound add onvif \
        --name "$endpoint_name" \
        --device "$device_name" \
        -i "$instance" \
        -g "$resource_group" \
        --address "$endpoint_address" \
        --ac true \
        --ad false

else
    echo "ERROR: Unsupported protocol '$protocol'. Supported: opcua, onvif" >&2
    exit 1
fi

# ---------- Asset + management group + action ----------
echo ""
echo ">> Creating asset '$asset_name' with management group and action..."

read -r -d '' asset_body << EOF || true
{
    "location": "${location}",
    "extendedLocation": {
        "name": "${ext_loc_name}",
        "type": "CustomLocation"
    },
    "properties": {
        "enabled": true,
        "displayName": "${asset_name}",
        "deviceRef": {
            "deviceName": "${device_name}",
            "endpointName": "${endpoint_name}"
        },
        "defaultDatasetsConfiguration": "{}",
        "defaultEventsConfiguration": "{}",
        "managementGroups": [
            {
                "name": "${mgmt_group_name}",
                "dataSource": "${device_name}",
                "actions": [
                    {
                        "name": "${action_name}",
                        "targetUri": "nsu=http://microsoft.com/Opc/OpcPlc/Boiler;i=7019",
                        "topic": "azure-iot-operations/asset-operations/${asset_name}/${mgmt_group_name}/${action_name}/test",
                        "actionType": "Call"
                    }
                ]
            }
        ]
    }
}
EOF

az resource create \
    --id "${ns_id}/assets/${asset_name}" \
    --api-version "$adr_api_version" \
    --is-full-object \
    --properties "$asset_body"

# ---------- Identity federation (UAMI only) ----------
if [ -n "$user_assigned_mi" ]; then
    echo ""
    echo ">> Assigning user-assigned managed identity to instance..."
    az iot ops identity assign \
        -n "$instance" \
        -g "$resource_group" \
        --mi-user-assigned "$user_assigned_mi"
fi

# ---------- Enable management actions ----------
echo ""
echo ">> Enabling management actions on instance '$instance'..."

enable_args=(
    "-i" "$instance"
    "-g" "$resource_group"
    "--eg-resource-id" "$eg_resource_id"
)

if [ -n "$registry_host" ]; then
    enable_args+=("--registry-endpoint" "$registry_endpoint_name")
fi

if [ -n "$user_assigned_mi" ]; then
    enable_args+=("--mi-user-assigned" "$user_assigned_mi")
fi

if [ "$skip_role_assignments" = "true" ]; then
    enable_args+=("--skip-ra")
fi

az iot ops mgmt-actions enable "${enable_args[@]}"

# ---------- Next steps ----------
echo ""
echo ">> Management actions enabled! Try these commands:"
echo ""
echo "   # Execute a management action"
echo "   az iot ops mgmt-actions execute -i $instance -g $resource_group --asset $asset_name --group $mgmt_group_name --action $action_name -p '{\"On\": true}'"
echo ""
echo "   # Show management actions configuration"
echo "   az iot ops mgmt-actions show -i $instance -g $resource_group"
echo ""
echo "   # Disable management actions (teardown)"
echo "   az iot ops mgmt-actions disable -i $instance -g $resource_group"
echo ""
echo "   Note: Role assignments may take up to a few minutes to propagate."

# ---------- Done ----------
elapsed=$SECONDS
printf "\nTotal elapsed: %02d:%02d:%02d\n" $((elapsed/3600)) $((elapsed%3600/60)) $((elapsed%60))
