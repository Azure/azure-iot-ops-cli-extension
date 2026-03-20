#!/usr/bin/env pwsh
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
#     ./quickstart.ps1          # or: pwsh quickstart.ps1
#
#   For bash, use quickstart.sh instead.
# =============================================================================

set-strictmode -version latest
$ErrorActionPreference = "Stop"
# Make native command failures (non-zero exit code) respect $ErrorActionPreference,
# equivalent to bash's 'set -e'. Requires PS 7.3+; harmless no-op on older versions.
$PSNativeCommandUseErrorActionPreference = $true
$sw = [System.Diagnostics.Stopwatch]::StartNew()

# =============================================================================
# CONFIGURATION — Edit this section, or override values via .env.ps1
#
# Defaults are defined below. To use a personal env file (gitignored):
#   1. Copy .env.example.ps1 to .env.ps1
#   2. Set only the values you want to override
#   3. Run the script — .env.ps1 is sourced after defaults, overriding them
# =============================================================================

# --- IoT Operations instance (required) ---
$instance      = "my-aio-instance"
$resourceGroup = "my-resource-group"

# --- Event Grid namespace ---
# If you already have an EG namespace, set $egResourceId to its full resource ID.
# If left empty, the script auto-creates one in the instance's resource group
# and location, named "${instance}-egns".
$egResourceId = ""

# --- Insecure broker listener (debugging) ---
# Set to $true to add a no-auth listener on port 1883 for debugging.
# Useful for observing MQTT traffic with tools like mosquitto_sub.
$addInsecureListener  = $false
$insecureListenerName = "debuglistener"

# --- Identity for EG dataflow endpoint ---
# Leave empty to use the system-assigned managed identity (default).
# Set to a full UAMI resource ID to use a user-assigned managed identity instead.
# Example: "/subscriptions/.../resourceGroups/.../providers/Microsoft.ManagedIdentity/userAssignedIdentities/my-uami"
$userAssignedMI = ""

# --- Role assignments ---
# Set to $true to skip role assignment creation during enable.
# Useful if role assignments were pre-configured or you lack permissions.
$skipRoleAssignments = $false

# --- Device name ---
$deviceName = "test-device"

# --- Protocol: OPC UA (default) ---
# To use a different protocol, comment out this block and uncomment another below.
$protocol        = "opcua"
$endpointName    = "anonymous-endpoint"
$endpointAddress = "opc.tcp://opcplc-000000.azure-iot-operations:50000"
$deployOpcPlc    = $true    # OPC PLC simulator pod
$assetName       = "method-call-asset"
$mgmtGroupName   = "managementGroup"
$actionName      = "Switch"  # Used in next-steps hints

# --- Protocol: ONVIF (uncomment to switch) ---
# $protocol        = "onvif"
# $endpointName    = "onvif-endpoint"
# $endpointAddress = "http://onvif-simulator:8080"
# $assetName       = "onvif-mgmt-asset"
# $mgmtGroupName   = "managementGroup"
# $actionName      = "TBD"

# --- Registry config ---
# If a non-default container registry is needed for the dataflow graph asset,
# set the hostname here. Leave empty to skip registry endpoint creation.
$registryHost         = ""
$registryEndpointName = "stagingregistry"

# --- ADR API version ---
$adrApiVersion = "2026-04-01"

# --- Override defaults from personal env file ---
$envFile = Join-Path $PSScriptRoot ".env.ps1"
if (Test-Path $envFile) {
    Write-Host ">> Loading overrides from .env.ps1"
    . $envFile
}

# =============================================================================
# HELPERS
# =============================================================================

# Write JSON to a temp file and return the path. Call sites use az's @filepath
# syntax to pass JSON from disk, bypassing PowerShell 5.1's argument mangling
# which strips embedded double quotes from native command arguments.
function Write-TempJson {
    param([Parameter(Mandatory)][string]$Content)
    $path = [System.IO.Path]::GetTempFileName()
    # WriteAllText without an Encoding parameter writes UTF-8 with no BOM,
    # which prevents az (Python) from choking on a BOM prefix.
    [System.IO.File]::WriteAllText($path, $Content)
    return $path
}

# =============================================================================
# EXECUTION — No changes needed below this line
# =============================================================================

# ---------- Discover instance metadata ----------
# Extract ADR namespace ID and extended location from the instance.
# Location is resolved from the ADR namespace (devices and assets must be co-located).
# Runs early so location is available for EG auto-creation and asset body.
Write-Host "`n>> Discovering instance metadata..."
$meta = (az iot ops show -n $instance -g $resourceGroup `
    --query "[properties.adrNamespaceRef.resourceId, extendedLocation.name]" -o tsv)
$nsId       = $meta[0]
$extLocName = $meta[1]

# ADR namespace location — devices and assets must be co-located
$location = (az resource show --ids $nsId --query location -o tsv)

Write-Host "   Namespace:  $nsId"
Write-Host "   Location:   $location"
Write-Host "   ExtLoc:     $extLocName"

# ---------- Event Grid namespace ----------
if (-not $egResourceId) {
    $egName = "${instance}-egns"
    az extension add --upgrade -n eventgrid -y
    Write-Host "`n>> Creating Event Grid namespace '$egName'..."
    $topicSpacesFile = Write-TempJson '{"state":"Enabled","maximumClientSessionsPerAuthenticationName":8}'
    $skuFile = Write-TempJson '{"name":"Standard","capacity":1}'

    az eventgrid namespace create `
        -n $egName `
        -g $resourceGroup `
        -l $location `
        --topic-spaces-configuration "@$topicSpacesFile" `
        --sku "@$skuFile"

    Remove-Item $topicSpacesFile, $skuFile -ErrorAction SilentlyContinue

    $egResourceId = (az eventgrid namespace show `
        -n $egName `
        -g $resourceGroup `
        --query id -o tsv)

    Write-Host "   EG namespace: $egResourceId"
}

# ---------- Insecure broker listener (debugging) ----------
if ($addInsecureListener) {
    Write-Host "`n>> Adding insecure broker listener '$insecureListenerName' on port 1883..."
    az iot ops broker listener port add `
        --port 1883 `
        --listener $insecureListenerName `
        -i $instance `
        -g $resourceGroup
}

# ---------- Registry endpoint (non-default registry) ----------
if ($registryHost) {
    Write-Host "`n>> Creating registry endpoint '$registryEndpointName'..."
    az iot ops registry create `
        -n $registryEndpointName `
        -i $instance `
        -g $resourceGroup `
        --host $registryHost `
        --no-auth
}

# ---------- Device ----------
Write-Host "`n>> Creating device '$deviceName'..."
az iot ops ns device create `
    -n $deviceName `
    -i $instance `
    -g $resourceGroup

# ---------- Simulator + inbound endpoint (protocol-specific) ----------
switch ($protocol) {
    "opcua" {
        if ($deployOpcPlc) {
            Write-Host "`n>> Deploying OPC PLC simulator..."
            kubectl apply -f https://raw.githubusercontent.com/Azure-Samples/explore-iot-operations/main/samples/quickstarts/opc-plc-deployment.yaml
        }

        Write-Host "`n>> Adding OPC UA inbound endpoint '$endpointName' to device..."
        az iot ops ns device endpoint inbound add opcua `
            --name $endpointName `
            --device $deviceName `
            -i $instance `
            -g $resourceGroup `
            --address $endpointAddress `
            --ac true `
            --ad false
    }
    "onvif" {
        Write-Host "`n>> Adding ONVIF inbound endpoint '$endpointName' to device..."
        az iot ops ns device endpoint inbound add onvif `
            --name $endpointName `
            --device $deviceName `
            -i $instance `
            -g $resourceGroup `
            --address $endpointAddress `
            --ac true `
            --ad false
    }
    default {
        Write-Error "Unsupported protocol '$protocol'. Supported: opcua, onvif"
    }
}

# ---------- Asset + management group + action ----------
Write-Host "`n>> Creating asset '$assetName' with management group and action..."

$assetBody = @"
{
    "location": "$location",
    "extendedLocation": {
        "name": "$extLocName",
        "type": "CustomLocation"
    },
    "properties": {
        "enabled": true,
        "displayName": "$assetName",
        "deviceRef": {
            "deviceName": "$deviceName",
            "endpointName": "$endpointName"
        },
        "defaultDatasetsConfiguration": "{}",
        "defaultEventsConfiguration": "{}",
        "managementGroups": [
            {
                "name": "$mgmtGroupName",
                "dataSource": "$deviceName",
                "actions": [
                    {
                        "name": "$actionName",
                        "targetUri": "nsu=http://microsoft.com/Opc/OpcPlc/Boiler;i=7019",
                        "topic": "azure-iot-operations/asset-operations/$assetName/$mgmtGroupName/$actionName/test",
                        "actionType": "Call"
                    }
                ]
            }
        ]
    }
}
"@

$assetBodyFile = Write-TempJson $assetBody

az resource create `
    --id "$nsId/assets/$assetName" `
    --api-version $adrApiVersion `
    --is-full-object `
    --properties "@$assetBodyFile"

Remove-Item $assetBodyFile -ErrorAction SilentlyContinue

# ---------- Identity federation (UAMI only) ----------
if ($userAssignedMI) {
    Write-Host "`n>> Assigning user-assigned managed identity to instance..."
    az iot ops identity assign `
        -n $instance `
        -g $resourceGroup `
        --mi-user-assigned $userAssignedMI
}

# ---------- Enable management actions ----------
Write-Host "`n>> Enabling management actions on instance '$instance'..."

$enableArgs = @(
    "-i", $instance,
    "-g", $resourceGroup,
    "--eg-resource-id", $egResourceId
)

if ($registryHost) {
    $enableArgs += "--registry-endpoint", $registryEndpointName
}

if ($userAssignedMI) {
    $enableArgs += "--mi-user-assigned", $userAssignedMI
}

if ($skipRoleAssignments) {
    $enableArgs += "--skip-ra"
}

az iot ops mgmt-actions enable @enableArgs

# ---------- Next steps ----------
Write-Host "`n>> Management actions enabled! Try these commands (PowerShell):"
Write-Host ""
Write-Host "   # Execute a management action"
Write-Host "   az iot ops mgmt-actions execute -i $instance -g $resourceGroup --asset $assetName --group $mgmtGroupName --action $actionName -p '{`\`"On`\`": true}'"
Write-Host ""
Write-Host "   # Show management actions configuration"
Write-Host "   az iot ops mgmt-actions show -i $instance -g $resourceGroup"
Write-Host ""
Write-Host "   # Disable management actions (teardown)"
Write-Host "   az iot ops mgmt-actions disable -i $instance -g $resourceGroup"
Write-Host ""
Write-Host "   Note: Role assignments may take up to a few minutes to propagate."

# ---------- Done ----------
$sw.Stop()
Write-Host "`nTotal elapsed: $($sw.Elapsed.ToString('hh\:mm\:ss'))"
