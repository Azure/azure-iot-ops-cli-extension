# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from knack.help_files import helps


def load_iotops_adr_help():
    helps[
        "iot ops asset"
    ] = """
        type: group
        short-summary: Asset management.
        long-summary: This command group applies to classic assets. For namespace asset mgmt (latest), use
          `az iot ops ns` commands. More information on asset management is available at aka.ms/asset-overview.
    """

    helps[
        "iot ops asset create"
    ] = """
        type: command
        short-summary: Create an asset.
        long-summary: For examples of file formats, please see aka.ms/aziotops-assets

        examples:
        - name: Create an asset using the given instance in the same resource group.
          text: >
            az iot ops asset create --name myasset -g myresourcegroup --endpoint-profile myassetendpoint --instance myinstance

        - name: Create an asset using the given instance in a different resource group but same subscription. Note that the Digital
                Operations Experience may not display the asset if it is in a different subscription from the instance.
          text: >
            az iot ops asset create --name myasset -g myresourcegroup --endpoint-profile myassetendpoint --instance myinstance
            --instance-resource-group myinstanceresourcegroup

        - name: Create a disabled asset using a file containing events.
          text: >
            az iot ops asset create --name myasset -g myresourcegroup --endpoint-profile myassetendpoint --instance myinstance
            --event-file /path/to/myasset_events.csv --disable

        - name: Create an asset with the given pre-filled values.
          text: >
            az iot ops asset create --name myasset -g myresourcegroup --endpoint-profile myassetendpoint --instance myinstance
            --event event_notifier=EventNotifier1 name=myEvent1 observability_mode=log sampling_interval=10 queue_size=2 --event
            event_notifier=EventNotifier2 name=myEvent2 --dataset-publish-int 1250 --dataset-queue-size 2 --dataset-sample-int 30
            --event-publish-int 750 --event-queue-size 3 --event-sample-int 50
            --description 'Description for a test asset.'
            --documentation-uri www.contoso.com --external-asset-id 000-000-1234 --hardware-revision 10.0
            --product-code XXX100 --software-revision 0.1 --manufacturer Contoso
            --manufacturer-uri constoso.com --model AssetModel --serial-number 000-000-ABC10
            --custom-attribute work_location=factory
    """

    helps[
        "iot ops asset query"
    ] = """
        type: command
        short-summary: Query the Resource Graph for assets.

        examples:
        - name: Query for assets that are disabled within a given resource group.
          text: >
            az iot ops asset query -g myresourcegroup --disabled
        - name: Query for assets that have the given model, manufacturer, and serial number.
          text: >
            az iot ops asset query --model model1 --manufacturer contoso --serial-number 000-000-ABC10
    """

    helps[
        "iot ops asset show"
    ] = """
        type: command
        short-summary: Show an asset.

        examples:
        - name: Show the details of an asset.
          text: >
            az iot ops asset show --name myasset -g myresourcegroup
    """

    helps[
        "iot ops asset update"
    ] = """
        type: command
        short-summary: Update an asset.
        long-summary: To update datasets and events, please use the command groups `az iot ops asset dataset` and
            `az iot ops asset event` respectively.

        examples:
        - name: Update an asset's dataset and event defaults.
          text: >
            az iot ops asset update --name myasset -g myresourcegroup --dataset-publish-int 1250 --dataset-queue-size 2 --dataset-sample-int 30
            --event-publish-int 750 --event-queue-size 3 --event-sample-int 50

        - name: Update an asset's description, documentation uri, hardware revision, product code,
                and software revision.
          text: >
            az iot ops asset update --name myasset -g myresourcegroup --description "Updated test asset description."
            --documentation-uri www.contoso.com --hardware-revision 11.0
            --product-code XXX102 --software-revision 0.2

        - name: Update an asset's manufacturer, manufacturer uri, model, serial number, and custom attribute.
          text: >
            az iot ops asset update --name myasset -g myresourcegroup --manufacturer Contoso
            --manufacturer-uri constoso2.com --model NewAssetModel --serial-number 000-000-ABC11
            --custom-attribute work_location=new_factory --custom-attribute secondary_work_location=factory

        - name: Disable an asset and remove a custom attribute called "work_site".
          text: >
            az iot ops asset update --name myasset -g myresourcegroup --disable --custom-attribute work_site=""
    """

    helps[
        "iot ops asset delete"
    ] = """
        type: command
        short-summary: Delete an asset.
        examples:
        - name: Delete an asset.
          text: >
            az iot ops asset delete --name myasset -g myresourcegroup
    """

    helps[
        "iot ops asset dataset"
    ] = """
        type: group
        short-summary: Manage datasets in an asset.
        long-summary: A dataset will be created once a point is created via `az iot ops asset dataset point add`.
          This command group applies to classic assets. For namespace asset mgmt (latest), use `az iot ops ns` commands.
    """

    helps[
        "iot ops asset dataset list"
    ] = """
        type: command
        short-summary: List datasets within an asset.

        examples:
        - name: List datasets within an asset.
          text: >
            az iot ops asset dataset list -g myresourcegroup --asset myasset
    """

    helps[
        "iot ops asset dataset show"
    ] = """
        type: command
        short-summary: Show a dataset within an asset.

        examples:
        - name: Show the details of a dataset in an asset.
          text: >
            az iot ops asset dataset show -g myresourcegroup --asset myasset -n default
    """

    helps[
        "iot ops asset dataset point"
    ] = """
        type: group
        short-summary: Manage data-points in an asset dataset.
        long-summary: This command group applies to classic assets. For namespace asset mgmt (latest), use `az iot ops ns` commands.
    """

    helps[
        "iot ops asset dataset point add"
    ] = """
        type: command
        short-summary: Add a datapoint to an asset dataset.
        long-summary: If no datasets exist yet, this will create a new dataset.

        examples:
        - name: Add a datapoint to an asset.
          text: >
            az iot ops asset dataset point add --asset myasset -g myresourcegroup --dataset default --data-source mydatasource --name data1

        - name: Add a datapoint to an asset with datapoint name, observability mode, custom queue size,
                and custom sampling interval.
          text: >
            az iot ops asset dataset point add --asset myasset -g myresourcegroup --dataset default --data-source mydatasource --name data1
            --observability-mode log --queue-size 5 --sampling-interval 200
    """

    helps[
        "iot ops asset dataset point export"
    ] = """
        type: command
        short-summary: Export data-points in an asset dataset.
        long-summary: The file name will be {asset_name}_{dataset_name}_dataPoints.{file_type}.
        examples:
        - name: Export all data-points in an asset in JSON format.
          text: >
            az iot ops asset dataset point export --asset myasset -g myresourcegroup --dataset default
        - name: Export all data-points in an asset in CSV format in a specific output directory that can be uploaded via the Digital Operations Experience.
          text: >
            az iot ops asset dataset point export --asset myasset -g myresourcegroup --dataset default --format csv --output-dir myAssetsFiles
        - name: Export all data-points in an asset in YAML format. Replace the file if one is present already.
          text: >
            az iot ops asset dataset point export --asset myasset -g myresourcegroup --dataset default --format yaml --replace
    """

    helps[
        "iot ops asset dataset point import"
    ] = """
        type: command
        short-summary: Import data-points in an asset dataset.
        long-summary: For examples of file formats, please see aka.ms/aziotops-assets
        examples:
        - name: Import all data-points from a file. These data-points will be appended to the asset dataset's current data-points. Data-points with duplicate names will be ignored.
          text: >
            az iot ops asset dataset point import --asset myasset -g myresourcegroup --dataset default --input-file myasset_default_dataPoints.csv
        - name: Import all data-points from a file. These data-points will be appended to the asset dataset's current data-points. Data-points with duplicate names will replace the current asset data-points.
          text: >
            az iot ops asset dataset point import --asset myasset -g myresourcegroup --dataset default --input-file myasset_default_dataPoints.json --replace
    """

    helps[
        "iot ops asset dataset point list"
    ] = """
        type: command
        short-summary: List data-points in an asset dataset.
        examples:
        - name: List all points in an asset dataset.
          text: >
            az iot ops asset dataset point list --asset myasset -g myresourcegroup --dataset default
    """

    helps[
        "iot ops asset dataset point remove"
    ] = """
        type: command
        short-summary: Remove a datapoint in an asset dataset.

        examples:
        - name: Remove a datapoint from an asset via the datapoint name.
          text: >
            az iot ops asset dataset point remove --asset myasset -g myresourcegroup --dataset default --name data1
    """

    helps[
        "iot ops asset event"
    ] = """
        type: group
        short-summary: Manage events in an asset.
        long-summary: This command group applies to classic assets. For namespace asset mgmt (latest), use `az iot ops ns` commands.
    """

    helps[
        "iot ops asset event add"
    ] = """
        type: command
        short-summary: Add an event to an asset.

        examples:
        - name: Add an event to an asset.
          text: >
            az iot ops asset event add --asset myasset -g myresourcegroup --event-notifier eventId --name eventName

        - name: Add an event to an asset with event name, observability mode, custom queue size,
                and custom sampling interval.
          text: >
            az iot ops asset event add --asset MyAsset -g MyRG --event-notifier eventId --name eventName
            --observability-mode log --queue-size 2 --sampling-interval 500
    """

    helps[
        "iot ops asset event export"
    ] = """
        type: command
        short-summary: Export events in an asset.
        long-summary: The file name will be {asset_name}_events.{file_type}.
        examples:
        - name: Export all events in an asset in JSON format.
          text: >
            az iot ops asset event export --asset myasset -g myresourcegroup
        - name: Export all events in an asset in CSV format in a specific output directory that can be uploaded to the Digital Operations Experience.
          text: >
            az iot ops asset event export --asset myasset -g myresourcegroup --format csv --output-dir myAssetFiles
        - name: Export all events in an asset in YAML format. Replace the file if one is present already.
          text: >
            az iot ops asset event export --asset myasset -g myresourcegroup --format yaml --replace
    """

    helps[
        "iot ops asset event import"
    ] = """
        type: command
        short-summary: Import events in an asset.
        long-summary: For examples of file formats, please see aka.ms/aziotops-assets
        examples:
        - name: Import all events from a file. These events will be appended to the asset's current events. Events with duplicate names will be ignored.
          text: >
            az iot ops asset event import --asset myasset -g myresourcegroup --input-file myasset_events.yaml
        - name: Import all events from a file. These events will appended the asset's current events. Events with duplicate names will replace the current asset events.
          text: >
            az iot ops asset event import --asset myasset -g myresourcegroup --input-file myasset_events.csv --replace
    """

    helps[
        "iot ops asset event list"
    ] = """
        type: command
        short-summary: List events in an asset.

        examples:
        - name: List all events in an asset.
          text: >
            az iot ops asset event list --asset myasset -g myresourcegroup
    """

    helps[
        "iot ops asset event remove"
    ] = """
        type: command
        short-summary: Remove an event in an asset.

        examples:
        - name: Remove an event from an asset via the event name.
          text: >
            az iot ops asset event remove --asset myasset -g myresourcegroup --name myevent
    """

    helps[
        "iot ops asset endpoint"
    ] = """
        type: group
        short-summary: Manage asset endpoint profiles.
        long-summary: This command group applies to classic assets. For namespace asset mgmt (latest), use `az iot ops ns` commands.
    """

    helps[
        "iot ops asset endpoint create"
    ] = """
        type: group
        short-summary: Create asset endpoint profiles.
        long-summary: This command group applies to classic assets. For namespace asset mgmt (latest), use `az iot ops ns` commands.
    """

    helps[
        "iot ops asset endpoint create opcua"
    ] = """
        type: command
        short-summary: Create an asset endpoint profile for an OPCUA connector.
        long-summary: |
                      Azure IoT OPC UA Connector (preview) uses the same client certificate for all secure
                      channels between itself and the OPC UA servers that it connects to.

                      For OPC UA connector arguments, a value of -1 means that parameter will not be used (ex: --session-reconnect-backoff -1 means that no exponential backoff should be used).
                      A value of 0 means use the fastest practical rate (ex: --default-sampling-int 0 means use the fastest sampling interval possible for the server).

                      For more information on how to configure asset endpoints for the OPC UA connector, please see https://aka.ms/aio-opcua-quickstart
        examples:
        - name: Create an asset endpoint with anonymous user authentication using the given instance in the same resource group.
          text: >
            az iot ops asset endpoint create opcua --name myprofile -g myresourcegroup --instance myinstance
            --target-address opc.tcp://opcplc-000000:50000
        - name: Create an asset endpoint with anonymous user authentication using the given instance in a different resource group but same subscription. Note that the Digital
                Operations Experience may not display the asset endpoint profile if it is in a different subscription from the instance.
          text: >
            az iot ops asset endpoint create opcua --name myprofile -g myresourcegroup --instance myinstance
            --instance-resource-group myinstanceresourcegroup
            --target-address opc.tcp://opcplc-000000:50000
        - name: Create an asset endpoint with username-password user authentication using the given instance in the same resource group.
          text: >
            az iot ops asset endpoint create opcua --name myprofile -g myresourcegroup --instance myinstance
            --target-address opc.tcp://opcplc-000000:50000
            --username-ref myusername --password-ref mypassword
        - name: Create an asset endpoint with anonymous user authentication and recommended values for the OPCUA configuration using the given instance in the same resource group.
                Note that for successfully using the connector, you will need to have the OPC PLC service deployed and the target address must point to the service.
                If the OPC PLC service is in the same cluster and namespace as IoT Ops, the target address should be formatted as `opc.tcp://{opc-plc-service-name}:{service-port}`
                If the OPC PLC service is in the same cluster but different namespace as IoT Ops, include the service namespace like so `opc.tcp://{opc-plc-service-name}.{service-namespace}:{service-port}`
                For more information, please see aka.ms/opcua-quickstart
          text: >
            az iot ops asset endpoint create opcua --name myprofile -g myresourcegroup --instance myinstance
            --target-address opc.tcp://opcplc-000000:50000 --accept-untrusted-certs --application myopcuaconnector
            --default-publishing-int 1000 --default-queue-size 1 --default-sampling-int 1000 --keep-alive 10000 --run-asset-discovery
            --security-mode sign --security-policy Basic256 --session-keep-alive 10000 --session-reconnect-backoff 10000 --session-reconnect-period 2000
            --session-timeout 60000 --subscription-life-time 60000 --subscription-max-items 1000
    """

    helps[
        "iot ops asset endpoint query"
    ] = """
        type: command
        short-summary: Query the Resource Graph for asset endpoint profiles.
        examples:
        - name: Query for asset endpoint profiles that have anonymous authentication.
          text: >
            az iot ops asset endpoint query --authentication-mode Anonymous
        - name: Query for asset endpoint profiles that have the given target address and instance name.
          text: >
            az iot ops asset endpoint query --target-address opc.tcp://opcplc-000000:50000 --instance myinstance
    """

    helps[
        "iot ops asset endpoint show"
    ] = """
        type: command
        short-summary: Show an asset endpoint profile.
        examples:
        - name: Show the details of an asset endpoint profile.
          text: >
            az iot ops asset endpoint show --name myprofile -g myresourcegroup
    """

    helps[
        "iot ops asset endpoint update"
    ] = """
        type: command
        short-summary: Update an asset endpoint profile.
        long-summary: To update owned certificates, please use the command group `az iot ops asset endpoint certificate`.
        examples:
        - name: Update an asset endpoint profile's authentication mode to use anonymous user authentication.
          text: >
            az iot ops asset endpoint update --name myprofile -g myresourcegroup
            --authentication-mode Anonymous
        - name: Update an asset endpoint profile's username and password reference with prefilled values. This will transform the
                authentication mode to username-password if it is not so already.
          text: >
            az iot ops asset endpoint update --name myAssetEndpoint -g myRG
            --username-ref "aio-opc-ua-broker-user-authentication/opc-plc-username"
            --password-ref "aio-opc-ua-broker-user-authentication/opc-plc-password"
    """

    helps[
        "iot ops asset endpoint delete"
    ] = """
        type: command
        short-summary: Delete an asset endpoint profile.
        examples:
        - name: Delete an asset endpoint profile.
          text: >
            az iot ops asset endpoint delete --name myprofile -g myresourcegroup
    """

    # ADR REFRESH STARTS HERE
    helps[
        "iot ops ns"
    ] = """
        type: group
        short-summary: Device Registry Namespaces management.
        long-summary: |
          Namespaces enable organizing your namespaced assets and devices.
    """

    helps[
        "iot ops ns create"
    ] = """
        type: command
        short-summary: Create a Device Registry namespace.

        examples:
        - name: Create a namespace with minimal configuration.
          text: >
            az iot ops ns create -n mynamespace -g myResourceGroup

        - name: Create a namespace with custom location and tags
          text: >
            az iot ops ns create -n mynamespace -g myResourceGroup
            --location "eastus" --tags env=prod department=operations
    """

    helps[
        "iot ops ns delete"
    ] = """
        type: command
        short-summary: Delete a Device Registry namespace.

        examples:
        - name: Delete a namespace
          text: >
            az iot ops ns delete -n mynamespace -g myResourceGroup
    """

    helps[
        "iot ops ns show"
    ] = """
        type: command
        short-summary: Show details of a Device Registry namespace.

        examples:
        - name: Show details of a namespace
          text: >
            az iot ops ns show -n mynamespace -g myResourceGroup
    """

    helps[
        "iot ops ns list"
    ] = """
        type: command
        short-summary: List Device Registry namespaces.

        examples:
        - name: List all namespaces in a resource group
          text: >
            az iot ops ns list -g myResourceGroup

        - name: List all namespaces in the current subscription
          text: >
            az iot ops ns list
    """

    helps[
        "iot ops ns update"
    ] = """
        type: command
        short-summary: Update a Device Registry namespace.

        examples:
        - name: Update tags for a namespace
          text: >
            az iot ops ns update -n mynamespace -g myResourceGroup --tags env=test department=iot
    """

    helps[
        "iot ops ns mgmt-endpoint"
    ] = """
        type: group
        short-summary: Manage management endpoints on Device Registry namespaces.
        long-summary: |
          Management endpoints are configured by `az iot ops mgmt-actions enable` and
          associate an Event Grid namespace with a custom location scope.
    """

    helps[
        "iot ops ns mgmt-endpoint remove"
    ] = """
        type: command
        short-summary: Remove a management endpoint entry from a Device Registry namespace.
        long-summary: |
          Removes a single management endpoint entry from the ADR namespace.
          This is useful for targeted cleanup when full `mgmt-actions disable` teardown
          is not appropriate — for example, when switching Event Grid namespaces,
          cleaning up after an externally deleted Event Grid namespace, or removing
          management actions configuration for a specific custom location scope without
          tearing down the full infrastructure.

          Use `az iot ops ns show` to inspect available endpoint keys under
          properties.management.endpoints.

        examples:
        - name: Remove a management endpoint entry by key.
          text: >
            az iot ops ns mgmt-endpoint remove -n mynamespace -g myResourceGroup
            --endpoint-key $CUSTOM_LOCATION_RESOURCE_ID

        - name: Remove a management endpoint entry without confirmation prompt.
          text: >
            az iot ops ns mgmt-endpoint remove -n mynamespace -g myResourceGroup
            --endpoint-key $CUSTOM_LOCATION_RESOURCE_ID
            -y
    """

    helps[
        "iot ops ns device"
    ] = """
        type: group
        short-summary: Manage devices in Device Registry namespaces.
    """

    helps[
        "iot ops ns device create"
    ] = """
        type: command
        short-summary: Create a device in a Device Registry namespace.
        long-summary: The device will be linked to an Azure IoT Operations instance.

        examples:
        - name: Create a device with minimal configuration
          text: >
            az iot ops ns device create --name mydevice --instance myInstance -g myInstanceResourceGroup

        - name: Create a device with custom attributes
          text: >
            az iot ops ns device create --name mydevice --instance myInstance -g myInstanceResourceGroup
            --attr location=building1 floor=3

        - name: Create a device with manufacturer information and operating system details
          text: >
            az iot ops ns device create --name mydevice --instance myInstance -g myInstanceResourceGroup
            --manufacturer "Contoso" --model "Gateway X1" --os "Linux" --os-version "4.15"

        - name: Create a disabled device with tags
          text: >
            az iot ops ns device create --name mydevice --instance myInstance -g myInstanceResourceGroup
            --disabled --tags environment=test criticality=low
    """

    helps[
        "iot ops ns device query"
    ] = """
        type: command
        short-summary: Query devices in Device Registry namespaces.
        long-summary: |
          Query devices across namespaces based on various search criteria including device name,
          manufacturer, model, and more.

        examples:
        - name: Query for devices in an IoT Operations instance
          text: >
            az iot ops ns device query --instance myInstance -g myInstanceResourceGroup

        - name: Query for a specific device by name
          text: >
            az iot ops ns device query --name mydevice

        - name: Query for devices from a specific manufacturer
          text: >
            az iot ops ns device query --manufacturer "Contoso"

        - name: Use a custom query to search for devices
          text: >
            az iot ops ns device query --custom-query "where tags.environment=='production'"
    """

    helps[
        "iot ops ns device show"
    ] = """
        type: command
        short-summary: Show details of a device in a Device Registry namespace.

        examples:
        - name: Show details of a device
          text: >
            az iot ops ns device show --name mydevice --instance myInstance -g myInstanceResourceGroup
    """

    helps[
        "iot ops ns device delete"
    ] = """
        type: command
        short-summary: Delete a device from a Device Registry namespace.

        examples:
        - name: Delete a device
          text: >
            az iot ops ns device delete --name mydevice --instance myInstance -g myInstanceResourceGroup
    """

    helps[
        "iot ops ns device update"
    ] = """
        type: command
        short-summary: Update a device in a Device Registry namespace.

        examples:
        - name: Update device custom attributes
          text: >
            az iot ops ns device update --name mydevice --instance myInstance -g myInstanceResourceGroup
            --attr location=building2 floor=5

        - name: Update operating system version
          text: >
            az iot ops ns device update --name mydevice --instance myInstance -g myInstanceResourceGroup
            --os-version "4.18"

        - name: Disable a device
          text: >
            az iot ops ns device update --name mydevice --instance myInstance -g myInstanceResourceGroup
            --disabled

        - name: Update device tags
          text: >
            az iot ops ns device update --name mydevice --instance myInstance -g myInstanceResourceGroup
            --tags environment=production criticality=high
    """

    helps[
        "iot ops ns device endpoint"
    ] = """
        type: group
        short-summary: Manage endpoints for devices in Device Registry namespaces.
        long-summary: |
          Endpoints define the destinations where data will be sent from this namespace.
          Currently, only Event Grid Topics are supported as endpoints.
    """

    helps[
        "iot ops ns device endpoint list"
    ] = """
        type: command
        short-summary: List all endpoints of a device in a Device Registry namespace.

        examples:
        - name: List inbound and outbound endpoints of a device
          text: >
            az iot ops ns device endpoint list --device mydevice --instance myInstance -g myInstanceResourceGroup
        - name: List only inbound endpoints of a device
          text: >
            az iot ops ns device endpoint list --device mydevice --instance myInstance -g myInstanceResourceGroup --inbound
    """

    helps[
        "iot ops ns device endpoint inbound"
    ] = """
        type: group
        short-summary: Manage inbound endpoints for devices in Device Registry namespaces.
        long-summary: |
          Inbound endpoints define communication channels from the device to the IoT Ops platform.
    """

    helps[
        "iot ops ns device endpoint inbound list"
    ] = """
        type: command
        short-summary: List inbound endpoints of a device in a Device Registry namespace.

        examples:
        - name: List all inbound endpoints of a device
          text: >
            az iot ops ns device endpoint inbound list --device mydevice --instance myInstance -g myInstanceResourceGroup
        - name: List all Media endpoints of a device using a keyword
          text: >
            az iot ops ns device endpoint inbound list --device mydevice --instance myInstance -g myInstanceResourceGroup --endpoint-type media
        - name: List all Media endpoints of a device using the full endpoint type
          text: >
            az iot ops ns device endpoint inbound list --device mydevice --instance myInstance -g myInstanceResourceGroup --endpoint-type Microsoft.Media
    """

    helps[
        "iot ops ns device endpoint inbound remove"
    ] = """
        type: command
        short-summary: Remove inbound endpoints from a device in a Device Registry namespace.

        examples:
        - name: Remove a single inbound endpoint from a device
          text: >
            az iot ops ns device endpoint inbound remove --device mydevice --instance myInstance -g myInstanceResourceGroup --endpoint myEndpoint

        - name: Remove multiple inbound endpoints from a device
          text: >
            az iot ops ns device endpoint inbound remove --device mydevice --instance myInstance -g myInstanceResourceGroup --endpoint myEndpoint1 myEndpoint2
    """

    helps[
        "iot ops ns device endpoint inbound apply"
    ] = """
        type: command
        short-summary: Apply an inbound endpoint to a device using a generalized connector-type approach.
        long-summary: |
          The generalized apply command is schema-driven. For non-OPC UA connector types it looks up
          an existing connector template for the specified --connector-type, auto-resolves the
          endpoint version, and optionally validates --endpoint-config against the connector schema.

          Schema validation of --endpoint-config is only performed when the connector's
          additionalConfigurationSchema uses JSON Schema Draft-07
          (http://json-schema.org/draft-07/schema#). If the schema uses a different dialect,
          validation is skipped with a warning and the endpoint is still created.

          OPC UA (Microsoft.OpcUa) is a special case: it does not use Akri connector templates.
          Its schema and version are derived from bundled metadata. The instance must have OPC UA
          enabled (feature.opcua.mode != Disabled).

          Use --show-template to discover valid configuration fields before creating an endpoint.

        examples:
        - name: Discover default endpoint configuration template for an OPC UA connector
          text: >
            az iot ops ns device endpoint inbound apply --connector-type Microsoft.OpcUa --instance myInstance -g myInstanceResourceGroup --show-template config

        - name: Discover full schema template (with types and constraints) for an OPC UA connector
          text: >
            az iot ops ns device endpoint inbound apply --connector-type Microsoft.OpcUa --instance myInstance -g myInstanceResourceGroup --show-template schema

        - name: Apply a generalized OPC UA inbound endpoint using a JSON config file
          text: >
            az iot ops ns device endpoint inbound apply --device mydevice --name myOPCUAEndpoint --endpoint-address "opc.tcp://192.168.1.100:4840" --connector-type Microsoft.OpcUa --instance myInstance -g myInstanceResourceGroup --endpoint-config ./opcua-endpoint-config.json

        - name: Apply a generalized OPC UA inbound endpoint using a YAML config file
          text: >
            az iot ops ns device endpoint inbound apply --device mydevice --name myOPCUAEndpoint --endpoint-address "opc.tcp://192.168.1.100:4840" --connector-type Microsoft.OpcUa --instance myInstance -g myInstanceResourceGroup --endpoint-config ./opcua-endpoint-config.yaml

        - name: Apply a generalized OPC UA inbound endpoint using inline JSON with nested objects
          text: >
            az iot ops ns device endpoint inbound apply --device mydevice --name myOPCUAEndpoint --endpoint-address "opc.tcp://192.168.1.100:4840" --connector-type Microsoft.OpcUa --instance myInstance -g myInstanceResourceGroup --endpoint-config '{"applicationName":"line1-opcua-client","keepAliveMilliseconds":10000,"session":{"timeoutMilliseconds":60000,"reconnectPeriod":5000},"security":{"securityPolicy":"Basic256Sha256","securityMode":"SignAndEncrypt","autoAcceptUntrustedServerCertificates":true}}'

        - name: Apply a generalized ONVIF inbound endpoint using a config file with authentication
          text: >
            az iot ops ns device endpoint inbound apply --device mydevice --name myONVIFEndpoint --endpoint-address "http://192.168.1.100:8000/onvif/device_service" --connector-type Microsoft.Onvif --instance myInstance -g myInstanceResourceGroup --endpoint-config ./onvif-config.json --user-ref auth-secret/username --pass-ref auth-secret/password

        - name: Apply an inbound endpoint skipping connector template check (no schema validation, no version auto-resolution)
          text: >
            az iot ops ns device endpoint inbound apply --device mydevice --name myEndpoint --endpoint-address "opc.tcp://192.168.1.100:4840" --connector-type Microsoft.OpcUa --instance myInstance -g myInstanceResourceGroup --skip-connector-check

        - name: Apply an inbound endpoint but error if it already exists (prevent overwrite)
          text: >
            az iot ops ns device endpoint inbound apply --device mydevice --name myOPCUAEndpoint --endpoint-address "opc.tcp://192.168.1.100:4840" --connector-type Microsoft.OpcUa --instance myInstance -g myInstanceResourceGroup --no-replace
    """

    helps[
        "iot ops ns device endpoint inbound add"
    ] = """
        type: group
        short-summary: Add a type-specific inbound endpoint to a device in a Device Registry namespace.
    """

    helps[
        "iot ops ns device endpoint inbound add custom"
    ] = """
        type: command
        short-summary: Add a custom inbound endpoint to a device in a Device Registry namespace.
        long-summary: |
          Custom endpoints allow you to define your own endpoint type and configuration.

        examples:
        - name: Add a basic custom endpoint to a device
          text: >
            az iot ops ns device endpoint inbound add custom --device mydevice --instance myInstance -g myInstanceResourceGroup --name myCustomEndpoint --endpoint-type "Custom.Type" --endpoint-address "192.168.1.100:8080"

        - name: Add a custom endpoint with authentication
          text: >
            az iot ops ns device endpoint inbound add custom --device mydevice --instance myInstance -g myInstanceResourceGroup --name myCustomEndpoint --endpoint-type "Custom.Type" --endpoint-address "192.168.1.100:8080" --user-ref auth-secret/username --pass-ref auth-secret/password

        - name: Add a custom endpoint with certificate authentication and a version
          text: >
            az iot ops ns device endpoint inbound add custom --device mydevice --instance myInstance -g myInstanceResourceGroup --name myCustomEndpoint --endpoint-type "Custom.Type" --endpoint-address "192.168.1.100:8080" --cert-ref cert-secret/certificate --version "1.0"

        - name: Add a custom endpoint with enhanced certificate authentication including private key
          text: >
            az iot ops ns device endpoint inbound add custom --device mydevice --instance myInstance -g myInstanceResourceGroup --name myCustomEndpoint --endpoint-type "Custom.Type" --endpoint-address "192.168.1.100:8080" --cert-ref cert-secret/certificate --key-ref cert-secret/privateKey

        - name: Add a custom endpoint with certificate authentication including intermediate certificates
          text: >
            az iot ops ns device endpoint inbound add custom --device mydevice --instance myInstance -g myInstanceResourceGroup --name myCustomEndpoint --endpoint-type "Custom.Type" --endpoint-address "192.168.1.100:8080" --cert-ref cert-secret/certificate --icr cert-secret/intermediateCerts

        - name: Add a custom endpoint with full certificate chain authentication
          text: >
            az iot ops ns device endpoint inbound add custom --device mydevice --instance myInstance -g myInstanceResourceGroup --name myCustomEndpoint --endpoint-type "Custom.Type" --endpoint-address "192.168.1.100:8080" --cert-ref cert-secret/certificate --key-ref cert-secret/privateKey --icr cert-secret/intermediateCerts

        - name: Add a custom endpoint with additional configuration
          text: >
            az iot ops ns device endpoint inbound add custom --device mydevice --instance myInstance -g myInstanceResourceGroup --name myCustomEndpoint --endpoint-type "Custom.Type" --endpoint-address "192.168.1.100:8080" --additional-config "{\\\"customSetting\\\": \\\"value\\\"}"
    """

    helps[
        "iot ops ns device endpoint inbound add media"
    ] = """
        type: command
        short-summary: Add a media inbound endpoint to a device in a Device Registry namespace.
        long-summary: |
          For more information on media connectors, please see https://aka.ms/aio-media-quickstart

        examples:
        - name: Add a basic media endpoint to a device
          text: >
            az iot ops ns device endpoint inbound add media --device mydevice --instance myInstance -g myInstanceResourceGroup --name myCameraEndpoint --endpoint-address "rtsp://192.168.1.100:554/stream"

        - name: Add a media endpoint with authentication
          text: >
            az iot ops ns device endpoint inbound add media --device mydevice --instance myInstance -g myInstanceResourceGroup --name myCameraEndpoint --endpoint-address "rtsp://192.168.1.100:554/stream" --user-ref auth-secret/username --pass-ref auth-secret/password
    """

    helps[
        "iot ops ns device endpoint inbound add onvif"
    ] = """
        type: command
        short-summary: Add an ONVIF inbound endpoint to a device in a Device Registry namespace.
        long-summary: |
          For more information on ONVIF connectors, please see https://aka.ms/aio-onvif-quickstart

        examples:
        - name: Add a basic ONVIF endpoint to a device
          text: >
            az iot ops ns device endpoint inbound add onvif --device mydevice --instance myInstance -g myInstanceResourceGroup --name myONVIFEndpoint --endpoint-address "http://192.168.1.100:8000/onvif/device_service"

        - name: Add an ONVIF endpoint with authentication
          text: >
            az iot ops ns device endpoint inbound add onvif --device mydevice --instance myInstance -g myInstanceResourceGroup --name myONVIFEndpoint --endpoint-address "http://192.168.1.100:8000/onvif/device_service" --user-ref auth-secret/username --pass-ref auth-secret/password

        - name: Add an ONVIF endpoint that accepts invalid hostnames and certificates
          text: >
            az iot ops ns device endpoint inbound add onvif --device mydevice --instance myInstance -g myInstanceResourceGroup --name myONVIFEndpoint --endpoint-address "https://192.168.1.100:8000/onvif/device_service" --accept-invalid-hostnames --accept-invalid-certificates
    """

    helps[
        "iot ops ns device endpoint inbound add opcua"
    ] = """
        type: command
        short-summary: Add an OPC UA inbound endpoint to a device in a Device Registry namespace.
        long-summary: |
          For more information on OPC UA connectors, please see https://aka.ms/aio-opcua-quickstart

        examples:
        - name: Add a basic OPC UA endpoint to a device
          text: >
            az iot ops ns device endpoint inbound add opcua --device mydevice --instance myInstance -g myInstanceResourceGroup --name myOPCUAEndpoint --endpoint-address "opc.tcp://192.168.1.100:4840"

        - name: Add an OPC UA endpoint with authentication
          text: >
            az iot ops ns device endpoint inbound add opcua --device mydevice --instance myInstance -g myInstanceResourceGroup --name myOPCUAEndpoint --endpoint-address "opc.tcp://192.168.1.100:4840" --user-ref auth-secret/username --pass-ref auth-secret/password

        - name: Add an OPC UA endpoint with a custom application name
          text: >
            az iot ops ns device endpoint inbound add opcua --device mydevice --instance myInstance -g myInstanceResourceGroup --name myOPCUAEndpoint --endpoint-address "opc.tcp://192.168.1.100:4840" --application-name "My OPC UA App"

        - name: Add an OPC UA endpoint with customized session parameters
          text: >
            az iot ops ns device endpoint inbound add opcua --device mydevice --instance myInstance -g myInstanceResourceGroup --name myOPCUAEndpoint --endpoint-address "opc.tcp://192.168.1.100:4840" --keep-alive 15000 --session-timeout 90000 --publishing-interval 2000 --sampling-interval 1500

        - name: Add an OPC UA endpoint with security settings and asset discovery enabled
          text: >
            az iot ops ns device endpoint inbound add opcua --device mydevice --instance myInstance -g myInstanceResourceGroup --name myOPCUAEndpoint --endpoint-address "opc.tcp://192.168.1.100:4840" --security-policy "Basic256Sha256" --security-mode "SignAndEncrypt" --run-asset-discovery

        - name: Add an OPC UA endpoint with asset discovery and property sync to state store enabled
          text: >
            az iot ops ns device endpoint inbound add opcua --device mydevice --instance myInstance -g myInstanceResourceGroup --name myOPCUAEndpoint --endpoint-address "opc.tcp://192.168.1.100:4840" --run-asset-discovery --sync-props-into-dss
    """

    helps[
        "iot ops ns device endpoint inbound add rest"
    ] = """
        type: command
        short-summary: Add a rest inbound endpoint to a device in a Device Registry namespace.

        examples:
        - name: Add a basic rest endpoint to a device
          text: >
            az iot ops ns device endpoint inbound add rest --device mydevice --instance myInstance -g myInstanceResourceGroup --name myEndpoint --endpoint-address "https://api.example.com/data"

        - name: Add a rest endpoint with authentication
          text: >
            az iot ops ns device endpoint inbound add rest --device mydevice --instance myInstance -g myInstanceResourceGroup --name myEndpoint --endpoint-address "https://api.example.com/data" --user-ref auth-secret/username --pass-ref auth-secret/password

        - name: Add a rest endpoint with certificate authentication
          text: >
            az iot ops ns device endpoint inbound add rest --device mydevice --instance myInstance -g myInstanceResourceGroup --name myEndpoint --endpoint-address "https://api.example.com/data" --cert-ref cert-secret/certificate

        - name: Add a rest endpoint with enhanced certificate authentication including private key
          text: >
            az iot ops ns device endpoint inbound add rest --device mydevice --instance myInstance -g myInstanceResourceGroup --name myEndpoint --endpoint-address "https://api.example.com/data" --cert-ref cert-secret/certificate --key-ref cert-secret/privateKey

        - name: Add a rest endpoint with certificate authentication including intermediate certificates
          text: >
            az iot ops ns device endpoint inbound add rest --device mydevice --instance myInstance -g myInstanceResourceGroup --name myEndpoint --endpoint-address "https://api.example.com/data" --cert-ref cert-secret/certificate --icr cert-secret/intermediateCerts

        - name: Add a rest endpoint with full certificate chain authentication
          text: >
            az iot ops ns device endpoint inbound add rest --device mydevice --instance myInstance -g myInstanceResourceGroup --name myEndpoint --endpoint-address "https://api.example.com/data" --cert-ref cert-secret/certificate --key-ref cert-secret/privateKey --icr cert-secret/intermediateCerts
    """

    helps[
        "iot ops ns device endpoint inbound add sse"
    ] = """
        type: command
        short-summary: Add an SSE inbound endpoint to a device in a Device Registry namespace.

        examples:
        - name: Add a basic SSE endpoint to a device
          text: >
            az iot ops ns device endpoint inbound add sse --device mydevice --instance myInstance -g myInstanceResourceGroup --name mySSEEndpoint --endpoint-address "https://events.example.com/stream"

        - name: Add an SSE endpoint with authentication
          text: >
            az iot ops ns device endpoint inbound add sse --device mydevice --instance myInstance -g myInstanceResourceGroup --name mySSEEndpoint --endpoint-address "https://events.example.com/stream" --user-ref auth-secret/username --pass-ref auth-secret/password

        - name: Add an SSE endpoint with certificate authentication
          text: >
            az iot ops ns device endpoint inbound add sse --device mydevice --instance myInstance -g myInstanceResourceGroup --name mySSEEndpoint --endpoint-address "https://events.example.com/stream" --cert-ref cert-secret/certificate

        - name: Add an SSE endpoint with enhanced certificate authentication including private key
          text: >
            az iot ops ns device endpoint inbound add sse --device mydevice --instance myInstance -g myInstanceResourceGroup --name mySSEEndpoint --endpoint-address "https://events.example.com/stream" --cert-ref cert-secret/certificate --key-ref cert-secret/privateKey

        - name: Add an SSE endpoint with certificate authentication including intermediate certificates
          text: >
            az iot ops ns device endpoint inbound add sse --device mydevice --instance myInstance -g myInstanceResourceGroup --name mySSEEndpoint --endpoint-address "https://events.example.com/stream" --cert-ref cert-secret/certificate --icr cert-secret/intermediateCerts

        - name: Add an SSE endpoint with full certificate chain authentication
          text: >
            az iot ops ns device endpoint inbound add sse --device mydevice --instance myInstance -g myInstanceResourceGroup --name mySSEEndpoint --endpoint-address "https://events.example.com/stream" --cert-ref cert-secret/certificate --key-ref cert-secret/privateKey --icr cert-secret/intermediateCerts
    """

    helps[
        "iot ops ns device endpoint inbound add mqtt"
    ] = """
        type: command
        short-summary: Add an MQTT inbound endpoint to a device in a Device Registry namespace.

        examples:
        - name: Add a basic MQTT endpoint to a device connecting to in-cluster broker
          text: >
            az iot ops ns device endpoint inbound add mqtt --device mydevice --instance myInstance
            -g myInstanceResourceGroup --name myMqttEndpoint --endpoint-address "aio-broker:18883"
    """

    helps[
        "iot ops ns asset"
    ] = """
        type: group
        short-summary: Manage namespaced assets in an IoT Operations instance.
    """

    helps[
        "iot ops ns asset delete"
    ] = """
        type: command
        short-summary: Delete a namespaced asset from an IoT Operations instance.

        examples:
        - name: Delete an asset with confirmation prompt
          text: >
            az iot ops ns asset delete --name myasset --instance myInstance -g myInstanceResourceGroup

        - name: Delete an asset and skip the confirmation prompt
          text: >
            az iot ops ns asset delete --name myasset --instance myInstance -g myInstanceResourceGroup -y
    """

    helps[
        "iot ops ns asset query"
    ] = """
        type: command
        short-summary: Query namespaced assets.
        long-summary: |
          Query assets across namespaces based on various search criteria including asset name,
          device name, endpoint name and more.

        examples:
        - name: Query for assets in an IoT Operations instance
          text: >
            az iot ops ns asset query --instance myInstance -g myInstanceResourceGroup

        - name: Query for a specific asset by name
          text: >
            az iot ops ns asset query --name myasset

        - name: Query for assets associated with a specific device and endpoint
          text: >
            az iot ops ns asset query --device mydevice --endpoint myEndpoint

        - name: Use a custom query to search for assets
          text: >
            az iot ops ns asset query --custom-query "where tags.environment=='production'"
    """

    helps[
        "iot ops ns asset show"
    ] = """
        type: command
        short-summary: Show details of a namespaced asset in an IoT Operations instance.

        examples:
        - name: Show details of an asset
          text: >
            az iot ops ns asset show --name myasset --instance myInstance -g myInstanceResourceGroup
    """

    helps[
        "iot ops ns asset create"
    ] = """
        type: command
        short-summary: Create a namespaced asset in an IoT Operations instance.

        examples:
        - name: Create a namespaced asset for a given connector type
          text: >
            az iot ops ns asset create --name myasset --instance myInstance -g myInstanceResourceGroup
            --connector-type Microsoft.OpcUa --device mydevice --endpoint myEndpoint

        - name: Create a namespaced asset with a connector-specific configuration using a file
          text: >
            az iot ops ns asset create --name myasset --instance myInstance -g myInstanceResourceGroup
            --connector-type Microsoft.OpcUa --device mydevice --endpoint myEndpoint
            --asset-config path/to/config.yaml

        - name: Create a namespaced asset with a connector-specific configuration using inline JSON
          text: >
            az iot ops ns asset create --name myasset --instance myInstance -g myInstanceResourceGroup
            --connector-type Microsoft.OpcUa --device mydevice --endpoint myEndpoint
            --asset-config '{"defaultDatasetsConfiguration":{"publishingInterval":1000,"samplingInterval":500,"queueSize":5}}'

        - name: Create a namespaced asset with connector configuration and metadata in a single operation
          text: >
            az iot ops ns asset create --name myasset --instance myInstance -g myInstanceResourceGroup
            --connector-type Microsoft.OpcUa --device mydevice --endpoint myEndpoint
            --asset-config path/to/config.yaml --description "Factory floor sensor" --display-name "My Asset v1"
            --manufacturer "Contoso" --model "SensorX1" --serial-number "SN-001"

        - name: Show the configuration template for a connector type without creating an asset
          text: >
            az iot ops ns asset create --connector-type Microsoft.OpcUa --show-template config
            --instance myInstance -g myInstanceResourceGroup
    """

    helps[
        "iot ops ns asset update"
    ] = """
        type: command
        short-summary: Update a namespaced asset in an IoT Operations instance.
        long-summary: >
            The connector type is detected from the asset's device endpoint.
            Use --asset-config to supply connector-specific configuration (defaultDatasetsConfiguration,
            defaultEventsConfiguration, etc.). Use --show-template config to see the current asset
            configuration pre-filled with existing values (ready to edit and pass back via
            --asset-config). Use --show-template schema to see the full connector schema with types
            and constraints.

        examples:
        - name: Update an asset's basic properties
          text: >
            az iot ops ns asset update --name myasset --instance myInstance -g myInstanceResourceGroup
            --description "Updated description" --display-name "My Asset v2"

        - name: Update an asset's connector-specific configuration using a file
          text: >
            az iot ops ns asset update --name myasset --instance myInstance -g myInstanceResourceGroup
            --asset-config path/to/config.yaml

        - name: Update an asset's connector-specific configuration using inline JSON
          text: >
            az iot ops ns asset update --name myasset --instance myInstance -g myInstanceResourceGroup
            --asset-config '{"defaultDatasetsConfiguration":{"publishingInterval":2000,"samplingInterval":1000}}'

        - name: Update an asset's connector configuration along with metadata in a single operation
          text: >
            az iot ops ns asset update --name myasset --instance myInstance -g myInstanceResourceGroup
            --asset-config path/to/config.yaml --description "Updated factory sensor" --display-name "My Asset v2"
            --manufacturer "Contoso" --model "SensorX1" --serial-number "SN-001"

        - name: Show current asset config pre-filled with existing values (for editing before update)
          text: >
            az iot ops ns asset update --name myasset --instance myInstance -g myInstanceResourceGroup
            --show-template config

        - name: Show the full connector schema structure with types and constraints
          text: >
            az iot ops ns asset update --name myasset --instance myInstance -g myInstanceResourceGroup
            --show-template schema
    """

    helps[
        "iot ops ns asset custom"
    ] = """
        type: group
        short-summary: Manage namespaced assets that point to custom device endpoints.
    """

    helps[
        "iot ops ns asset custom create"
    ] = """
        type: command
        short-summary: Create a custom namespaced asset in an IoT Operations instance.

        examples:
        - name: Create a basic custom asset
          text: >
            az iot ops ns asset custom create --name mycustomasset --instance myInstance -g myInstanceResourceGroup
            --device mydevice --endpoint myEndpoint

        - name: Create a custom asset with additional metadata
          text: >
            az iot ops ns asset custom create --name mycustomasset --instance myInstance -g myInstanceResourceGroup
            --device mydevice --endpoint myEndpoint --description "Factory sensor" --display-name "Temperature Sensor"
            --model "TempSensor-X1" --manufacturer "Contoso" --serial-number "SN12345"

        - name: Create a custom asset with dataset and events configuration using inline JSON
          text: >
            az iot ops ns asset custom create --name mycustomasset --instance myInstance -g myInstanceResourceGroup
            --device mydevice --endpoint myEndpoint --dataset-config "{\\\"publishingInterval\\\": 1000}"
            --event-config "{\\\"queueSize\\\": 5}"

        - name: Create a custom asset with datasets use a BrokerStateStore destination, events use a Mqtt destination, and streams use a Storage destination.
          text: >
            az iot ops ns asset custom create --name mycustomasset --instance myInstance -g myInstanceResourceGroupmyResourceGroup
            --device mydevice --endpoint myEndpoint
            --dataset-dest key="myKey"
            --event-dest topic="factory/events/temperature/updated" qos=Qos0 retain=Never ttl=3600
            --stream-dest path="my/storage/path"
    """

    helps[
        "iot ops ns asset custom update"
    ] = """
        type: command
        short-summary: Update a custom namespaced asset in an IoT Operations instance.

        examples:
        - name: Update a custom asset's basic properties
          text: >
            az iot ops ns asset custom update --name mycustomasset --instance myInstance -g myInstanceResourceGroup
            --description "Updated factory sensor" --display-name "Temperature Sensor v2"

        - name: Update a custom asset with additional metadata
          text: >
            az iot ops ns asset custom update --name mycustomasset --instance myInstance -g myInstanceResourceGroup
            --model "TempSensor-X2" --manufacturer "Contoso" --serial-number "SN98765" --disable

        - name: Update a custom asset's dataset and events configuration
          text: >
            az iot ops ns asset custom update --name mycustomasset --instance myInstance -g myInstanceResourceGroup
            --dataset-config "{\\\"publishingInterval\\\": 2000}" --event-config "{\\\"queueSize\\\": 10}"

        - name: Update a custom asset's destinations so the datasets use a BrokerStateStore destination, events use a Mqtt destination, and streams use a Storage destination.
          text: >
            az iot ops ns asset custom update --name mycustomasset --instance myInstance -g myInstanceResourceGroup
            --dataset-dest key="myKey"
            --event-dest topic="factory/events/temperature/updated" qos=Qos0 retain=Never ttl=3600
            --stream-dest path="my/storage/path"

        - name: Update a custom asset's custom attributes
          text: >
            az iot ops ns asset custom update --name mycustomasset --instance myInstance -g myInstanceResourceGroup
            --attribute location=building2 floor=3 zone=production
    """

    helps[
        "iot ops ns asset custom dataset"
    ] = """
        type: group
        short-summary: Manage datasets for custom namespaced assets in an IoT Operations instance.
    """

    helps[
        "iot ops ns asset custom dataset add"
    ] = """
        type: command
        short-summary: Add a dataset to a custom namespaced asset in an IoT Operations instance.

        examples:
        - name: Add a basic custom dataset
          text: >
            az iot ops ns asset custom dataset add --asset mycustomasset --instance myInstance
            -g myInstanceResourceGroup --name myDataset --data-source "customDataSource"

        - name: Add a custom dataset with configuration
          text: >
            az iot ops ns asset custom dataset add --asset mycustomasset --instance myInstance
            -g myInstanceResourceGroup --name myDataset --data-source "sensor/pressure"
            --config "{\\\"publishingInterval\\\": 1000, \\\"queueSize\\\": 5}"

        - name: Add a custom dataset with MQTT destination
          text: >
            az iot ops ns asset custom dataset add --asset mycustomasset --instance myInstance
            -g myInstanceResourceGroup --name myDataset --data-source "sensor/temp"
            --destination topic="factory/temperature" retain=Keep qos=Qos1 ttl=3600

        - name: Add a custom dataset with BrokerStateStore destination
          text: >
            az iot ops ns asset custom dataset add --asset mycustomasset --instance myInstance
            -g myInstanceResourceGroup --name myDataset --data-source "device/state"
            --destination key="deviceState"

        - name: Add a custom dataset with Storage destination
          text: >
            az iot ops ns asset custom dataset add --asset mycustomasset --instance myInstance
            -g myInstanceResourceGroup --name myDataset --data-source "device/logs"
            --destination path="data/logs/device001"
    """

    helps[
        "iot ops ns asset custom dataset list"
    ] = """
        type: command
        short-summary: List datasets for a custom namespaced asset in an IoT Operations instance.

        examples:
        - name: List all datasets for a custom asset
          text: >
            az iot ops ns asset custom dataset list --asset mycustomasset --instance myInstance
            -g myInstanceResourceGroup
    """

    helps[
        "iot ops ns asset custom dataset remove"
    ] = """
        type: command
        short-summary: Remove a dataset from a custom namespaced asset in an IoT Operations instance.

        examples:
        - name: Remove a dataset from a custom asset
          text: >
            az iot ops ns asset custom dataset remove --asset mycustomasset --instance myInstance
            -g myInstanceResourceGroup --name myDataset
    """

    helps[
        "iot ops ns asset custom dataset show"
    ] = """
        type: command
        short-summary: Show details of a dataset for a custom namespaced asset in an IoT Operations instance.

        examples:
        - name: Show dataset details
          text: >
            az iot ops ns asset custom dataset show --asset mycustomasset --instance myInstance
            -g myInstanceResourceGroup --name myDataset
    """

    helps[
        "iot ops ns asset custom dataset update"
    ] = """
        type: command
        short-summary: Update a dataset for a custom namespaced asset in an IoT Operations instance.

        examples:
        - name: Update dataset configuration
          text: >
            az iot ops ns asset custom dataset update --asset mycustomasset --instance myInstance
            -g myInstanceResourceGroup --name myDataset --data-source "updated/source"
            --config "{\\\"publishingInterval\\\": 2000}"

        - name: Update dataset destination to MQTT
          text: >
            az iot ops ns asset custom dataset update --asset mycustomasset --instance myInstance
            -g myInstanceResourceGroup --name myDataset
            --destination topic="factory/updated/temperature" retain=Never qos=Qos0 ttl=7200
    """

    helps[
        "iot ops ns asset custom datapoint"
    ] = """
        type: group
        short-summary: Manage datapoints for custom asset datasets in Device Registry namespaces.
    """

    helps[
        "iot ops ns asset custom datapoint add"
    ] = """
        type: command
        short-summary: Add a datapoint to a custom asset dataset in a Device Registry namespace.

        examples:
        - name: Add a basic datapoint
          text: >
            az iot ops ns asset custom datapoint add --asset mycustomasset --instance myInstance
            -g myInstanceResourceGroup --dataset myDataset --name temp1 --data-source "sensor.temp1"

        - name: Add a datapoint with custom configuration
          text: >
            az iot ops ns asset custom datapoint add --asset mycustomasset --instance myInstance
            -g myInstanceResourceGroup --dataset myDataset --name pressure1 --data-source "sensor.pressure1"
            --config "{\\\"samplingInterval\\\": 500, \\\"priority\\\": \\\"high\\\"}"

        - name: Add a datapoint and replace existing one with same name
          text: >
            az iot ops ns asset custom datapoint add --asset mycustomasset --instance myInstance
            -g myInstanceResourceGroup --dataset myDataset --name temp1 --data-source "sensor.temp1.v2"
            --replace
    """

    helps[
        "iot ops ns asset custom datapoint list"
    ] = """
        type: command
        short-summary: List data points for a custom asset dataset in a Device Registry namespace.

        examples:
        - name: List all data points for a dataset
          text: >
            az iot ops ns asset custom datapoint list --asset mycustomasset --instance myInstance
            -g myInstanceResourceGroup --dataset myDataset
    """

    helps[
        "iot ops ns asset custom datapoint remove"
    ] = """
        type: command
        short-summary: Remove a datapoint from a custom asset dataset in a Device Registry namespace.

        examples:
        - name: Remove a datapoint from a dataset
          text: >
            az iot ops ns asset custom datapoint remove --asset mycustomasset --instance myInstance
            -g myInstanceResourceGroup --dataset myDataset --name temp1
    """

    helps[
        "iot ops ns asset custom event-group"
    ] = """
        type: group
        short-summary: Manage event groups for custom namespaced assets in an IoT Operations instance.
    """

    helps[
        "iot ops ns asset custom event-group add"
    ] = """
        type: command
        short-summary: Add an event group to a custom namespaced asset in an IoT Operations instance.

        examples:
        - name: Add a basic custom event group
          text: >
            az iot ops ns asset custom event-group add --asset mycustomasset --instance myInstance
            -g myInstanceResourceGroup --name alarmEvent --data-source "alarm.critical"

        - name: Add a custom event group with MQTT destination
          text: >
            az iot ops ns asset custom event-group add --asset mycustomasset --instance myInstance
            -g myInstanceResourceGroup --name statusEvent --data-source "status.change"
            --destination topic="factory/custom/events" retain=Never qos=Qos1 ttl=1800

        - name: Replace a custom event group with same name
          text: >
            az iot ops ns asset custom event-group add --asset mycustomasset --instance myInstance
            -g myInstanceResourceGroup --name alarmEvent --data-source "alarm.updated"
            --replace
    """

    helps[
        "iot ops ns asset custom event-group list"
    ] = """
        type: command
        short-summary: List event groups for a custom namespaced asset in an IoT Operations instance.

        examples:
        - name: List all event groups for a custom asset
          text: >
            az iot ops ns asset custom event-group list --asset mycustomasset --instance myInstance
            -g myInstanceResourceGroup
    """

    helps[
        "iot ops ns asset custom event-group remove"
    ] = """
        type: command
        short-summary: Remove an event group from a custom namespaced asset in an IoT Operations instance.

        examples:
        - name: Remove an event group from a custom asset
          text: >
            az iot ops ns asset custom event-group remove --asset mycustomasset --instance myInstance
            -g myInstanceResourceGroup --name alarmEvent
    """

    helps[
        "iot ops ns asset custom event-group show"
    ] = """
        type: command
        short-summary: Show details of an event group for a custom namespaced asset in an IoT Operations instance.

        examples:
        - name: Show event group details
          text: >
            az iot ops ns asset custom event-group show --asset mycustomasset --instance myInstance
            -g myInstanceResourceGroup --name alarmEvent
    """

    helps[
        "iot ops ns asset custom event-group update"
    ] = """
        type: command
        short-summary: Update an event group for a custom namespaced asset in an IoT Operations instance.

        examples:
        - name: Update the data source for an event group
          text: >
            az iot ops ns asset custom event-group update --asset mycustomasset --instance myInstance
            -g myInstanceResourceGroup --name alarmEvent --data-source "alarm.updated"

        - name: Update event group destination
          text: >
            az iot ops ns asset custom event-group update --asset mycustomasset --instance myInstance
            -g myInstanceResourceGroup --name temperatureAlert
            --destination topic="factory/custom/alerts/updated" retain=Keep qos=Qos0 ttl=3600
    """

    helps[
        "iot ops ns asset custom event"
    ] = """
        type: group
        short-summary: Manage events for custom asset event groups in Device Registry namespaces.
    """

    helps[
        "iot ops ns asset custom event add"
    ] = """
        type: command
        short-summary: Add an event to a custom asset event group in a Device Registry namespace.

        examples:
        - name: Add a basic custom event
          text: >
            az iot ops ns asset custom event add --asset mycustomasset --instance myInstance
            -g myInstanceResourceGroup --event-group alarmGroup --name severity --data-source "alarm.severity"

        - name: Replace a custom event with same name
          text: >
            az iot ops ns asset custom event add --asset mycustomasset --instance myInstance
            -g myInstanceResourceGroup --event-group alarmGroup --name severity --data-source "alarm.severity.updated"
            --replace
    """

    helps[
        "iot ops ns asset custom event list"
    ] = """
        type: command
        short-summary: List events for a custom asset event group in a Device Registry namespace.

        examples:
        - name: List all events for an event group
          text: >
            az iot ops ns asset custom event list --asset mycustomasset --instance myInstance
            -g myInstanceResourceGroup --event-group alarmGroup
    """

    helps[
        "iot ops ns asset custom event remove"
    ] = """
        type: command
        short-summary: Remove an events from a custom asset event group in a Device Registry namespace.

        examples:
        - name: Remove an event from an event group
          text: >
            az iot ops ns asset custom event remove --asset mycustomasset --instance myInstance
            -g myInstanceResourceGroup --event-group alarmGroup --name severity
    """

    helps[
        "iot ops ns asset custom stream"
    ] = """
        type: group
        short-summary: Manage streams for custom namespaced assets in an IoT Operations instance.
        long-summary: |
          Streams define how data flows from custom assets to destinations. Custom streams
          allow flexible configuration for various data streaming scenarios.
    """

    helps[
        "iot ops ns asset custom stream add"
    ] = """
        type: command
        short-summary: Add a stream to a custom asset.

        examples:
        - name: Add a basic custom stream to an asset.
          text: >
            az iot ops ns asset custom stream add --asset myasset --instance myInstance -g myInstanceResourceGroup
            --name myStream --config '{"streamType": "sensor-data", "frequency": "1000ms"}'

        - name: Add a custom stream with MQTT destinations.
          text: >
            az iot ops ns asset custom stream add --asset myasset --instance myInstance -g myInstanceResourceGroup
            --name myStream --config '{"streamType": "telemetry", "bufferSize": 1024}'
            --destination topic=/factory/streams/data retain=Keep qos=Qos1

        - name: Replace an existing custom stream with the same name.
          text: >
            az iot ops ns asset custom stream add --asset myasset --instance myInstance -g myInstanceResourceGroup
            --name myStream --config '{"streamType": "updated-config", "version": "2.0"}' --replace
    """

    helps[
        "iot ops ns asset custom stream list"
    ] = """
        type: command
        short-summary: List streams in a custom asset.

        examples:
        - name: List all streams in a custom asset.
          text: >
            az iot ops ns asset custom stream list --asset myasset --instance myInstance -g myInstanceResourceGroup
    """

    helps[
        "iot ops ns asset custom stream show"
    ] = """
        type: command
        short-summary: Show details of a stream in a custom asset.

        examples:
        - name: Show details of a specific stream.
          text: >
            az iot ops ns asset custom stream show --asset myasset --instance myInstance -g myInstanceResourceGroup
            --name myStream
    """

    helps[
        "iot ops ns asset custom stream update"
    ] = """
        type: command
        short-summary: Update a stream in a custom asset.

        examples:
        - name: Update the custom configuration of a stream.
          text: >
            az iot ops ns asset custom stream update --asset myasset --instance myInstance -g myInstanceResourceGroup
            --name myStream --config '{"streamType": "updated-sensor-data", "frequency": "500ms"}'

        - name: Update both configuration and destinations.
          text: >
            az iot ops ns asset custom stream update --asset myasset --instance myInstance -g myInstanceResourceGroup
            --name myStream --config '{"streamType": "hybrid-data", "compression": true}'
            --destination path=/compressed/data
    """

    helps[
        "iot ops ns asset custom stream remove"
    ] = """
        type: command
        short-summary: Remove a stream from a custom asset.

        examples:
        - name: Remove a stream from a custom asset.
          text: >
            az iot ops ns asset custom stream remove --asset myasset --instance myInstance -g myInstanceResourceGroup
            --name myStream
    """

    helps[
        "iot ops ns asset custom mgmt-group"
    ] = """
        type: group
        short-summary: Manage custom asset management groups in an IoT Operations instance.
    """

    helps[
        "iot ops ns asset custom mgmt-group add"
    ] = """
        type: command
        short-summary: Add a management group to a custom asset.

        examples:
        - name: Add a basic management group to a custom asset.
          text: >
            az iot ops ns asset custom mgmt-group add --asset myasset --instance myInstance -g myInstanceResourceGroup
            --name myManagementGroup --data-source mydatasource

        - name: Add a management group with default topic and timeout.
          text: >
            az iot ops ns asset custom mgmt-group add --asset myasset --instance myInstance -g myInstanceResourceGroup
            --name myManagementGroup --default-topic factory/management/responses --default-timeout 30
            --data-source mydatasource

        - name: Add a management group with custom configuration.
          text: >
            az iot ops ns asset custom mgmt-group add --asset myasset --instance myInstance -g myInstanceResourceGroup
            --name myManagementGroup --config '{"groupType": "sensor-control", "priority": "high"}'
            --default-topic factory/control/commands --default-timeout 60 --data-source mydatasource

        - name: Replace an existing management group with the same name.
          text: >
            az iot ops ns asset custom mgmt-group add --asset myasset --instance myInstance -g myInstanceResourceGroup
            --name myManagementGroup --config '{"groupType": "updated-control", "version": "2.0"}'
            --data-source mydatasource --replace
    """

    helps[
        "iot ops ns asset custom mgmt-group list"
    ] = """
        type: command
        short-summary: List management groups for a custom asset.

        examples:
        - name: List all management groups for a custom asset.
          text: >
            az iot ops ns asset custom mgmt-group list --asset myasset --instance myInstance -g myInstanceResourceGroup
    """

    helps[
        "iot ops ns asset custom mgmt-group show"
    ] = """
        type: command
        short-summary: Show details of a management group for a custom asset.

        examples:
        - name: Show details of a specific management group.
          text: >
            az iot ops ns asset custom mgmt-group show --asset myasset --instance myInstance -g myInstanceResourceGroup
            --name myManagementGroup
    """

    helps[
        "iot ops ns asset custom mgmt-group update"
    ] = """
        type: command
        short-summary: Update a management group for a custom asset.

        examples:
        - name: Update the default topic and timeout for a management group.
          text: >
            az iot ops ns asset custom mgmt-group update --asset myasset --instance myInstance -g myInstanceResourceGroup
            --name myManagementGroup --default-topic factory/updated/responses --default-timeout 45

        - name: Update the custom configuration and data source for a management group.
          text: >
            az iot ops ns asset custom mgmt-group update --asset myasset --instance myInstance -g myInstanceResourceGroup
            --name myManagementGroup --config '{"groupType": "advanced-control", "features": ["logging", "retry"]}'
            --data-source mydatasource

        - name: Clear the custom configuration for a management group.
          text: >
            az iot ops ns asset custom mgmt-group update --asset myasset --instance myInstance -g myInstanceResourceGroup
            --name myManagementGroup --config ""
    """

    helps[
        "iot ops ns asset custom mgmt-group remove"
    ] = """
        type: command
        short-summary: Remove a management group from a custom asset.

        examples:
        - name: Remove a management group from a custom asset.
          text: >
            az iot ops ns asset custom mgmt-group remove --asset myasset --instance myInstance -g myInstanceResourceGroup
            --name myManagementGroup
    """

    helps[
        "iot ops ns asset custom mgmt-action"
    ] = """
        type: group
        short-summary: Manage actions within custom asset management groups.
        long-summary: |
          Actions within management groups define specific operations that can be performed on custom assets.
          Each action has a target URI and can include custom configuration.
    """

    helps[
        "iot ops ns asset custom mgmt-action add"
    ] = """
        type: command
        short-summary: Add an action to a custom asset management group.

        examples:
        - name: Add a basic action to a management group.
          text: >
            az iot ops ns asset custom mgmt-action add --asset myasset --instance myInstance -g myInstanceResourceGroup
            --group myManagementGroup --name myAction --target-uri /custom/device_service?Profile=Profile1

        - name: Add an action with custom configuration and timeout.
          text: >
            az iot ops ns asset custom mgmt-action add --asset myasset --instance myInstance -g myInstanceResourceGroup
            --group myManagementGroup --name myAction --target-uri /custom/device_service?Profile=Profile1
            --config '{"method": "start", "parameters": {"speed": 100}}'
            --timeout 45

        - name: Add an action with specific action type and topic.
          text: >
            az iot ops ns asset custom mgmt-action add --asset myasset --instance myInstance -g myInstanceResourceGroup
            --group myManagementGroup --name myAction --target-uri /custom/device_service?Profile=Profile1
            --action-type Control --topic factory/control/actions --timeout 30

        - name: Replace an existing action with the same name.
          text: >
            az iot ops ns asset custom mgmt-action add --asset myasset --instance myInstance -g myInstanceResourceGroup
            --group myManagementGroup --name myAction --target-uri /custom/device_service?Profile=Profile2
            --config '{"method": "restart", "priority": "high"}' --replace
    """

    helps[
        "iot ops ns asset custom mgmt-action list"
    ] = """
        type: command
        short-summary: List actions in a custom asset management group.

        examples:
        - name: List all actions in a management group.
          text: >
            az iot ops ns asset custom mgmt-action list --asset myasset --instance myInstance -g myInstanceResourceGroup
            --group myManagementGroup
    """

    helps[
        "iot ops ns asset custom mgmt-action remove"
    ] = """
        type: command
        short-summary: Remove an action from a custom asset management group.

        examples:
        - name: Remove an action from a management group.
          text: >
            az iot ops ns asset custom mgmt-action remove --asset myasset --instance myInstance -g myInstanceResourceGroup
            --group myManagementGroup --name myAction
    """

    helps[
        "iot ops ns asset media"
    ] = """
        type: group
        short-summary: Manage namespaced assets that point to media device endpoints.
        long-summary: For more information on media connectors, please see https://aka.ms/aio-media-quickstart
    """

    helps[
        "iot ops ns asset media create"
    ] = """
        type: command
        short-summary: Create a media namespaced asset in an IoT Operations instance.
        long-summary: The device endpoint must be of type Microsoft.Media.

        examples:
        - name: Create a basic media asset
          text: >
            az iot ops ns asset media create --name mymediaasset --instance myInstance -g myInstanceResourceGroup
            --device myCamera --endpoint myCameraEndpoint

        - name: Create a media asset for MQTT snapshots with an MQTT destination
          text: >
            az iot ops ns asset media create --name mymediaasset --instance myInstance -g myInstanceResourceGroup
            --device myCamera --endpoint myCameraEndpoint --task-type snapshot-to-mqtt
            --task-format jpeg --snapshots-per-sec 1
            --stream-dest topic="factory/cameras/snapshots" qos=Qos1 retain=Never ttl=60

        - name: Create a media asset for file system snapshots
          text: >
            az iot ops ns asset media create --name mymediaasset --instance myInstance -g myInstanceResourceGroup
            --device myCamera --endpoint myCameraEndpoint --task-type snapshot-to-fs
            --task-format png --snapshots-per-sec 5 --path "/data/snapshots"

        - name: Create a media asset for file system clips
          text: >
            az iot ops ns asset media create --name mymediaasset --instance myInstance -g myInstanceResourceGroup
            --device myCamera --endpoint myCameraEndpoint --task-type clip-to-fs
            --task-format mp4 --duration 300 --path "/data/clips"

        - name: Create a media asset for RTSP streaming
          text: >
            az iot ops ns asset media create --name mymediaasset --instance myInstance -g myInstanceResourceGroup
            --device myCamera --endpoint myCameraEndpoint --task-type stream-to-rtsp
            --media-server-address "media-server.media-server.svc.cluster.local"
            --media-server-port 8554 --media-server-path "myCamera/stream"
    """

    helps[
        "iot ops ns asset media update"
    ] = """
        type: command
        short-summary: Update a media namespaced asset in an IoT Operations instance.
        long-summary: The device endpoint must be of type Microsoft.Media.

        examples:
        - name: Update a media asset's basic properties
          text: >
            az iot ops ns asset media update --name mymediaasset --instance myInstance -g myInstanceResourceGroup
            --description "Updated surveillance camera" --display-name "Entry Camera HD"

        - name: Change a media asset from MQTT snapshots to file system snapshots
          text: >
            az iot ops ns asset media update --name mymediaasset --instance myInstance -g myInstanceResourceGroup
            --task-type snapshot-to-fs --task-format png --path "/data/snapshots/hd"

        - name: Update a media asset's clip configuration
          text: >
            az iot ops ns asset media update --name mymediaasset --instance myInstance -g myInstanceResourceGroup
            --task-type clip-to-fs --duration 600 --path "/data/clips/extended"

        - name: Update a media asset's RTSP streaming configuration
          text: >
            az iot ops ns asset media update --name mymediaasset --instance myInstance -g myInstanceResourceGroup
            --task-type stream-to-rtsp --media-server-address "new-media-server.local"
            --media-server-port 8555 --media-server-path "cameras/main/stream"

        - name: Update a media asset's destination and metadata
          text: >
            az iot ops ns asset media update --name mymediaasset --instance myInstance -g myInstanceResourceGroup
            --stream-dest topic="security/cameras/main" qos=Qos1 retain=Never ttl=300
            --manufacturer "SecureCam Inc." --model "HD-8000" --serial-number "CAM9876"
    """

    helps[
        "iot ops ns asset media stream"
    ] = """
        type: group
        short-summary: Manage streams for media namespaced assets in an IoT Operations instance.
    """

    helps[
        "iot ops ns asset media stream add"
    ] = """
        type: command
        short-summary: Add a stream to a media asset.

        examples:
        - name: Add a snapshot-to-mqtt stream with default settings.
          text: >
            az iot ops ns asset media stream add --asset mymediaasset --instance myInstance -g myInstanceResourceGroup
            --name snapshotStream --task-type snapshot-to-mqtt

        - name: Add a snapshot-to-mqtt stream with custom format and rate.
          text: >
            az iot ops ns asset media stream add --asset mymediaasset --instance myInstance -g myInstanceResourceGroup
            --name snapshotStream --task-type snapshot-to-mqtt --format png --snapshots-per-sec 2 --disable-autostart

        - name: Add a snapshot-to-fs stream for saving images to file system.
          text: >
            az iot ops ns asset media stream add --asset mymediaasset --instance myInstance -g myInstanceResourceGroup
            --name fileSnapshotStream --task-type snapshot-to-fs --format jpeg --path /media/snapshots
            --snapshots-per-sec 1

        - name: Add a clip-to-fs stream for recording video clips.
          text: >
            az iot ops ns asset media stream add --asset mymediaasset --instance myInstance -g myInstanceResourceGroup
            --name clipStream --task-type clip-to-fs --format mp4 --duration 30 --path /media/clips

        - name: Add a stream-to-rtsp stream for real-time streaming.
          text: >
            az iot ops ns asset media stream add --asset mymediaasset --instance myInstance -g myInstanceResourceGroup
            --name rtspStream --task-type stream-to-rtsp --media-server-address 192.168.1.100 --media-server-port 554
            --media-server-path /live/stream1 --media-server-user streamuser --media-server-pass streampass

        - name: Add a secure stream-to-rtsps stream with certificate.
          text: >
            az iot ops ns asset media stream add --asset mymediaasset --instance myInstance -g myInstanceResourceGroup
            --name secureRtspStream --task-type stream-to-rtsps --media-server-address secure.example.com
            --media-server-port 322 --media-server-path /secure/stream --media-server-cert /path/to/cert.pem

        - name: Add a media stream with a MQTT destination.
          text: >
            az iot ops ns asset media stream add --asset mymediaasset --instance myInstance -g myInstanceResourceGroup
            --name streamWithDest --task-type snapshot-to-mqtt --format jpeg
            --destination topic=/media/snapshots retain=Keep qos=Qos1 ttl=3600

        - name: Replace an existing media stream with new configuration.
          text: >
            az iot ops ns asset media stream add --asset mymediaasset --instance myInstance -g myInstanceResourceGroup
            --name snapshotStream --task-type snapshot-to-mqtt --format bmp --snapshots-per-sec 5 --replace
    """

    helps[
        "iot ops ns asset media stream list"
    ] = """
        type: command
        short-summary: List streams in a media asset.

        examples:
        - name: List all streams in a media asset.
          text: >
            az iot ops ns asset media stream list --asset mymediaasset --instance myInstance -g myInstanceResourceGroup
    """

    helps[
        "iot ops ns asset media stream show"
    ] = """
        type: command
        short-summary: Show details of a stream in a media asset.

        examples:
        - name: Show details of a specific media stream.
          text: >
            az iot ops ns asset media stream show --asset mymediaasset --instance myInstance -g myInstanceResourceGroup
            --name snapshotStream
    """

    helps[
        "iot ops ns asset media stream update"
    ] = """
        type: command
        short-summary: Update a stream in a media asset.

        examples:
        - name: Update the format and rate of a snapshot stream.
          text: >
            az iot ops ns asset media stream update --asset mymediaasset --instance myInstance -g myInstanceResourceGroup
            --name snapshotStream --format png --snapshots-per-sec 3

        - name: Update the path for a file-based stream.
          text: >
            az iot ops ns asset media stream update --asset mymediaasset --instance myInstance -g myInstanceResourceGroup
            --name fileStream --path /updated/media/path

        - name: Update server configuration for an RTSP stream.
          text: >
            az iot ops ns asset media stream update --asset mymediaasset --instance myInstance -g myInstanceResourceGroup
            --name rtspStream --media-server-address 192.168.1.200 --media-server-port 8554

        - name: Update destinations for a media stream and disable autostart.
          text: >
            az iot ops ns asset media stream update --asset mymediaasset --instance myInstance -g myInstanceResourceGroup
            --name snapshotStream --destination path=/new/snapshot/path --disable-autostart

        - name: Update clip duration and format.
          text: >
            az iot ops ns asset media stream update --asset mymediaasset --instance myInstance -g myInstanceResourceGroup
            --name clipStream --duration 60 --format avi

        - name: Update secure RTSP stream credentials.
          text: >
            az iot ops ns asset media stream update --asset mymediaasset --instance myInstance -g myInstanceResourceGroup
            --name secureStream --media-server-cert /new/path/to/cert.pem
    """

    helps[
        "iot ops ns asset media stream remove"
    ] = """
        type: command
        short-summary: Remove a stream from a media asset.

        examples:
        - name: Remove a stream from a media asset.
          text: >
            az iot ops ns asset media stream remove --asset mymediaasset --instance myInstance -g myInstanceResourceGroup
            --name snapshotStream
    """

    helps[
        "iot ops ns asset onvif"
    ] = """
        type: group
        short-summary: Manage namespaced assets that point to ONVIF device endpoints.
        long-summary: For more information on ONVIF connectors, please see https://aka.ms/aio-onvif-quickstart
    """

    helps[
        "iot ops ns asset onvif create"
    ] = """
        type: command
        short-summary: Create an ONVIF namespaced asset in an IoT Operations instance.
        long-summary: The device endpoint must be of type Microsoft.Onvif.

        examples:
        - name: Create a basic ONVIF asset
          text: >
            az iot ops ns asset onvif create --name myonvifasset --instance myInstance -g myInstanceResourceGroup
            --device myCamera --endpoint myOnvifEndpoint

        - name: Create an ONVIF asset with additional metadata
          text: >
            az iot ops ns asset onvif create --name myonvifasset --instance myInstance -g myInstanceResourceGroup
            --device myCamera --endpoint myOnvifEndpoint --description "Surveillance Camera"
            --display-name "Entry Camera" --model "SecureCam Pro" --manufacturer "SecurityCo"
            --serial-number "CAM-12345" --documentation-uri "https://example.com/docs/camera"

        - name: Create an ONVIF asset with custom attributes
          text: >
            az iot ops ns asset onvif create --name myonvifasset --instance myInstance -g myInstanceResourceGroup
            --device myCamera --endpoint myOnvifEndpoint --attribute location=entrance
            --attribute resolution=1080p --attribute ptz=true
    """

    helps[
        "iot ops ns asset onvif update"
    ] = """
        type: command
        short-summary: Update an ONVIF namespaced asset in an IoT Operations instance.
        long-summary: The device endpoint must be of type Microsoft.Onvif.

        examples:
        - name: Update an ONVIF asset's basic properties
          text: >
            az iot ops ns asset onvif update --name myonvifasset --instance myInstance -g myInstanceResourceGroup
            --description "Updated surveillance camera" --display-name "Main Entrance Camera"

        - name: Update an ONVIF asset's metadata
          text: >
            az iot ops ns asset onvif update --name myonvifasset --instance myInstance -g myInstanceResourceGroup
            --model "SecureCam Pro X1" --manufacturer "SecurityCo" --serial-number "CAM-67890"
            --documentation-uri "https://example.com/docs/camera/v2"

        - name: Update an ONVIF asset's custom attributes
          text: >
            az iot ops ns asset onvif update --name myonvifasset --instance myInstance -g myInstanceResourceGroup
            --attribute location=main-entrance resolution=4K ptz=true night-vision=true

        - name: Disable an ONVIF asset and update its reference information
          text: >
            az iot ops ns asset onvif update --name myonvifasset --instance myInstance -g myInstanceResourceGroup
            --disable --external-asset-id "CAM-MAIN-01" --hardware-revision "v2.1"
    """

    helps[
        "iot ops ns asset onvif event-group"
    ] = """
        type: group
        short-summary: Manage event groups for ONVIF namespaced assets in an IoT Operations instance.
    """

    helps[
        "iot ops ns asset onvif event-group add"
    ] = """
        type: command
        short-summary: Add an event group to an ONVIF namespaced asset in an IoT Operations instance.

        examples:
        - name: Add a basic ONVIF event group
          text: >
            az iot ops ns asset onvif event-group add --asset myonvifasset --instance myInstance
            -g myInstanceResourceGroup --name motionEvent --data-source "motion.detection"

        - name: Add an ONVIF event group with MQTT destination
          text: >
            az iot ops ns asset onvif event-group add --asset myonvifasset --instance myInstance
            -g myInstanceResourceGroup --name lineDetection --data-source "line.crossing"
            --destination topic="factory/onvif/events" retain=Never qos=Qos1 ttl=1800

        - name: Repalce an ONVIF event group with same name
          text: >
            az iot ops ns asset onvif event-group add --asset myonvifasset --instance myInstance
            -g myInstanceResourceGroup --name motionEvent --data-source "motion.detection.updated"
            --replace
    """

    helps[
        "iot ops ns asset onvif event-group list"
    ] = """
        type: command
        short-summary: List event groups for an ONVIF namespaced asset in an IoT Operations instance.

        examples:
        - name: List all event groups for an ONVIF asset
          text: >
            az iot ops ns asset onvif event-group list --asset myonvifasset --instance myInstance
            -g myInstanceResourceGroup
    """

    helps[
        "iot ops ns asset onvif event-group remove"
    ] = """
        type: command
        short-summary: Remove an event group from an ONVIF namespaced asset in an IoT Operations instance.

        examples:
        - name: Remove an event group from an ONVIF asset
          text: >
            az iot ops ns asset onvif event-group remove --asset myonvifasset --instance myInstance
            -g myInstanceResourceGroup --name motionEvent
    """

    helps[
        "iot ops ns asset onvif event-group show"
    ] = """
        type: command
        short-summary: Show details of an event group for an ONVIF namespaced asset in an IoT Operations instance.

        examples:
        - name: Show event group details
          text: >
            az iot ops ns asset onvif event-group show --asset myonvifasset --instance myInstance
            -g myInstanceResourceGroup --name motionEvent
    """

    helps[
        "iot ops ns asset onvif event-group update"
    ] = """
        type: command
        short-summary: Update an event group for an ONVIF namespaced asset in an IoT Operations instance.

        examples:
        - name: Update event notifier
          text: >
            az iot ops ns asset onvif event-group update --asset myonvifasset --instance myInstance
            -g myInstanceResourceGroup --name motionEvent --data-source "motion.detection.enhanced"

        - name: Update event group destination
          text: >
            az iot ops ns asset onvif event-group update --asset myonvifasset --instance myInstance
            -g myInstanceResourceGroup --name lineDetection
            --destination topic="factory/onvif/security/updated" retain=Keep qos=Qos0 ttl=3600
    """

    helps[
        "iot ops ns asset onvif event"
    ] = """
        type: group
        short-summary: Manage individual events for ONVIF asset event groups in Device Registry namespaces.
    """

    helps[
        "iot ops ns asset onvif event add"
    ] = """
        type: command
        short-summary: Add an event to an ONVIF asset event group in a Device Registry namespace.

        examples:
        - name: Add a basic ONVIF event
          text: >
            az iot ops ns asset onvif event add --asset myonvifasset --instance myInstance
            -g myInstanceResourceGroup --event-group motionEvents --name motion --data-source "camera.motion"

        - name: Add an ONVIF event with MQTT destination
          text: >
            az iot ops ns asset onvif event add --asset myonvifasset --instance myInstance
            -g myInstanceResourceGroup --event-group motionEvents --name intrusion --data-source "camera.intrusion"
            --dest topic="factory/onvif/events" retain=Keep qos=Qos1 ttl=3600

        - name: Replace an ONVIF event with same name (all properties must be re-specified)
          text: >
            az iot ops ns asset onvif event add --asset myonvifasset --instance myInstance
            -g myInstanceResourceGroup --event-group motionEvents --name intrusion --data-source "camera.intrusion.v2"
            --dest topic="factory/onvif/events" retain=Keep qos=Qos1 ttl=3600 --replace
    """

    helps[
        "iot ops ns asset onvif event list"
    ] = """
        type: command
        short-summary: List events for an ONVIF asset event group in a Device Registry namespace.

        examples:
        - name: List all events for an event group
          text: >
            az iot ops ns asset onvif event list --asset myonvifasset --instance myInstance
            -g myInstanceResourceGroup --event-group motionEvents
    """

    helps[
        "iot ops ns asset onvif event remove"
    ] = """
        type: command
        short-summary: Remove an event from an ONVIF asset event group in a Device Registry namespace.

        examples:
        - name: Remove an event from an event group
          text: >
            az iot ops ns asset onvif event remove --asset myonvifasset --instance myInstance
            -g myInstanceResourceGroup --event-group motionEvents --name motion
    """

    helps[
        "iot ops ns asset onvif mgmt-group"
    ] = """
        type: group
        short-summary: Manage ONVIF asset management groups in an IoT Operations instance.
        long-summary: |
          Management groups define collections of management actions that can be performed on ONVIF assets.
          Each management group contains actions with specific configurations and targets.
    """

    helps[
        "iot ops ns asset onvif mgmt-group add"
    ] = """
        type: command
        short-summary: Add a management group to an ONVIF asset.

        examples:
        - name: Add a basic management group to an ONVIF asset.
          text: >
            az iot ops ns asset onvif mgmt-group add --asset myonvifasset --instance myInstance -g myInstanceResourceGroup
            --name myManagementGroup --data-source mydatasource

        - name: Add a management group with default topic and timeout.
          text: >
            az iot ops ns asset onvif mgmt-group add --asset myonvifasset --instance myInstance -g myInstanceResourceGroup
            --name myManagementGroup --default-topic factory/onvif/management/responses --default-timeout 30
            --data-source mydatasource

        - name: Replace an existing management group with the same name.
          text: >
            az iot ops ns asset onvif mgmt-group add --asset myonvifasset --instance myInstance -g myInstanceResourceGroup
            --name myManagementGroup --default-topic factory/onvif/control/commands --default-timeout 60
            --data-source mydatasource --replace
    """

    helps[
        "iot ops ns asset onvif mgmt-group list"
    ] = """
        type: command
        short-summary: List management groups for an ONVIF asset.

        examples:
        - name: List all management groups for an ONVIF asset.
          text: >
            az iot ops ns asset onvif mgmt-group list --asset myonvifasset --instance myInstance -g myInstanceResourceGroup
    """

    helps[
        "iot ops ns asset onvif mgmt-group show"
    ] = """
        type: command
        short-summary: Show details of a management group for an ONVIF asset.

        examples:
        - name: Show details of a specific management group.
          text: >
            az iot ops ns asset onvif mgmt-group show --asset myonvifasset --instance myInstance -g myInstanceResourceGroup
            --name myManagementGroup
    """

    helps[
        "iot ops ns asset onvif mgmt-group update"
    ] = """
        type: command
        short-summary: Update a management group for an ONVIF asset.

        examples:
        - name: Update the default topic and timeout for a management group.
          text: >
            az iot ops ns asset onvif mgmt-group update --asset myonvifasset --instance myInstance -g myInstanceResourceGroup
            --name myManagementGroup --default-topic factory/onvif/updated/responses --default-timeout 45

        - name: Update the default timeout and data source for a management group.
          text: >
            az iot ops ns asset onvif mgmt-group update --asset myonvifasset --instance myInstance -g myInstanceResourceGroup
            --name myManagementGroup --default-timeout 90 --data-source mydatasource
    """

    helps[
        "iot ops ns asset onvif mgmt-group remove"
    ] = """
        type: command
        short-summary: Remove a management group from an ONVIF asset.

        examples:
        - name: Remove a management group from an ONVIF asset.
          text: >
            az iot ops ns asset onvif mgmt-group remove --asset myonvifasset --instance myInstance -g myInstanceResourceGroup
            --name myManagementGroup
    """

    helps[
        "iot ops ns asset opcua"
    ] = """
        type: group
        short-summary: Manage namespaced assets that point to OPC UA device endpoints.
        long-summary: For more information on OPC UA connectors, please see https://aka.ms/aio-opcua-quickstart
    """

    helps[
        "iot ops ns asset opcua create"
    ] = """
        type: command
        short-summary: Create an OPC UA namespaced asset in an IoT Operations instance.
        long-summary: The device endpoint must be of type Microsoft.OpcUa.

        examples:
        - name: Create a basic OPC UA asset
          text: >
            az iot ops ns asset opcua create --name myopcuaasset --instance myInstance -g myInstanceResourceGroup
            --device myOpcuaDevice --endpoint myOpcuaEndpoint

        - name: Create an OPC UA asset with dataset configuration
          text: >
            az iot ops ns asset opcua create --name myopcuaasset --instance myInstance -g myInstanceResourceGroup
            --device myOpcuaDevice --endpoint myOpcuaEndpoint --dataset-publish-int 1000
            --dataset-sampling-int 500 --dataset-queue-size 5 --dataset-key-frame-count 1

        - name: Create an OPC UA asset with event configuration
          text: >
            az iot ops ns asset opcua create --name myopcuaasset --instance myInstance -g myInstanceResourceGroup
            --device myOpcuaDevice --endpoint myOpcuaEndpoint --event-publish-int 2000
            --event-queue-size 10

        - name: Create an OPC UA asset with MQTT destinations for datasets and events
          text: >
            az iot ops ns asset opcua create --name myopcuaasset --instance myInstance -g myInstanceResourceGroup
            --device myOpcuaDevice --endpoint myOpcuaEndpoint
            --dataset-dest topic="factory/opcua/data" retain=Keep qos=Qos1 ttl=3600
            --event-dest topic="factory/opcua/events" retain=Never qos=Qos1 ttl=3600

        - name: Create an OPC UA asset with start instances for datasets and events
          text: >
            az iot ops ns asset opcua create --name myopcuaasset --instance myInstance -g myInstanceResourceGroup
            --device myOpcuaDevice --endpoint myOpcuaEndpoint --dataset-start-inst "ns=2;i=1001"
            --event-start-inst "ns=3;i=3001"

        - name: Create an OPC UA asset with event filter configuration
          text: >
            az iot ops ns asset opcua create --name myopcuaasset --instance myInstance -g myInstanceResourceGroup
            --device myOpcuaDevice --endpoint myOpcuaEndpoint --event-filter-type "ns=2;i=5001"
            --event-filter-clause path="/EventType" type="ns=2;i=5001"
    """

    helps[
        "iot ops ns asset opcua update"
    ] = """
        type: command
        short-summary: Update an OPC UA namespaced asset in an IoT Operations instance.
        long-summary: The device endpoint must be of type Microsoft.OpcUa.

        examples:
        - name: Update an OPC UA asset's basic properties
          text: >
            az iot ops ns asset opcua update --name myopcuaasset --instance myInstance -g myInstanceResourceGroup
            --description "Updated factory PLC" --display-name "Production Line Controller"

        - name: Update an OPC UA asset's dataset configuration
          text: >
            az iot ops ns asset opcua update --name myopcuaasset --instance myInstance -g myInstanceResourceGroup
            --dataset-publish-int 500 --dataset-sampling-int 250
            --dataset-queue-size 10 --dataset-key-frame-count 2

        - name: Update an OPC UA asset's event configuration
          text: >
            az iot ops ns asset opcua update --name myopcuaasset --instance myInstance -g myInstanceResourceGroup
            --event-publish-int 1000 --event-queue-size 5

        - name: Update an OPC UA asset's destination configurations
          text: >
            az iot ops ns asset opcua update --name myopcuaasset --instance myInstance -g myInstanceResourceGroup
            --dataset-dest topic="factory/opcua/data/updated" retain=Keep qos=Qos1 ttl=7200
            --event-dest topic="factory/opcua/events/updated" retain=Never qos=Qos1 ttl=3600

        - name: Update an OPC UA asset's metadata and attributes
          text: >
            az iot ops ns asset opcua update --name myopcuaasset --instance myInstance -g myInstanceResourceGroup
            --manufacturer "Automation Corp" --model "PLC-2000" --serial-number "PLC87654"
            --attribute location=factory-floor zone="production line"

        - name: Update an OPC UA asset's start instances for datasets and events
          text: >
            az iot ops ns asset opcua update --name myopcuaasset --instance myInstance -g myInstanceResourceGroup
            --dataset-start-inst "ns=2;i=1001" --event-start-inst "ns=3;i=3001"
    """

    helps[
        "iot ops ns asset dataset"
    ] = """
        type: group
        short-summary: Manage datasets for namespaced assets in an IoT Operations instance.
        long-summary: >
            The connector type is detected automatically from the existing asset.
            For connector-specific parameters use --dataset-config (inline JSON or file).
            Use --show-template to discover the supported configuration schema for the asset's connector type.
    """

    helps[
        "iot ops ns asset dataset add"
    ] = """
        type: command
        short-summary: Add a dataset to a namespaced asset in an IoT Operations instance.
        long-summary: >
            The connector type is detected from the asset's device endpoint.
            Connector-specific configuration (publishing interval, queue size, etc.) can
            be supplied via --dataset-config. Use --show-template to discover the supported config
            schema. For non-OPC UA connectors, a connector template must exist in the instance.

        examples:
        - name: Add a basic dataset to any asset type
          text: >
            az iot ops ns asset dataset add --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name default --data-source "ns=2;s=Temperature"

        - name: Show the dataset config template for the asset's connector type
          text: >
            az iot ops ns asset dataset add --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name default --show-template config

        - name: Add a dataset with connector-specific configuration from inline JSON
          text: >
            az iot ops ns asset dataset add --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name default
            --dataset-config '{"datasetConfiguration": {"publishingInterval": 1000, "samplingInterval": 500}}'

        - name: Add a dataset with configuration from a file
          text: >
            az iot ops ns asset dataset add --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name default --dataset-config ./dataset_config.json

        - name: Add a dataset with an MQTT destination
          text: >
            az iot ops ns asset dataset add --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name default
            --dataset-config '{"destinations": [{"target": "Mqtt", "configuration": {"topic": "factory/data", "retain": "Keep", "qos": "Qos1", "ttl": 3600}}]}'

        - name: Replace an existing dataset
          text: >
            az iot ops ns asset dataset add --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name default --replace
    """

    helps[
        "iot ops ns asset dataset update"
    ] = """
        type: command
        short-summary: Update a dataset for a namespaced asset in an IoT Operations instance.
        long-summary: >
            The connector type is detected from the asset's device endpoint.
            Use --dataset-config to supply connector-specific configuration.
            Use --show-template config to see current dataset values pre-filled in the full schema
            structure (ready to edit and pass back via --dataset-config).
            Use --show-template schema to see the full connector schema with types and constraints.

        examples:
        - name: Show current dataset config pre-filled with existing values (for editing before update)
          text: >
            az iot ops ns asset dataset update --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name default --show-template config

        - name: Show the dataset config schema with types and constraints
          text: >
            az iot ops ns asset dataset update --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name default --show-template schema

        - name: Update dataset configuration from inline JSON
          text: >
            az iot ops ns asset dataset update --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name default
            --dataset-config '{"datasetConfiguration": {"publishingInterval": 2000}}'

        - name: Update dataset data source
          text: >
            az iot ops ns asset dataset update --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name default --data-source "ns=3;s=UpdatedSensor"
    """

    helps[
        "iot ops ns asset dataset list"
    ] = """
        type: command
        short-summary: List datasets for a namespaced asset in an IoT Operations instance.

        examples:
        - name: List all datasets for an asset
          text: >
            az iot ops ns asset dataset list --asset myasset --instance myInstance
            -g myInstanceResourceGroup
    """

    helps[
        "iot ops ns asset dataset remove"
    ] = """
        type: command
        short-summary: Remove a dataset from a namespaced asset in an IoT Operations instance.

        examples:
        - name: Remove a dataset from an asset
          text: >
            az iot ops ns asset dataset remove --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name default
    """

    helps[
        "iot ops ns asset dataset show"
    ] = """
        type: command
        short-summary: Show details of a dataset for a namespaced asset in an IoT Operations instance.

        examples:
        - name: Show dataset details
          text: >
            az iot ops ns asset dataset show --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name default
    """

    helps[
        "iot ops ns asset dataset export"
    ] = """
        type: command
        short-summary: Export datasets to file.

        examples:
        - name: Export datasets to JSON
          text: >
            az iot ops ns asset dataset export --asset myasset --instance myInstance
            -g myInstanceResourceGroup
    """

    helps[
        "iot ops ns asset dataset import"
    ] = """
        type: command
        short-summary: Import datasets from file.

        examples:
        - name: Import datasets from a JSON file
          text: >
            az iot ops ns asset dataset import --asset myasset --instance myInstance
            -g myInstanceResourceGroup --input-file ./datasets.json
    """

    helps[
        "iot ops ns asset datapoint"
    ] = """
        type: group
        short-summary: Manage data points for asset datasets in IoT Operations namespaces.
        long-summary: >
            The connector type is detected automatically from the existing asset.
            For connector-specific parameters use --datapoint-config (inline JSON or file).
            Use --show-template to discover the supported configuration schema for the asset's connector type.
    """

    helps[
        "iot ops ns asset datapoint add"
    ] = """
        type: command
        short-summary: Add a datapoint to an asset dataset in an IoT Operations namespace.
        long-summary: >
            The connector type is detected from the asset's device endpoint.
            Connector-specific configuration (queue size, sampling interval, etc.)
            can be supplied via --datapoint-config. Use --show-template to discover the supported
            config schema. For non-OPC UA connectors, a connector template must exist in the instance.

        examples:
        - name: Add a basic datapoint to any asset type
          text: >
            az iot ops ns asset datapoint add --asset myasset --instance myInstance
            -g myInstanceResourceGroup --dataset default --name temp1 --data-source "ns=2;s=Temp1"

        - name: Show the datapoint config template for the asset's connector type
          text: >
            az iot ops ns asset datapoint add --asset myasset --instance myInstance
            -g myInstanceResourceGroup --dataset default --name temp1 --data-source "ns=2;s=Temp1"
            --show-template config

        - name: Add a datapoint with connector-specific configuration from inline JSON
          text: >
            az iot ops ns asset datapoint add --asset myasset --instance myInstance
            -g myInstanceResourceGroup --dataset default --name temp1 --data-source "ns=2;s=Temp1"
            --datapoint-config '{"datapointConfiguration": {"samplingInterval": 1000, "queueSize": 5}}'

        - name: Add a datapoint with configuration from a file
          text: >
            az iot ops ns asset datapoint add --asset myasset --instance myInstance
            -g myInstanceResourceGroup --dataset default --name temp1 --data-source "ns=2;s=Temp1"
            --datapoint-config ./datapoint_config.json

        - name: Replace an existing datapoint
          text: >
            az iot ops ns asset datapoint add --asset myasset --instance myInstance
            -g myInstanceResourceGroup --dataset default --name temp1 --data-source "ns=3;s=NewTemp"
            --replace
    """

    helps[
        "iot ops ns asset datapoint list"
    ] = """
        type: command
        short-summary: List data points for an asset dataset in an IoT Operations namespace.

        examples:
        - name: List all data points for a dataset
          text: >
            az iot ops ns asset datapoint list --asset myasset --instance myInstance
            -g myInstanceResourceGroup --dataset default
    """

    helps[
        "iot ops ns asset datapoint remove"
    ] = """
        type: command
        short-summary: Remove a datapoint from an asset dataset in an IoT Operations namespace.

        examples:
        - name: Remove a datapoint from a dataset
          text: >
            az iot ops ns asset datapoint remove --asset myasset --instance myInstance
            -g myInstanceResourceGroup --dataset default --name temp1
    """

    helps[
        "iot ops ns asset datapoint export"
    ] = """
        type: command
        short-summary: Export datapoints to file.

        examples:
        - name: Export datapoints to JSON
          text: >
            az iot ops ns asset datapoint export --asset myasset --instance myInstance
            -g myInstanceResourceGroup --dataset default
    """

    helps[
        "iot ops ns asset datapoint import"
    ] = """
        type: command
        short-summary: Import datapoints from file.

        examples:
        - name: Import datapoints from a JSON file
          text: >
            az iot ops ns asset datapoint import --asset myasset --instance myInstance
            -g myInstanceResourceGroup --dataset default --input-file ./datapoints.json
    """

    helps[
        "iot ops ns asset event-group"
    ] = """
        type: group
        short-summary: Manage event-groups for namespaced assets in an IoT Operations instance.
        long-summary: >
            The connector type is detected automatically from the existing asset.
            For connector-specific parameters use --event-group-config (inline JSON or file).
            Use --show-template to discover the supported configuration schema for the asset's connector type.
    """

    helps[
        "iot ops ns asset event-group add"
    ] = """
        type: command
        short-summary: Add an event-group to a namespaced asset in an IoT Operations instance.
        long-summary: >
            The connector type is detected from the asset's device endpoint.
            Connector-specific configuration can be supplied via --event-group-config.
            Use --show-template to discover the supported config schema. For non-OPC UA connectors,
            a connector template must exist in the instance.

        examples:
        - name: Add a basic event-group to any asset type
          text: >
            az iot ops ns asset event-group add --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name alarmGroup

        - name: Show the event-group config template for the asset's connector type
          text: >
            az iot ops ns asset event-group add --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name alarmGroup --show-template config

        - name: Add an event-group with connector-specific configuration from inline JSON
          text: >
            az iot ops ns asset event-group add --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name alarmGroup
            --event-group-config '{"eventGroupConfiguration": {"queueSize": 5}}'

        - name: Add an event-group with configuration from a file
          text: >
            az iot ops ns asset event-group add --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name alarmGroup --event-group-config ./event_group_config.json

        - name: Add an event-group with a default MQTT destination
          text: >
            az iot ops ns asset event-group add --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name alarmGroup
            --event-group-config '{"destinations": [{"target": "Mqtt", "configuration": {"topic": "factory/alarms", "retain": "Keep", "qos": "Qos1", "ttl": 3600}}]}'

        - name: Replace an existing event-group
          text: >
            az iot ops ns asset event-group add --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name alarmGroup --replace
    """

    helps[
        "iot ops ns asset event-group update"
    ] = """
        type: command
        short-summary: Update an event-group for a namespaced asset in an IoT Operations instance.
        long-summary: >
            The connector type is detected from the asset's device endpoint.
            Use --event-group-config to supply connector-specific configuration.
            Use --show-template config to see current event-group values pre-filled in the full schema
            structure (ready to edit and pass back via --event-group-config).
            Use --show-template schema to see the full connector schema with types and constraints.

        examples:
        - name: Show current event-group config pre-filled with existing values (for editing before update)
          text: >
            az iot ops ns asset event-group update --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name alarmGroup --show-template config

        - name: Show the event-group config schema with types and constraints
          text: >
            az iot ops ns asset event-group update --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name alarmGroup --show-template schema

        - name: Update event-group configuration from inline JSON
          text: >
            az iot ops ns asset event-group update --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name alarmGroup
            --event-group-config '{"eventGroupConfiguration": {"queueSize": 10}}'

        - name: Update event-group data source
          text: >
            az iot ops ns asset event-group update --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name alarmGroup --data-source "alarm.updated"
    """

    helps[
        "iot ops ns asset event-group list"
    ] = """
        type: command
        short-summary: List event-groups for a namespaced asset in an IoT Operations instance.

        examples:
        - name: List all event-groups for an asset
          text: >
            az iot ops ns asset event-group list --asset myasset --instance myInstance
            -g myInstanceResourceGroup
    """

    helps[
        "iot ops ns asset event-group remove"
    ] = """
        type: command
        short-summary: Remove an event-group from a namespaced asset in an IoT Operations instance.

        examples:
        - name: Remove an event-group from an asset
          text: >
            az iot ops ns asset event-group remove --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name alarmGroup
    """

    helps[
        "iot ops ns asset event-group show"
    ] = """
        type: command
        short-summary: Show details of an event-group for a namespaced asset in an IoT Operations instance.

        examples:
        - name: Show event-group details
          text: >
            az iot ops ns asset event-group show --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name alarmGroup
    """

    helps[
        "iot ops ns asset event-group export"
    ] = """
        type: command
        short-summary: Export event-groups to file.

        examples:
        - name: Export event-groups to JSON
          text: >
            az iot ops ns asset event-group export --asset myasset --instance myInstance
            -g myInstanceResourceGroup
    """

    helps[
        "iot ops ns asset event-group import"
    ] = """
        type: command
        short-summary: Import event-groups from file.

        examples:
        - name: Import event-groups from a JSON file
          text: >
            az iot ops ns asset event-group import --asset myasset --instance myInstance
            -g myInstanceResourceGroup --input-file ./event_groups.json
    """

    helps[
        "iot ops ns asset event"
    ] = """
        type: group
        short-summary: Manage events for asset event-groups in IoT Operations namespaces.
        long-summary: >
            The connector type is detected automatically from the existing asset.
            For connector-specific parameters use --event-config (inline JSON or file).
            Use --show-template to discover the supported configuration schema for the asset's connector type.
    """

    helps[
        "iot ops ns asset event add"
    ] = """
        type: command
        short-summary: Add an event to an asset event-group in an IoT Operations namespace.
        long-summary: >
            The connector type is detected from the asset's device endpoint.
            Connector-specific configuration (queue size, sampling interval, etc.) and destinations
            can be supplied via --event-config. Use --show-template to discover the supported
            config schema. For non-OPC UA connectors, a connector template must exist in the instance.

        examples:
        - name: Add a basic event to any asset type
          text: >
            az iot ops ns asset event add --asset myasset --instance myInstance
            -g myInstanceResourceGroup --event-group alarmGroup --name severity --data-source "alarm.severity"

        - name: Show the event config template for the asset's connector type
          text: >
            az iot ops ns asset event add --asset myasset --instance myInstance
            -g myInstanceResourceGroup --event-group alarmGroup --name severity --data-source "alarm.severity"
            --show-template config

        - name: Add an event with connector-specific configuration from inline JSON
          text: >
            az iot ops ns asset event add --asset myasset --instance myInstance
            -g myInstanceResourceGroup --event-group alarmGroup --name severity --data-source "alarm.severity"
            --event-config '{"eventConfiguration": {"samplingInterval": 1000, "queueSize": 5}}'

        - name: Add an event with configuration from a file
          text: >
            az iot ops ns asset event add --asset myasset --instance myInstance
            -g myInstanceResourceGroup --event-group alarmGroup --name severity --data-source "alarm.severity"
            --event-config ./event_config.json

        - name: Add an event with an MQTT destination
          text: >
            az iot ops ns asset event add --asset myasset --instance myInstance
            -g myInstanceResourceGroup --event-group alarmGroup --name severity --data-source "alarm.severity"
            --event-config '{"destinations": [{"target": "Mqtt", "configuration": {"topic": "factory/alarms", "retain": "Keep", "qos": "Qos1", "ttl": 3600}}]}'

        - name: Replace an existing event
          text: >
            az iot ops ns asset event add --asset myasset --instance myInstance
            -g myInstanceResourceGroup --event-group alarmGroup --name severity --data-source "alarm.severity.updated"
            --replace
    """

    helps[
        "iot ops ns asset event list"
    ] = """
        type: command
        short-summary: List events for an asset event-group in an IoT Operations namespace.

        examples:
        - name: List all events for an event-group
          text: >
            az iot ops ns asset event list --asset myasset --instance myInstance
            -g myInstanceResourceGroup --event-group alarmGroup
    """

    helps[
        "iot ops ns asset event remove"
    ] = """
        type: command
        short-summary: Remove an event from an asset event-group in an IoT Operations namespace.

        examples:
        - name: Remove an event from an event-group
          text: >
            az iot ops ns asset event remove --asset myasset --instance myInstance
            -g myInstanceResourceGroup --event-group alarmGroup --name severity
    """

    helps[
        "iot ops ns asset event export"
    ] = """
        type: command
        short-summary: Export events to file.

        examples:
        - name: Export events to JSON
          text: >
            az iot ops ns asset event export --asset myasset --instance myInstance
            -g myInstanceResourceGroup --event-group alarmGroup
    """

    helps[
        "iot ops ns asset event import"
    ] = """
        type: command
        short-summary: Import events from file.

        examples:
        - name: Import events from a JSON file
          text: >
            az iot ops ns asset event import --asset myasset --instance myInstance
            -g myInstanceResourceGroup --event-group alarmGroup --input-file ./events.json
    """

    helps[
        "iot ops ns asset mgmt-group"
    ] = """
        type: group
        short-summary: Manage management groups for namespaced assets in an IoT Operations instance.
        long-summary: >
            The connector type is detected automatically from the existing asset.
            For connector-specific parameters use --mgmt-group-config (inline JSON or file).
            Use --show-template to discover the supported configuration schema for the asset's connector type.
    """

    helps[
        "iot ops ns asset mgmt-group add"
    ] = """
        type: command
        short-summary: Add a management group to a namespaced asset in an IoT Operations instance.
        long-summary: >
            The connector type is detected from the asset's device endpoint.
            Connector-specific configuration can be supplied via --mgmt-group-config.
            Use --show-template to discover the supported config schema. For non-OPC UA connectors,
            a connector template must exist in the instance.

        examples:
        - name: Add a basic management group to any asset type
          text: >
            az iot ops ns asset mgmt-group add --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name boilerControls

        - name: Show the management group config template for the asset's connector type
          text: >
            az iot ops ns asset mgmt-group add --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name boilerControls --show-template config

        - name: Add a management group with connector-specific configuration from inline JSON
          text: >
            az iot ops ns asset mgmt-group add --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name boilerControls
            --mgmt-group-config '{"managementGroupConfiguration": {"maxConcurrentRequests": 5}}'

        - name: Add a management group with configuration from a file
          text: >
            az iot ops ns asset mgmt-group add --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name boilerControls --mgmt-group-config ./mgmt_group_config.json

        - name: Replace an existing management group
          text: >
            az iot ops ns asset mgmt-group add --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name boilerControls --replace
    """

    helps[
        "iot ops ns asset mgmt-group update"
    ] = """
        type: command
        short-summary: Update a management group for a namespaced asset in an IoT Operations instance.
        long-summary: >
            The connector type is detected from the asset's device endpoint.
            Use --mgmt-group-config to supply connector-specific configuration.
            Use --show-template config to see current management group values pre-filled in the full schema
            structure (ready to edit and pass back via --mgmt-group-config).
            Use --show-template schema to see the full connector schema with types and constraints.

        examples:
        - name: Show current management group config pre-filled with existing values (for editing before update)
          text: >
            az iot ops ns asset mgmt-group update --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name boilerControls --show-template config

        - name: Show the management group config schema with types and constraints
          text: >
            az iot ops ns asset mgmt-group update --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name boilerControls --show-template schema

        - name: Update management group configuration from inline JSON
          text: >
            az iot ops ns asset mgmt-group update --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name boilerControls
            --mgmt-group-config '{"managementGroupConfiguration": {"maxConcurrentRequests": 10}}'

        - name: Update management group data source
          text: >
            az iot ops ns asset mgmt-group update --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name boilerControls --data-source "boiler.controls"
    """

    helps[
        "iot ops ns asset mgmt-group list"
    ] = """
        type: command
        short-summary: List management groups for a namespaced asset in an IoT Operations instance.

        examples:
        - name: List all management groups for an asset
          text: >
            az iot ops ns asset mgmt-group list --asset myasset --instance myInstance
            -g myInstanceResourceGroup
    """

    helps[
        "iot ops ns asset mgmt-group remove"
    ] = """
        type: command
        short-summary: Remove a management group from a namespaced asset in an IoT Operations instance.

        examples:
        - name: Remove a management group from an asset
          text: >
            az iot ops ns asset mgmt-group remove --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name boilerControls
    """

    helps[
        "iot ops ns asset mgmt-group show"
    ] = """
        type: command
        short-summary: Show details of a management group for a namespaced asset in an IoT Operations instance.

        examples:
        - name: Show management group details
          text: >
            az iot ops ns asset mgmt-group show --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name boilerControls
    """

    helps[
        "iot ops ns asset mgmt-group export"
    ] = """
        type: command
        short-summary: Export management groups to file.

        examples:
        - name: Export management groups to JSON
          text: >
            az iot ops ns asset mgmt-group export --asset myasset --instance myInstance
            -g myInstanceResourceGroup
    """

    helps[
        "iot ops ns asset mgmt-group import"
    ] = """
        type: command
        short-summary: Import management groups from file.

        examples:
        - name: Import management groups from a JSON file
          text: >
            az iot ops ns asset mgmt-group import --asset myasset --instance myInstance
            -g myInstanceResourceGroup --input-file ./management_groups.json
    """

    helps[
        "iot ops ns asset mgmt-action"
    ] = """
        type: group
        short-summary: Manage actions for asset management groups in IoT Operations namespaces.
        long-summary: >
            The connector type is detected automatically from the existing asset.
            For connector-specific parameters use --action-config (inline JSON or file).
            Use --show-template to discover the supported configuration schema for the asset's connector type.
    """

    helps[
        "iot ops ns asset mgmt-action add"
    ] = """
        type: command
        short-summary: Add an action to an asset management group in an IoT Operations namespace.
        long-summary: >
            The connector type is detected from the asset's device endpoint.
            Connector-specific configuration can be supplied via --action-config. Use --show-template
            to discover the supported config schema. For non-OPC UA connectors, a connector template
            must exist in the instance.

        examples:
        - name: Add a basic action to any asset type
          text: >
            az iot ops ns asset mgmt-action add --asset myasset --instance myInstance
            -g myInstanceResourceGroup --group boilerControls --name restart --target-uri "opc.tcp://boiler/restart"

        - name: Show the action config template for the asset's connector type
          text: >
            az iot ops ns asset mgmt-action add --asset myasset --instance myInstance
            -g myInstanceResourceGroup --group boilerControls --name restart --show-template config

        - name: Add an action with connector-specific configuration from inline JSON
          text: >
            az iot ops ns asset mgmt-action add --asset myasset --instance myInstance
            -g myInstanceResourceGroup --group boilerControls --name restart --target-uri "opc.tcp://boiler/restart"
            --action-config '{"actionConfiguration": {"retryCount": 3}}'

        - name: Add an action with configuration from a file
          text: >
            az iot ops ns asset mgmt-action add --asset myasset --instance myInstance
            -g myInstanceResourceGroup --group boilerControls --name restart --target-uri "opc.tcp://boiler/restart"
            --action-config ./action_config.json

        - name: Replace an existing action
          text: >
            az iot ops ns asset mgmt-action add --asset myasset --instance myInstance
            -g myInstanceResourceGroup --group boilerControls --name restart --target-uri "opc.tcp://boiler/restart"
            --replace
    """

    helps[
        "iot ops ns asset mgmt-action list"
    ] = """
        type: command
        short-summary: List actions for an asset management group in an IoT Operations namespace.

        examples:
        - name: List all actions for a management group
          text: >
            az iot ops ns asset mgmt-action list --asset myasset --instance myInstance
            -g myInstanceResourceGroup --group boilerControls
    """

    helps[
        "iot ops ns asset mgmt-action remove"
    ] = """
        type: command
        short-summary: Remove an action from an asset management group in an IoT Operations namespace.

        examples:
        - name: Remove an action from a management group
          text: >
            az iot ops ns asset mgmt-action remove --asset myasset --instance myInstance
            -g myInstanceResourceGroup --group boilerControls --name restart
    """

    helps[
        "iot ops ns asset mgmt-action export"
    ] = """
        type: command
        short-summary: Export management group actions to file.

        examples:
        - name: Export actions to JSON
          text: >
            az iot ops ns asset mgmt-action export --asset myasset --instance myInstance
            -g myInstanceResourceGroup --group boilerControls
    """

    helps[
        "iot ops ns asset mgmt-action import"
    ] = """
        type: command
        short-summary: Import management group actions from file.

        examples:
        - name: Import actions from a JSON file
          text: >
            az iot ops ns asset mgmt-action import --asset myasset --instance myInstance
            -g myInstanceResourceGroup --group boilerControls --input-file ./actions.json
    """

    helps[
        "iot ops ns asset stream"
    ] = """
        type: group
        short-summary: Manage streams for namespaced assets in an IoT Operations instance.
        long-summary: >
            The connector type is detected automatically from the existing asset.
            For connector-specific parameters use --stream-config (inline JSON or file).
            Use --show-template to discover the supported configuration schema for the asset's connector type.
    """

    helps[
        "iot ops ns asset stream add"
    ] = """
        type: command
        short-summary: Add a stream to a namespaced asset in an IoT Operations instance.
        long-summary: >
            The connector type is detected from the asset's device endpoint.
            Connector-specific configuration and destinations can be supplied via --stream-config.
            Use --show-template to discover the supported config schema. For non-OPC UA connectors,
            a connector template must exist in the instance.

        examples:
        - name: Add a basic stream to any asset type
          text: >
            az iot ops ns asset stream add --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name videoStream

        - name: Show the stream config template for the asset's connector type
          text: >
            az iot ops ns asset stream add --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name videoStream --show-template config

        - name: Add a stream with connector-specific configuration from inline JSON
          text: >
            az iot ops ns asset stream add --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name videoStream
            --stream-config '{"streamConfiguration": {"taskType": "snapshot-to-mqtt", "snapshotsPerSecond": 5}}'

        - name: Add a stream with configuration from a file
          text: >
            az iot ops ns asset stream add --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name videoStream --stream-config ./stream_config.json

        - name: Add a stream with an MQTT destination
          text: >
            az iot ops ns asset stream add --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name videoStream
            --stream-config '{"destinations": [{"target": "Mqtt", "configuration": {"topic": "factory/streams", "retain": "Keep", "qos": "Qos1", "ttl": 3600}}]}'

        - name: Replace an existing stream
          text: >
            az iot ops ns asset stream add --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name videoStream --replace
    """

    helps[
        "iot ops ns asset stream update"
    ] = """
        type: command
        short-summary: Update a stream for a namespaced asset in an IoT Operations instance.
        long-summary: >
            The connector type is detected from the asset's device endpoint.
            Use --stream-config to supply connector-specific configuration.
            Use --show-template config to see current stream values pre-filled in the full schema
            structure (ready to edit and pass back via --stream-config).
            Use --show-template schema to see the full connector schema with types and constraints.

        examples:
        - name: Show current stream config pre-filled with existing values (for editing before update)
          text: >
            az iot ops ns asset stream update --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name videoStream --show-template config

        - name: Show the stream config schema with types and constraints
          text: >
            az iot ops ns asset stream update --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name videoStream --show-template schema

        - name: Update stream configuration from inline JSON
          text: >
            az iot ops ns asset stream update --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name videoStream
            --stream-config '{"streamConfiguration": {"snapshotsPerSecond": 10}}'

        - name: Update stream type reference
          text: >
            az iot ops ns asset stream update --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name videoStream --type-ref "myTypeRef"
    """

    helps[
        "iot ops ns asset stream list"
    ] = """
        type: command
        short-summary: List streams for a namespaced asset in an IoT Operations instance.

        examples:
        - name: List all streams for an asset
          text: >
            az iot ops ns asset stream list --asset myasset --instance myInstance
            -g myInstanceResourceGroup
    """

    helps[
        "iot ops ns asset stream remove"
    ] = """
        type: command
        short-summary: Remove a stream from a namespaced asset in an IoT Operations instance.

        examples:
        - name: Remove a stream from an asset
          text: >
            az iot ops ns asset stream remove --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name videoStream
    """

    helps[
        "iot ops ns asset stream show"
    ] = """
        type: command
        short-summary: Show details of a stream for a namespaced asset in an IoT Operations instance.

        examples:
        - name: Show stream details
          text: >
            az iot ops ns asset stream show --asset myasset --instance myInstance
            -g myInstanceResourceGroup --name videoStream
    """

    helps[
        "iot ops ns asset stream export"
    ] = """
        type: command
        short-summary: Export streams to file.

        examples:
        - name: Export streams to JSON
          text: >
            az iot ops ns asset stream export --asset myasset --instance myInstance
            -g myInstanceResourceGroup
    """

    helps[
        "iot ops ns asset stream import"
    ] = """
        type: command
        short-summary: Import streams from file.

        examples:
        - name: Import streams from a JSON file
          text: >
            az iot ops ns asset stream import --asset myasset --instance myInstance
            -g myInstanceResourceGroup --input-file ./streams.json
    """

    helps[
        "iot ops ns asset opcua dataset"
    ] = """
        type: group
        short-summary: Manage datasets for OPC UA namespaced assets in an IoT Operations instance.
    """

    helps[
        "iot ops ns asset opcua dataset add"
    ] = """
        type: command
        short-summary: Add a dataset to an OPC UA namespaced asset in an IoT Operations instance.

        examples:
        - name: Add a basic OPC UA dataset
          text: >
            az iot ops ns asset opcua dataset add --asset myopcuaasset --instance myInstance
            -g myInstanceResourceGroup --name temperatureData --data-source "ns=2;s=Temperature"

        - name: Add an OPC UA dataset with publishing and sampling intervals
          text: >
            az iot ops ns asset opcua dataset add --asset myopcuaasset --instance myInstance
            -g myInstanceResourceGroup --name pressureData --data-source "ns=2;s=Pressure"
            --publish-int 1000 --sampling-int 500 --queue-size 10

        - name: Add an OPC UA dataset with key frame count
          text: >
            az iot ops ns asset opcua dataset add --asset myopcuaasset --instance myInstance
            -g myInstanceResourceGroup --name videoData --data-source "ns=2;s=VideoStream"
            --key-frame-count 5

        - name: Add an OPC UA dataset with MQTT destination
          text: >
            az iot ops ns asset opcua dataset add --asset myopcuaasset --instance myInstance
            -g myInstanceResourceGroup --name temperatureData --data-source "ns=2;s=Temperature"
            --dest topic="factory/opcua/temperature" retain=Keep qos=Qos1 ttl=3600

        - name: Add an OPC UA dataset and replace existing one with same name
          text: >
            az iot ops ns asset opcua dataset add --asset myopcuaasset --instance myInstance
            -g myInstanceResourceGroup --name temperatureData --data-source "ns=3;s=NewTemperature"
            --replace

        - name: Add an OPC UA dataset with a start instance
          text: >
            az iot ops ns asset opcua dataset add --asset myopcuaasset --instance myInstance
            -g myInstanceResourceGroup --name temperatureData --data-source "ns=2;s=Temperature"
            --start-inst "ns=2;i=1001"
    """

    helps[
        "iot ops ns asset opcua dataset list"
    ] = """
        type: command
        short-summary: List datasets for an OPC UA namespaced asset in an IoT Operations instance.

        examples:
        - name: List all datasets for an OPC UA asset
          text: >
            az iot ops ns asset opcua dataset list --asset myopcuaasset --instance myInstance
            -g myInstanceResourceGroup
    """

    helps[
        "iot ops ns asset opcua dataset remove"
    ] = """
        type: command
        short-summary: Remove a dataset from an OPC UA namespaced asset in an IoT Operations instance.

        examples:
        - name: Remove a dataset from an OPC UA asset
          text: >
            az iot ops ns asset opcua dataset remove --asset myopcuaasset --instance myInstance
            -g myInstanceResourceGroup --name temperatureData
    """

    helps[
        "iot ops ns asset opcua dataset show"
    ] = """
        type: command
        short-summary: Show details of a dataset for an OPC UA namespaced asset in an IoT Operations instance.

        examples:
        - name: Show dataset details
          text: >
            az iot ops ns asset opcua dataset show --asset myopcuaasset --instance myInstance
            -g myInstanceResourceGroup --name temperatureData
    """

    helps[
        "iot ops ns asset opcua dataset update"
    ] = """
        type: command
        short-summary: Update a dataset for an OPC UA namespaced asset in an IoT Operations instance.

        examples:
        - name: Update dataset data source and intervals
          text: >
            az iot ops ns asset opcua dataset update --asset myopcuaasset --instance myInstance
            -g myInstanceResourceGroup --name temperatureData --data-source "ns=3;s=UpdatedTemperature"
            --publish-int 2000 --sampling-int 1000

        - name: Update dataset queue size and key frame count
          text: >
            az iot ops ns asset opcua dataset update --asset myopcuaasset --instance myInstance
            -g myInstanceResourceGroup --name videoData --queue-size 20 --key-frame-count 10

        - name: Update dataset destination
          text: >
            az iot ops ns asset opcua dataset update --asset myopcuaasset --instance myInstance
            -g myInstanceResourceGroup --name temperatureData
            --dest topic="factory/opcua/updated/temperature" retain=Never qos=Qos0 ttl=7200

        - name: Update the start instance for a dataset
          text: >
            az iot ops ns asset opcua dataset update --asset myopcuaasset --instance myInstance
            -g myInstanceResourceGroup --name temperatureData --start-inst "ns=2;i=2001"
    """

    helps[
        "iot ops ns asset opcua datapoint"
    ] = """
        type: group
        short-summary: Manage data points for OPC UA asset datasets in Device Registry namespaces.
    """

    helps[
        "iot ops ns asset opcua datapoint add"
    ] = """
        type: command
        short-summary: Add a datapoint to an OPC UA asset dataset in a Device Registry namespace.

        examples:
        - name: Add a basic OPC UA datapoint
          text: >
            az iot ops ns asset opcua datapoint add --asset myopcuaasset --instance myInstance
            -g myInstanceResourceGroup --dataset temperatureData --name temp1 --data-source "ns=2;s=Temp1"

        - name: Add an OPC UA datapoint with queue size and sampling interval
          text: >
            az iot ops ns asset opcua datapoint add --asset myopcuaasset --instance myInstance
            -g myInstanceResourceGroup --dataset pressureData --name pressure1 --data-source "ns=2;s=Pressure1"
            --queue-size 5 --sampling-int 1000

        - name: Add an OPC UA datapoint and replace existing one with same name
          text: >
            az iot ops ns asset opcua datapoint add --asset myopcuaasset --instance myInstance
            -g myInstanceResourceGroup --dataset temperatureData --name temp1 --data-source "ns=3;s=NewTemp1"
            --replace
    """

    helps[
        "iot ops ns asset opcua datapoint list"
    ] = """
        type: command
        short-summary: List data points for an OPC UA asset dataset in a Device Registry namespace.

        examples:
        - name: List all data points for a dataset
          text: >
            az iot ops ns asset opcua datapoint list --asset myopcuaasset --instance myInstance
            -g myInstanceResourceGroup --dataset temperatureData
    """

    helps[
        "iot ops ns asset opcua datapoint remove"
    ] = """
        type: command
        short-summary: Remove a datapoint from an OPC UA asset dataset in a Device Registry namespace.

        examples:
        - name: Remove a datapoint from a dataset
          text: >
            az iot ops ns asset opcua datapoint remove --asset myopcuaasset --instance myInstance
            -g myInstanceResourceGroup --dataset temperatureData --name temp1
    """

    helps[
        "iot ops ns asset opcua event-group"
    ] = """
        type: group
        short-summary: Manage event groups for OPC UA namespaced assets in an IoT Operations instance.
    """

    helps[
        "iot ops ns asset opcua event-group add"
    ] = """
        type: command
        short-summary: Add an event group to an OPC UA namespaced asset in an IoT Operations instance.

        examples:
        - name: Add a basic OPC UA event group
          text: >
            az iot ops ns asset opcua event-group add --asset myopcuaasset --instance myInstance
            -g myInstanceResourceGroup --name alarmEvent --data-source "ns=2;i=1000"

        - name: Add an OPC UA event group with publishing interval and queue size
          text: >
            az iot ops ns asset opcua event-group add --asset myopcuaasset --instance myInstance
            -g myInstanceResourceGroup --name systemEvent --data-source "ns=2;i=200"
            --publish-int 1500 --queue-size 8

        - name: Add an OPC UA event group with MQTT destination
          text: >
            az iot ops ns asset opcua event-group add --asset myopcuaasset --instance myInstance
            -g myInstanceResourceGroup --name criticalAlarm --data-source "ns=2;i=4000"
            --dest topic="factory/opcua/alarms" retain=Keep qos=Qos0 ttl=7200

        - name: Replace an OPC UA event group with same name
          text: >
            az iot ops ns asset opcua event-group add --asset myopcuaasset --instance myInstance
            -g myInstanceResourceGroup --name alarmEvent --data-source "ns=3;i=1000"
            --replace

        - name: Add an OPC UA event group with a start instance
          text: >
            az iot ops ns asset opcua event-group add --asset myopcuaasset --instance myInstance
            -g myInstanceResourceGroup --name alarmEvent --data-source "ns=2;i=1000"
            --start-inst "ns=3;i=3001"

        - name: Add an OPC UA event group with filter type and filter clauses
          text: >
            az iot ops ns asset opcua event-group add --asset myopcuaasset --instance myInstance
            -g myInstanceResourceGroup --name alarmEvent --data-source "ns=2;i=1000"
            --filter-type "ns=2;i=5001" --filter-clause path="/EventType" type="ns=2;i=5001"
    """

    helps[
        "iot ops ns asset opcua event-group list"
    ] = """
        type: command
        short-summary: List event groups for an OPC UA namespaced asset in an IoT Operations instance.

        examples:
        - name: List all event groups for an OPC UA asset
          text: >
            az iot ops ns asset opcua event-group list --asset myopcuaasset --instance myInstance
            -g myInstanceResourceGroup
    """

    helps[
        "iot ops ns asset opcua event-group remove"
    ] = """
        type: command
        short-summary: Remove an event group from an OPC UA namespaced asset in an IoT Operations instance.

        examples:
        - name: Remove an event group from an OPC UA asset
          text: >
            az iot ops ns asset opcua event-group remove --asset myopcuaasset --instance myInstance
            -g myInstanceResourceGroup --name alarmEvent
    """

    helps[
        "iot ops ns asset opcua event-group show"
    ] = """
        type: command
        short-summary: Show details of an event group for an OPC UA namespaced asset in an IoT Operations instance.

        examples:
        - name: Show event group details
          text: >
            az iot ops ns asset opcua event-group show --asset myopcuaasset --instance myInstance
            -g myInstanceResourceGroup --name alarmEvent
    """

    helps[
        "iot ops ns asset opcua event-group update"
    ] = """
        type: command
        short-summary: Update an event group for an OPC UA namespaced asset in an IoT Operations instance.

        examples:
        - name: Update event group publishing interval and queue size
          text: >
            az iot ops ns asset opcua event-group update --asset myopcuaasset --instance myInstance
            -g myInstanceResourceGroup --name alarmEvent --publish-int 2000 --queue-size 10

        - name: Update event group destination
          text: >
            az iot ops ns asset opcua event-group update --asset myopcuaasset --instance myInstance
            -g myInstanceResourceGroup --name systemEvent
            --dest topic="factory/opcua/system/updated" retain=Never qos=Qos1 ttl=3600

        - name: Update event group start instance and filter configuration
          text: >
            az iot ops ns asset opcua event-group update --asset myopcuaasset --instance myInstance
            -g myInstanceResourceGroup --name alarmEvent --start-inst "ns=3;i=4001"
            --filter-type "ns=2;i=5002" --filter-clause path="/Severity" type="ns=2;i=5002"
    """

    helps[
        "iot ops ns asset opcua event"
    ] = """
        type: group
        short-summary: Manage individual events for OPC UA asset event groups in Device Registry namespaces.
    """

    helps[
        "iot ops ns asset opcua event add"
    ] = """
        type: command
        short-summary: Add an event to an OPC UA asset event group in a Device Registry namespace.

        examples:
        - name: Add a basic OPC UA event
          text: >
            az iot ops ns asset opcua event add --asset myopcuaasset --instance myInstance
            -g myInstanceResourceGroup --event-group alarmGroup --name severity --data-source "alarm.severity"

        - name: Add an OPC UA event with sampling interval and queue size
          text: >
            az iot ops ns asset opcua event add --asset myopcuaasset --instance myInstance
            -g myInstanceResourceGroup --event-group alarmGroup --name pressure --data-source "alarm.pressure"
            --sampling-int 500 --queue-size 5

        - name: Replace an OPC UA event with same name
          text: >
            az iot ops ns asset opcua event add --asset myopcuaasset --instance myInstance
            -g myInstanceResourceGroup --event-group alarmGroup --name severity --data-source "alarm.severity.updated"
            --replace

        - name: Add an OPC UA event with filter type and filter clauses
          text: >
            az iot ops ns asset opcua event add --asset myopcuaasset --instance myInstance
            -g myInstanceResourceGroup --event-group alarmGroup --name criticalAlarm --data-source "alarm.critical"
            --filter-type "ns=2;i=5001" --filter-clause path="/EventType" type="ns=2;i=5001"
    """

    helps[
        "iot ops ns asset opcua event list"
    ] = """
        type: command
        short-summary: List events for an OPC UA asset event group in a Device Registry namespace.

        examples:
        - name: List all events for an event group
          text: >
            az iot ops ns asset opcua event list --asset myopcuaasset --instance myInstance
            -g myInstanceResourceGroup --event-group alarmGroup
    """

    helps[
        "iot ops ns asset opcua event remove"
    ] = """
        type: command
        short-summary: Remove an event from an OPC UA asset event group in a Device Registry namespace.

        examples:
        - name: Remove an event from an event group
          text: >
            az iot ops ns asset opcua event remove --asset myopcuaasset --instance myInstance
            -g myInstanceResourceGroup --event-group alarmGroup --name severity
    """

    helps[
        "iot ops ns asset opcua mgmt-group"
    ] = """
        type: group
        short-summary: Manage OPC UA asset management groups in an IoT Operations instance.
        long-summary: |
          Management groups define collections of management actions that can be performed on OPC UA assets.
          Each management group contains actions with specific configurations and targets.
    """

    helps[
        "iot ops ns asset opcua mgmt-group add"
    ] = """
        type: command
        short-summary: Add a management group to an OPC UA asset.

        examples:
        - name: Add a basic management group to an OPC UA asset.
          text: >
            az iot ops ns asset opcua mgmt-group add --asset myopcuaasset --instance myInstance -g myInstanceResourceGroup
            --name myManagementGroup

        - name: Add a management group with data source, default topic and timeout.
          text: >
            az iot ops ns asset opcua mgmt-group add --asset myopcuaasset --instance myInstance -g myInstanceResourceGroup
            --name myManagementGroup --default-topic factory/opcua/management/responses --default-timeout 30
            --data-source mydatasource

        - name: Replace an existing management group with the same name.
          text: >
            az iot ops ns asset opcua mgmt-group add --asset myopcuaasset --instance myInstance -g myInstanceResourceGroup
            --name myManagementGroup --default-topic factory/opcua/control/commands --default-timeout 60
            --data-source mydatasource --replace
    """

    helps[
        "iot ops ns asset opcua mgmt-group list"
    ] = """
        type: command
        short-summary: List management groups for an OPC UA asset.

        examples:
        - name: List all management groups for an OPC UA asset.
          text: >
            az iot ops ns asset opcua mgmt-group list --asset myopcuaasset --instance myInstance -g myInstanceResourceGroup
    """

    helps[
        "iot ops ns asset opcua mgmt-group show"
    ] = """
        type: command
        short-summary: Show details of a management group for an OPC UA asset.

        examples:
        - name: Show details of a specific management group.
          text: >
            az iot ops ns asset opcua mgmt-group show --asset myopcuaasset --instance myInstance -g myInstanceResourceGroup
            --name myManagementGroup
    """

    helps[
        "iot ops ns asset opcua mgmt-group update"
    ] = """
        type: command
        short-summary: Update a management group for an OPC UA asset.

        examples:
        - name: Update the default topic and timeout for a management group.
          text: >
            az iot ops ns asset opcua mgmt-group update --asset myopcuaasset --instance myInstance -g myInstanceResourceGroup
            --name myManagementGroup --default-topic factory/opcua/updated/responses --default-timeout 45

        - name: Update only the default timeout for a management group.
          text: >
            az iot ops ns asset opcua mgmt-group update --asset myopcuaasset --instance myInstance -g myInstanceResourceGroup
            --name myManagementGroup --default-timeout 90
    """

    helps[
        "iot ops ns asset opcua mgmt-group remove"
    ] = """
        type: command
        short-summary: Remove a management group from an OPC UA asset.

        examples:
        - name: Remove a management group from an OPC UA asset.
          text: >
            az iot ops ns asset opcua mgmt-group remove --asset myopcuaasset --instance myInstance -g myInstanceResourceGroup
            --name myManagementGroup
    """
    helps[
        "iot ops ns asset opcua mgmt-action"
    ] = """
        type: group
        short-summary: Manage actions within OPC UA asset management groups.
        long-summary: |
          Actions within management groups define specific operations that can be performed on OPC UA assets.
          Each action has a target URI and can include timeout and topic configuration.
    """

    helps[
        "iot ops ns asset opcua mgmt-action add"
    ] = """
        type: command
        short-summary: Add an action to an OPC UA asset management group.

        examples:
        - name: Add a basic action to a management group.
          text: >
            az iot ops ns asset opcua mgmt-action add --asset myopcuaasset --instance myInstance -g myInstanceResourceGroup
            --group myManagementGroup --name myAction --target-uri /opcua/device_service?OPCUAProfile=Profile1

        - name: Add an action with timeout and topic.
          text: >
            az iot ops ns asset opcua mgmt-action add --asset myopcuaasset --instance myInstance -g myInstanceResourceGroup
            --group myManagementGroup --name myAction --target-uri /opcua/device_service?OPCUAProfile=Profile1
            --timeout 45 --topic factory/opcua/actions

        - name: Add an action with specific action type.
          text: >
            az iot ops ns asset opcua mgmt-action add --asset myopcuaasset --instance myInstance -g myInstanceResourceGroup
            --group myManagementGroup --name myAction --target-uri /opcua/device_service?OPCUAProfile=Profile1
            --action-type Call --timeout 30

        - name: Add an action with a type reference.
          text: >
            az iot ops ns asset opcua mgmt-action add --asset myopcuaasset --instance myInstance -g myInstanceResourceGroup
            --group myManagementGroup --name myAction --target-uri /opcua/device_service?OPCUAProfile=Profile1
            --type-ref ns=2;i=1234

        - name: Replace an existing action with the same name.
          text: >
            az iot ops ns asset opcua mgmt-action add --asset myopcuaasset --instance myInstance -g myInstanceResourceGroup
            --group myManagementGroup --name myAction --target-uri /opcua/device_service?OPCUAProfile=Profile2
            --timeout 60 --replace
    """

    helps[
        "iot ops ns asset opcua mgmt-action list"
    ] = """
        type: command
        short-summary: List actions in an OPC UA asset management group.

        examples:
        - name: List all actions in a management group.
          text: >
            az iot ops ns asset opcua mgmt-action list --asset myopcuaasset --instance myInstance -g myInstanceResourceGroup
            --group myManagementGroup
    """

    helps[
        "iot ops ns asset opcua mgmt-action remove"
    ] = """
        type: command
        short-summary: Remove an action from an OPC UA asset management group.

        examples:
        - name: Remove an action from a management group.
          text: >
            az iot ops ns asset opcua mgmt-action remove --asset myopcuaasset --instance myInstance -g myInstanceResourceGroup
            --group myManagementGroup --name myAction
    """

    helps[
        "iot ops ns asset rest"
    ] = """
        type: group
        short-summary: Manage namespaced assets that point to REST device endpoints.
    """

    helps[
        "iot ops ns asset rest create"
    ] = """
        type: command
        short-summary: Create a REST namespaced asset in an IoT Operations instance.
        long-summary: The device endpoint must be of type Microsoft.Http.

        examples:
        - name: Create a basic REST asset
          text: >
            az iot ops ns asset rest create --name myrestasset --instance myInstance -g myInstanceResourceGroup
            --device myrestdevice --endpoint myRestEndpoint

        - name: Create a REST asset with dataset configuration
          text: >
            az iot ops ns asset rest create --name myrestasset --instance myInstance -g myInstanceResourceGroup
            --device myrestdevice --endpoint myRestEndpoint --sampling-int 5000

        - name: Create a REST asset with dataset destination
          text: >
            az iot ops ns asset rest create --name myrestasset --instance myInstance -g myInstanceResourceGroup
            --device myrestdevice --endpoint myRestEndpoint
            --dataset-dest topic="factory/rest/data" retain=Never qos=Qos1 ttl=3600

        - name: Create a REST asset with custom configuration and BrokerStateStore destination
          text: >
            az iot ops ns asset rest create --name myrestasset --instance myInstance -g myInstanceResourceGroup
            --device myrestdevice --endpoint myRestEndpoint --sampling-int 2000
            --dataset-dest key="rest-data-cache"

        - name: Create a REST asset with additional metadata
          text: >
            az iot ops ns asset rest create --name myrestasset --instance myInstance -g myInstanceResourceGroup
            --device myrestdevice --endpoint myRestEndpoint --description "Temperature sensor API"
            --display-name "Facility Temperature Monitor" --model "TempSensor-3000" --manufacturer "SensorCorp"
            --serial-number "TS-12345" --documentation-uri "https://example.com/docs/api"

        - name: Create a REST asset with custom attributes
          text: >
            az iot ops ns asset rest create --name myrestasset --instance myInstance -g myInstanceResourceGroup
            --device myrestdevice --endpoint myRestEndpoint --attribute location=warehouse
            --attribute sensor-type=temperature --attribute units=celsius
    """

    helps[
        "iot ops ns asset rest update"
    ] = """
        type: command
        short-summary: Update a REST namespaced asset in an IoT Operations instance.
        long-summary: The device endpoint must be of type Microsoft.Http.

        examples:
        - name: Update a REST asset's basic properties
          text: >
            az iot ops ns asset rest update --name myrestasset --instance myInstance -g myInstanceResourceGroup
            --description "Updated temperature sensor API" --display-name "Main Warehouse Temperature"

        - name: Update a REST asset's dataset destination to MQTT
          text: >
            az iot ops ns asset rest update --name myrestasset --instance myInstance -g myInstanceResourceGroup
            --dataset-dest topic="factory/rest/updated/data" retain=Keep qos=Qos1 ttl=7200

        - name: Update a REST asset's dataset destination to BrokerStateStore
          text: >
            az iot ops ns asset rest update --name myrestasset --instance myInstance -g myInstanceResourceGroup
            --dataset-dest key="updated-rest-cache"

        - name: Update a REST asset's metadata
          text: >
            az iot ops ns asset rest update --name myrestasset --instance myInstance -g myInstanceResourceGroup
            --model "TempSensor-4000" --manufacturer "SensorCorp" --serial-number "TS-67890"
            --documentation-uri "https://example.com/docs/api/v2"

        - name: Update a REST asset's custom attributes
          text: >
            az iot ops ns asset rest update --name myrestasset --instance myInstance -g myInstanceResourceGroup
            --attribute location=main-warehouse sensor-type=temperature units=fahrenheit accuracy=high

        - name: Disable a REST asset and update its reference information
          text: >
            az iot ops ns asset rest update --name myrestasset --instance myInstance -g myInstanceResourceGroup
            --disable --external-asset-id "TEMP-MAIN-01" --hardware-revision "v2.1"
    """

    helps[
        "iot ops ns asset rest dataset"
    ] = """
        type: group
        short-summary: Manage datasets for REST namespaced assets in an IoT Operations instance.
    """

    helps[
        "iot ops ns asset rest dataset add"
    ] = """
        type: command
        short-summary: Add a dataset to a REST namespaced asset in an IoT Operations instance.

        examples:
        - name: Add a basic REST dataset
          text: >
            az iot ops ns asset rest dataset add --asset myrestasset --instance myInstance
            -g myInstanceResourceGroup --name temperatureData --data-source "/api/temperature"

        - name: Add a REST dataset with sampling interval
          text: >
            az iot ops ns asset rest dataset add --asset myrestasset --instance myInstance
            -g myInstanceResourceGroup --name sensorData --data-source "/api/sensors/all"
            --sampling-int 30000

        - name: Add a REST dataset with MQTT destination
          text: >
            az iot ops ns asset rest dataset add --asset myrestasset --instance myInstance
            -g myInstanceResourceGroup --name weatherData --data-source "/api/weather"
            --dest topic="factory/rest/weather" retain=Never qos=Qos1 ttl=1800

        - name: Add a REST dataset with BrokerStateStore destination
          text: >
            az iot ops ns asset rest dataset add --asset myrestasset --instance myInstance
            -g myInstanceResourceGroup --name metricsData --data-source "/api/metrics"
            --dest key="rest-metrics-cache"

        - name: Add a REST dataset and replace existing one with same name
          text: >
            az iot ops ns asset rest dataset add --asset myrestasset --instance myInstance
            -g myInstanceResourceGroup --name temperatureData --data-source "/api/v2/temperature"
            --replace
    """

    helps[
        "iot ops ns asset rest dataset list"
    ] = """
        type: command
        short-summary: List datasets for a REST namespaced asset in an IoT Operations instance.

        examples:
        - name: List all datasets for a REST asset
          text: >
            az iot ops ns asset rest dataset list --asset myrestasset --instance myInstance
            -g myInstanceResourceGroup
    """

    helps[
        "iot ops ns asset rest dataset remove"
    ] = """
        type: command
        short-summary: Remove a dataset from a REST namespaced asset in an IoT Operations instance.

        examples:
        - name: Remove a dataset from a REST asset
          text: >
            az iot ops ns asset rest dataset remove --asset myrestasset --instance myInstance
            -g myInstanceResourceGroup --name temperatureData
    """

    helps[
        "iot ops ns asset rest dataset show"
    ] = """
        type: command
        short-summary: Show details of a dataset for a REST namespaced asset in an IoT Operations instance.

        examples:
        - name: Show dataset details
          text: >
            az iot ops ns asset rest dataset show --asset myrestasset --instance myInstance
            -g myInstanceResourceGroup --name temperatureData
    """

    helps[
        "iot ops ns asset rest dataset update"
    ] = """
        type: command
        short-summary: Update a dataset for a REST namespaced asset in an IoT Operations instance.

        examples:
        - name: Update dataset data source and sampling interval
          text: >
            az iot ops ns asset rest dataset update --asset myrestasset --instance myInstance
            -g myInstanceResourceGroup --name temperatureData --sampling-int 60000

        - name: Update dataset sampling interval only
          text: >
            az iot ops ns asset rest dataset update --asset myrestasset --instance myInstance
            -g myInstanceResourceGroup --name sensorData --sampling-int 15000

        - name: Update dataset destination to MQTT
          text: >
            az iot ops ns asset rest dataset update --asset myrestasset --instance myInstance
            -g myInstanceResourceGroup --name temperatureData
            --dest topic="factory/rest/updated/temperature" retain=Keep qos=Qos1 ttl=3600

        - name: Update dataset destination to BrokerStateStore
          text: >
            az iot ops ns asset rest dataset update --asset myrestasset --instance myInstance
            -g myInstanceResourceGroup --name metricsData
            --dest key="updated-rest-metrics"
    """

    helps[
        "iot ops ns asset sse"
    ] = """
        type: group
        short-summary: Manage namespaced assets that point to SSE (Server-Sent Events) device endpoints.
    """

    helps[
        "iot ops ns asset sse create"
    ] = """
        type: command
        short-summary: Create an SSE namespaced asset in an IoT Operations instance.
        long-summary: The device endpoint must be of type Microsoft.SSEHttp.

        examples:
        - name: Create a basic SSE asset
          text: >
            az iot ops ns asset sse create --name mysseAsset --instance myInstance -g myInstanceResourceGroup
            --device myssedevice --endpoint mySSEEndpoint

        - name: Create an SSE asset with dataset destination
          text: >
            az iot ops ns asset sse create --name mysseAsset --instance myInstance -g myInstanceResourceGroup
            --device myssedevice --endpoint mySSEEndpoint
            --dataset-dest topic="factory/sse/events" retain=Never qos=Qos1 ttl=3600

        - name: Create an SSE asset with event destination
          text: >
            az iot ops ns asset sse create --name mysseAsset --instance myInstance -g myInstanceResourceGroup
            --device myssedevice --endpoint mySSEEndpoint
            --event-dest topic="factory/sse/alerts" retain=Keep qos=Qos1 ttl=7200

        - name: Create an SSE asset with both dataset and event destinations
          text: >
            az iot ops ns asset sse create --name mysseAsset --instance myInstance -g myInstanceResourceGroup
            --device myssedevice --endpoint mySSEEndpoint
            --dataset-dest topic="factory/sse/data" retain=Never qos=Qos1 ttl=3600
            --event-dest topic="factory/sse/events" retain=Keep qos=Qos1 ttl=7200

        - name: Create an SSE asset with BrokerStateStore destinations
          text: >
            az iot ops ns asset sse create --name mysseAsset --instance myInstance -g myInstanceResourceGroup
            --device myssedevice --endpoint mySSEEndpoint
            --dataset-dest key="sse-data-cache"
            --event-dest topic="factory/sse/events" retain=Keep qos=Qos1 ttl=7200

        - name: Create an SSE asset with additional metadata
          text: >
            az iot ops ns asset sse create --name mysseAsset --instance myInstance -g myInstanceResourceGroup
            --device myssedevice --endpoint mySSEEndpoint --description "Real-time event stream from IoT sensors"
            --display-name "Facility Event Monitor" --model "EventStream-5000" --manufacturer "StreamCorp"
            --serial-number "ES-67890" --documentation-uri "https://example.com/docs/sse-api"

        - name: Create an SSE asset with custom attributes
          text: >
            az iot ops ns asset sse create --name mysseAsset --instance myInstance -g myInstanceResourceGroup
            --device myssedevice --endpoint mySSEEndpoint --attribute location=warehouse
            --attribute stream-type=events --attribute format=json
    """

    helps[
        "iot ops ns asset sse update"
    ] = """
        type: command
        short-summary: Update an SSE namespaced asset in an IoT Operations instance.

        examples:
        - name: Update SSE asset dataset destination
          text: >
            az iot ops ns asset sse update --name mysseAsset --instance myInstance -g myInstanceResourceGroup
            --dataset-dest topic="updated/sse/data" retain=Keep qos=Qos1 ttl=7200

        - name: Update SSE asset event destination
          text: >
            az iot ops ns asset sse update --name mysseAsset --instance myInstance -g myInstanceResourceGroup
            --event-dest topic="updated/sse/alerts" retain=Never qos=Qos0 ttl=3600

        - name: Update SSE asset metadata
          text: >
            az iot ops ns asset sse update --name mysseAsset --instance myInstance -g myInstanceResourceGroup
            --description "Updated real-time event stream" --display-name "Updated Event Monitor"

        - name: Update SSE asset attributes
          text: >
            az iot ops ns asset sse update --name mysseAsset --instance myInstance -g myInstanceResourceGroup
            --attribute location=factory --attribute priority=high

        - name: Disable SSE asset
          text: >
            az iot ops ns asset sse update --name mysseAsset --instance myInstance -g myInstanceResourceGroup
            --disable
    """

    helps[
        "iot ops ns asset sse dataset"
    ] = """
        type: group
        short-summary: Manage datasets for SSE namespaced assets.
    """

    helps[
        "iot ops ns asset sse dataset add"
    ] = """
        type: command
        short-summary: Add a dataset to an SSE namespaced asset in an IoT Operations instance.

        examples:
        - name: Add a basic dataset to an SSE asset
          text: >
            az iot ops ns asset sse dataset add --asset mysseAsset --instance myInstance
            -g myInstanceResourceGroup --name sensorData --data-source "temperature"

        - name: Add a dataset with MQTT destination
          text: >
            az iot ops ns asset sse dataset add --asset mysseAsset --instance myInstance
            -g myInstanceResourceGroup --name eventData --data-source "events"
            --dest topic="factory/sse/events" retain=Never qos=Qos1 ttl=3600

        - name: Add a dataset with BrokerStateStore destination
          text: >
            az iot ops ns asset sse dataset add --asset mysseAsset --instance myInstance
            -g myInstanceResourceGroup --name cacheData --data-source "metrics"
            --dest key="sse-metrics-cache"

        - name: Replace an existing dataset
          text: >
            az iot ops ns asset sse dataset add --asset mysseAsset --instance myInstance
            -g myInstanceResourceGroup --name sensorData --data-source "humidity" --replace
    """

    helps[
        "iot ops ns asset sse dataset list"
    ] = """
        type: command
        short-summary: List datasets for an SSE namespaced asset in an IoT Operations instance.

        examples:
        - name: List all datasets for an SSE asset
          text: >
            az iot ops ns asset sse dataset list --asset mysseAsset --instance myInstance
            -g myInstanceResourceGroup
    """

    helps[
        "iot ops ns asset sse dataset remove"
    ] = """
        type: command
        short-summary: Remove a dataset from an SSE namespaced asset in an IoT Operations instance.

        examples:
        - name: Remove a dataset from an SSE asset
          text: >
            az iot ops ns asset sse dataset remove --asset mysseAsset --instance myInstance
            -g myInstanceResourceGroup --name sensorData
    """

    helps[
        "iot ops ns asset sse dataset show"
    ] = """
        type: command
        short-summary: Show details of a dataset for an SSE namespaced asset in an IoT Operations instance.

        examples:
        - name: Show dataset details
          text: >
            az iot ops ns asset sse dataset show --asset mysseAsset --instance myInstance
            -g myInstanceResourceGroup --name sensorData
    """

    helps[
        "iot ops ns asset sse dataset update"
    ] = """
        type: command
        short-summary: Update a dataset for an SSE namespaced asset in an IoT Operations instance.

        examples:
        - name: Update dataset destination to MQTT
          text: >
            az iot ops ns asset sse dataset update --asset mysseAsset --instance myInstance
            -g myInstanceResourceGroup --name sensorData
            --dest topic="factory/sse/updated/sensor" retain=Keep qos=Qos1 ttl=3600

        - name: Update dataset destination to BrokerStateStore
          text: >
            az iot ops ns asset sse dataset update --asset mysseAsset --instance myInstance
            -g myInstanceResourceGroup --name metricsData
            --dest key="updated-sse-metrics"
    """

    helps[
        "iot ops ns asset sse event-group"
    ] = """
        type: group
        short-summary: Manage event groups for SSE namespaced assets.
    """

    helps[
        "iot ops ns asset sse event-group add"
    ] = """
        type: command
        short-summary: Add an event group to an SSE namespaced asset in an IoT Operations instance.

        examples:
        - name: Add a basic event group to an SSE asset
          text: >
            az iot ops ns asset sse event-group add --asset mysseAsset --instance myInstance
            -g myInstanceResourceGroup --name alertEvents --data-source "alert"

        - name: Add an event group with MQTT destination
          text: >
            az iot ops ns asset sse event-group add --asset mysseAsset --instance myInstance
            -g myInstanceResourceGroup --name systemEvents --data-source "system"
            --dest topic="factory/sse/system/alerts" retain=Keep qos=Qos1 ttl=7200

        - name: Replace an existing event group
          text: >
            az iot ops ns asset sse event-group add --asset mysseAsset --instance myInstance
            -g myInstanceResourceGroup --name alertEvents --data-source "critical-alert" --replace
    """

    helps[
        "iot ops ns asset sse event-group list"
    ] = """
        type: command
        short-summary: List event groups for an SSE namespaced asset in an IoT Operations instance.

        examples:
        - name: List all event groups for an SSE asset
          text: >
            az iot ops ns asset sse event-group list --asset mysseAsset --instance myInstance
            -g myInstanceResourceGroup
    """

    helps[
        "iot ops ns asset sse event-group remove"
    ] = """
        type: command
        short-summary: Remove an event group from an SSE namespaced asset in an IoT Operations instance.

        examples:
        - name: Remove an event group from an SSE asset
          text: >
            az iot ops ns asset sse event-group remove --asset mysseAsset --instance myInstance
            -g myInstanceResourceGroup --name alertEvents
    """

    helps[
        "iot ops ns asset sse event-group show"
    ] = """
        type: command
        short-summary: Show details of an event group for an SSE namespaced asset in an IoT Operations instance.

        examples:
        - name: Show event group details
          text: >
            az iot ops ns asset sse event-group show --asset mysseAsset --instance myInstance
            -g myInstanceResourceGroup --name alertEvents
    """

    helps[
        "iot ops ns asset sse event-group update"
    ] = """
        type: command
        short-summary: Update an event group for an SSE namespaced asset in an IoT Operations instance.

        examples:
        - name: Update event group data source
          text: >
            az iot ops ns asset sse event-group update --asset mysseAsset --instance myInstance
            -g myInstanceResourceGroup --name alertEvents --data-source "emergency-alert"

        - name: Update event group destination
          text: >
            az iot ops ns asset sse event-group update --asset mysseAsset --instance myInstance
            -g myInstanceResourceGroup --name systemEvents
            --dest topic="factory/sse/updated/system" retain=Never qos=Qos0 ttl=3600
    """

    helps[
        "iot ops ns asset sse event"
    ] = """
        type: group
        short-summary: Manage individual events for SSE event groups in Device Registry namespaces.
    """

    helps[
        "iot ops ns asset sse event add"
    ] = """
        type: command
        short-summary: Add an event to an SSE asset event group in a Device Registry namespace.

        examples:
        - name: Add a basic SSE event
          text: >
            az iot ops ns asset sse event add --asset mysseAsset --instance myInstance
            -g myInstanceResourceGroup --event-group alertEvents --name temperature --data-source "/events/temperature"

        - name: Add an SSE event with MQTT destination
          text: >
            az iot ops ns asset sse event add --asset mysseAsset --instance myInstance
            -g myInstanceResourceGroup --event-group alertEvents --name pressure --data-source "/events/pressure"
            --dest topic="factory/sse/pressure" retain=Keep qos=Qos1 ttl=3600

        - name: Replace an SSE event with same name
          text: >
            az iot ops ns asset sse event add --asset mysseAsset --instance myInstance
            -g myInstanceResourceGroup --event-group alertEvents --name temperature --data-source "/events/temperature/updated"
            --replace
    """

    helps[
        "iot ops ns asset sse event list"
    ] = """
        type: command
        short-summary: List events for an SSE asset event group in a Device Registry namespace.

        examples:
        - name: List all events for an event group
          text: >
            az iot ops ns asset sse event list --asset mysseAsset --instance myInstance
            -g myInstanceResourceGroup --event-group alertEvents
    """

    helps[
        "iot ops ns asset sse event remove"
    ] = """
        type: command
        short-summary: Remove an event from an SSE asset event group in a Device Registry namespace.

        examples:
        - name: Remove an event from an event group
          text: >
            az iot ops ns asset sse event remove --asset mysseAsset --instance myInstance
            -g myInstanceResourceGroup --event-group alertEvents --name temperature
    """

    # MQTT connector help
    helps[
        "iot ops ns asset mqtt"
    ] = """
        type: group
        short-summary: Manage namespaced assets that point to MQTT device endpoints.
    """

    helps[
        "iot ops ns asset mqtt create"
    ] = """
        type: command
        short-summary: Create an MQTT namespaced asset in an IoT Operations instance.

        examples:
        - name: Create a basic MQTT asset
          text: >
            az iot ops ns asset mqtt create --name myMqttAsset --instance myInstance -g myInstanceResourceGroup
            --device myMqttDevice --endpoint myMqttEndpoint

        - name: Create an MQTT asset with dataset destination
          text: >
            az iot ops ns asset mqtt create --name myMqttAsset --instance myInstance -g myInstanceResourceGroup
            --device myMqttDevice --endpoint myMqttEndpoint
            --dataset-dest topic="factory/mqtt/data" retain=Never qos=Qos1 ttl=3600

        - name: Create an MQTT asset with BrokerStateStore destination
          text: >
            az iot ops ns asset mqtt create --name myMqttAsset --instance myInstance -g myInstanceResourceGroup
            --device myMqttDevice --endpoint myMqttEndpoint
            --dataset-dest key="mqtt-data-cache"

        - name: Create an MQTT asset with metadata
          text: >
            az iot ops ns asset mqtt create --name myMqttAsset --instance myInstance -g myInstanceResourceGroup
            --device myMqttDevice --endpoint myMqttEndpoint --description "In-cluster MQTT topic subscriber"
            --display-name "Factory MQTT Stream" --model "MQTT-SUB-100" --manufacturer "BrokerCorp"
    """

    helps[
        "iot ops ns asset mqtt update"
    ] = """
        type: command
        short-summary: Update an MQTT namespaced asset in an IoT Operations instance.

        examples:
        - name: Update MQTT asset dataset destination
          text: >
            az iot ops ns asset mqtt update --name myMqttAsset --instance myInstance -g myInstanceResourceGroup
            --dataset-dest topic="updated/mqtt/data" retain=Keep qos=Qos1 ttl=7200

        - name: Update MQTT asset metadata
          text: >
            az iot ops ns asset mqtt update --name myMqttAsset --instance myInstance -g myInstanceResourceGroup
            --description "Updated MQTT topic subscriber"
    """

    helps[
        "iot ops ns asset mqtt dataset"
    ] = """
        type: group
        short-summary: Manage datasets for MQTT namespaced assets.
    """

    helps[
        "iot ops ns asset mqtt dataset add"
    ] = """
        type: command
        short-summary: Add a dataset to an MQTT namespaced asset in an IoT Operations instance.

        examples:
        - name: Add a dataset to an MQTT asset with MQTT topic
          text: >
            az iot ops ns asset mqtt dataset add --asset myMqttAsset --instance myInstance
            -g myInstanceResourceGroup --name sensorData --data-source "some/mqtt/topic"
            --dest topic="factory/processed/data" retain=Keep qos=Qos1 ttl=3600

        - name: Add a dataset with BrokerStateStore destination
          text: >
            az iot ops ns asset mqtt dataset add --asset myMqttAsset --instance myInstance
            -g myInstanceResourceGroup --name sensorData --data-source "some/mqtt/topic"
            --dest key="mqtt-data-store"
    """

    helps[
        "iot ops ns asset mqtt dataset list"
    ] = """
        type: command
        short-summary: List datasets for an MQTT namespaced asset in an IoT Operations instance.

        examples:
        - name: List all datasets for an MQTT asset
          text: >
            az iot ops ns asset mqtt dataset list --asset myMqttAsset --instance myInstance
            -g myInstanceResourceGroup
    """

    helps[
        "iot ops ns asset mqtt dataset remove"
    ] = """
        type: command
        short-summary: Remove a dataset from an MQTT namespaced asset in an IoT Operations instance.

        examples:
        - name: Remove a dataset from an MQTT asset
          text: >
            az iot ops ns asset mqtt dataset remove --asset myMqttAsset --instance myInstance
            -g myInstanceResourceGroup --name sensorData
    """

    helps[
        "iot ops ns asset mqtt dataset show"
    ] = """
        type: command
        short-summary: Show details of a dataset for an MQTT namespaced asset in an IoT Operations instance.

        examples:
        - name: Show dataset details
          text: >
            az iot ops ns asset mqtt dataset show --asset myMqttAsset --instance myInstance
            -g myInstanceResourceGroup --name sensorData
    """

    helps[
        "iot ops ns asset mqtt dataset update"
    ] = """
        type: command
        short-summary: Update a dataset for an MQTT namespaced asset in an IoT Operations instance.

        examples:
        - name: Update MQTT dataset destination
          text: >
            az iot ops ns asset mqtt dataset update --asset myMqttAsset --instance myInstance
            -g myInstanceResourceGroup --name sensorData
            --dest topic="updated/mqtt/topic" retain=Never qos=Qos0 ttl=1800
    """

    for asset_type in ["custom", "opcua", "rest", "sse", "mqtt"]:
        helps[
            f"iot ops ns asset {asset_type} dataset export"
        ] = """
            type: command
            short-summary: Export datasets to file.
            long-summary: Export all datasets from an asset to JSON or YAML format.
        """

        helps[
            f"iot ops ns asset {asset_type} dataset import"
        ] = """
            type: command
            short-summary: Import datasets from file.
            long-summary: Import datasets from JSON or YAML file. Use --replace to merge with overwrite.
        """

    for asset_type in ["custom", "opcua"]:
        helps[
            f"iot ops ns asset {asset_type} datapoint export"
        ] = """
            type: command
            short-summary: Export datapoints to file.
            long-summary: Export datapoints from a dataset to JSON, YAML, or CSV format.
        """

        helps[
            f"iot ops ns asset {asset_type} datapoint import"
        ] = """
            type: command
            short-summary: Import datapoints from file.
            long-summary: Import datapoints from JSON, YAML, or CSV file. Use --replace to merge with overwrite.
        """

    for asset_type in ["custom", "opcua", "onvif", "sse"]:
        helps[
            f"iot ops ns asset {asset_type} event-group export"
        ] = """
            type: command
            short-summary: Export event-groups to file.
            long-summary: Export all event-groups from an asset to JSON or YAML format.
        """

        helps[
            f"iot ops ns asset {asset_type} event-group import"
        ] = """
            type: command
            short-summary: Import event-groups from file.
            long-summary: Import event-groups from JSON or YAML file. Use --replace to merge with overwrite.
        """

    for asset_type in ["custom", "opcua", "onvif", "sse"]:
        helps[
            f"iot ops ns asset {asset_type} event export"
        ] = """
            type: command
            short-summary: Export events to file.
            long-summary: Export events from an event-group to JSON, YAML, or CSV format.
        """

        helps[
            f"iot ops ns asset {asset_type} event import"
        ] = """
            type: command
            short-summary: Import events from file.
            long-summary: Import events from JSON, YAML, or CSV file. Use --replace to merge with overwrite.
        """

    for asset_type in ["custom", "media"]:
        helps[
            f"iot ops ns asset {asset_type} stream export"
        ] = f"""
            type: command
            short-summary: Export streams to file.
            long-summary: Export all streams from an asset to JSON or YAML format.
                Destinations are stripped on export and auto-assigned on import.
            examples:
            - name: Export streams to JSON.
              text: >
                az iot ops ns asset {asset_type} stream export -a myasset --instance myinstance -g myresourcegroup
            - name: Export streams to YAML in a specific directory.
              text: >
                az iot ops ns asset {asset_type} stream export -a myasset --instance myinstance -g myresourcegroup -f yaml --od /path/to/output
        """

        helps[
            f"iot ops ns asset {asset_type} stream import"
        ] = f"""
            type: command
            short-summary: Import streams from file.
            long-summary: Import streams from JSON or YAML file. Use --replace to merge with overwrite.
                Destinations are auto-assigned from asset defaults if not specified in the file.
            examples:
            - name: Import streams from JSON file.
              text: >
                az iot ops ns asset {asset_type} stream import -a myasset --instance myinstance -g myresourcegroup --if /path/to/streams.json
            - name: Import streams with replace mode.
              text: >
                az iot ops ns asset {asset_type} stream import -a myasset --instance myinstance -g myresourcegroup --if /path/to/streams.json --replace
        """

    for asset_type in ["custom", "opcua", "onvif"]:
        helps[
            f"iot ops ns asset {asset_type} mgmt-group export"
        ] = f"""
            type: command
            short-summary: Export management groups to file.
            long-summary: Export all management groups from an asset to JSON or YAML format.
                Actions are not included in the export (use mgmt-action export separately).
            examples:
            - name: Export management groups to JSON.
              text: >
                az iot ops ns asset {asset_type} mgmt-group export -a myasset --instance myinstance -g myresourcegroup
            - name: Export management groups to YAML.
              text: >
                az iot ops ns asset {asset_type} mgmt-group export -a myasset --instance myinstance -g myresourcegroup -f yaml
        """

        helps[
            f"iot ops ns asset {asset_type} mgmt-group import"
        ] = f"""
            type: command
            short-summary: Import management groups from file.
            long-summary: Import management groups from JSON or YAML file. Use --replace to merge with overwrite.
                Existing actions are preserved when merging management groups.
            examples:
            - name: Import management groups from JSON file.
              text: >
                az iot ops ns asset {asset_type} mgmt-group import -a myasset --instance myinstance -g myresourcegroup --if /path/to/mgmt_groups.json
            - name: Import management groups with replace mode.
              text: >
                az iot ops ns asset {asset_type} mgmt-group import -a myasset --instance myinstance -g myresourcegroup --if /path/to/mgmt_groups.yaml --replace
        """

    for asset_type in ["custom", "opcua"]:
        helps[
            f"iot ops ns asset {asset_type} mgmt-action export"
        ] = f"""
            type: command
            short-summary: Export management actions to file.
            long-summary: Export actions from a management group to JSON, YAML, or CSV format.
            examples:
            - name: Export actions to CSV.
              text: >
                az iot ops ns asset {asset_type} mgmt-action export -a myasset --instance myinstance -g myresourcegroup --group mygroup -f csv
            - name: Export actions to JSON.
              text: >
                az iot ops ns asset {asset_type} mgmt-action export -a myasset --instance myinstance -g myresourcegroup --group mygroup
        """

        helps[
            f"iot ops ns asset {asset_type} mgmt-action import"
        ] = f"""
            type: command
            short-summary: Import management actions from file.
            long-summary: Import actions from JSON, YAML, or CSV file. Use --replace to merge with overwrite.
                Default actionType is 'Call' if not specified.
            examples:
            - name: Import actions from CSV file.
              text: >
                az iot ops ns asset {asset_type} mgmt-action import -a myasset --instance myinstance -g myresourcegroup --group mygroup --if /path/to/actions.csv
            - name: Import actions with replace mode.
              text: >
                az iot ops ns asset {asset_type} mgmt-action import -a myasset --instance myinstance -g myresourcegroup --group mygroup --if /path/to/actions.json --replace
        """
