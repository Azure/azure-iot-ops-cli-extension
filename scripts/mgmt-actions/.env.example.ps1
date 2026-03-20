# Personal overrides — copy this file to .env.ps1 and fill in your values.
# .env.ps1 is gitignored and sourced automatically by quickstart.ps1.

$instance       = "my-aio-instance"
$resourceGroup  = "my-resource-group"

# Paste a full ARM resource ID to use an existing EG namespace, or leave empty
# to auto-create one (named "${instance}-egns" in the instance's RG and location).
# $egResourceId = "/subscriptions/.../resourceGroups/.../providers/Microsoft.EventGrid/namespaces/..."

# User-assigned managed identity (leave commented out to use system MI):
# $userAssignedMI = "/subscriptions/.../resourceGroups/.../providers/Microsoft.ManagedIdentity/userAssignedIdentities/..."

# Non-default container registry for the dataflow graph asset:
# $registryHost = "myregistry.azurecr.io"

# Protocol config (defaults to OPC UA with simulator):
# $protocol        = "opcua"
# $endpointName    = "anonymous-endpoint"
# $endpointAddress = "opc.tcp://opcplc-000000.azure-iot-operations:50000"
# $deployOpcPlc    = $true
# $assetName       = "method-call-asset"
# $actionName      = "Switch"

# $skipRoleAssignments = $false
