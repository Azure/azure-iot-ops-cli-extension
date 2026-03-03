# Personal overrides — copy this file to .env.sh and fill in your values.
# .env.sh is gitignored and sourced automatically by quickstart.sh.

instance="my-aio-instance"
resource_group="my-resource-group"

# Paste a full ARM resource ID to use an existing EG namespace, or leave empty to create one.
# event_grid_resource_id="/subscriptions/.../resourceGroups/.../providers/Microsoft.EventGrid/namespaces/..."

# EG creation settings (only used when event_grid_resource_id is empty):
# eg_namespace_name="my-eg-namespace"
# eg_resource_group="my-resource-group"
# eg_location="westus2"

# User-assigned managed identity (leave commented out to use system MI):
# user_assigned_mi="/subscriptions/.../resourceGroups/.../providers/Microsoft.ManagedIdentity/userAssignedIdentities/..."

# Non-default container registry for the dataflow graph asset:
# registry_host="myregistry.azurecr.io"

# Protocol config (defaults to OPC UA with simulator):
# protocol="opcua"
# endpoint_name="anonymous-endpoint"
# endpoint_address="opc.tcp://opcplc-000000.azure-iot-operations:50000"
# deploy_opc_plc="true"
# asset_name="method-call-asset"
# action_name="Switch"

# skip_role_assignments="false"
