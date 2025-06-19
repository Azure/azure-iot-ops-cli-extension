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
        long-summary: For more information on asset management, please see aka.ms/asset-overview
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
        long-summary: A dataset will be created once a point is created. See `az iot ops asset dataset point add` for more details.
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
    """

    helps[
        "iot ops asset dataset point add"
    ] = """
        type: command
        short-summary: Add a data point to an asset dataset.
        long-summary: If no datasets exist yet, this will create a new dataset. Currently, only one dataset is supported with the name "default".

        examples:
        - name: Add a data point to an asset.
          text: >
            az iot ops asset dataset point add --asset myasset -g myresourcegroup --dataset default --data-source mydatasource --name data1

        - name: Add a data point to an asset with data point name, observability mode, custom queue size,
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
        short-summary: Remove a data point in an asset dataset.

        examples:
        - name: Remove a data point from an asset via the data point name.
          text: >
            az iot ops asset dataset point remove --asset myasset -g myresourcegroup --dataset default --name data1
    """

    helps[
        "iot ops asset event"
    ] = """
        type: group
        short-summary: Manage events in an asset.
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
    """

    helps[
        "iot ops asset endpoint create"
    ] = """
        type: group
        short-summary: Create asset endpoint profiles.
    """

    helps[
        "iot ops asset endpoint create custom"
    ] = """
        type: command
        short-summary: Create an asset endpoint profile for a custom connector.
        examples:
        - name: Create an asset endpoint with anonymous user authentication using the given instance in the same resource group.
          text: >
            az iot ops asset endpoint create custom --name myprofile -g myresourcegroup --instance myinstance
            --target-address http://rest-server-service.azure-iot-operations.svc.cluster.local:80 --endpoint-type rest-thermostat
        - name: Create an asset endpoint with username-password user authentication using the given instance in a different resource group but same subscription. The additional
                configuration is provided as an inline json.
          text: >
            az iot ops asset endpoint create custom --name myprofile -g myresourcegroup --instance myinstance
            --instance-resource-group myinstanceresourcegroup
            --target-address http://rest-server-service.azure-iot-operations.svc.cluster.local:80 --endpoint-type rest-thermostat
            --username-ref rest-server-auth-creds/username --password-ref rest-server-auth-creds/password
            --additional-config addition_configuration.json
        - name: Create an asset endpoint with certificate authentication using the given instance in the same resource group.
          text: >
            az iot ops asset endpoint create custom --name myprofile -g myresourcegroup --instance myinstance
            --target-address http://rest-server-service.azure-iot-operations.svc.cluster.local:80 --endpoint-type rest-thermostat
            --certificate-ref mycertificate.pem
        - name: Create an asset endpoint with anonymous user authentication using the given instance in the same resource group. The inline content is a bash syntax example. For more examples, see https://aka.ms/inline-json-examples
          text: >
            az iot ops asset endpoint create custom --name myprofile -g myresourcegroup --instance myinstance
            --target-address http://rest-server-service.azure-iot-operations.svc.cluster.local:80 --endpoint-type rest-thermostat
            --additional-config '{"displayName": "myconnector", "maxItems": 100}'
    """

    helps[
        "iot ops asset endpoint create onvif"
    ] = """
        type: command
        short-summary: Create an asset endpoint profile for an Onvif connector.
        long-summary: |
                      Certificate authentication is not supported yet for Onvif Connectors.

                      For more information on how to create an Onvif connector, please see https://aka.ms/onvif-quickstart
        examples:
        - name: Create an asset endpoint with anonymous user authentication using the given instance in the same resource group.
          text: >
            az iot ops asset endpoint create onvif --name myprofile -g myresourcegroup --instance myinstance
            --target-address http://onvif-rtsp-simulator:8000
        - name: Create an asset endpoint with username-password user authentication using the given instance in a different resource group but same subscription.
          text: >
            az iot ops asset endpoint create onvif --name myprofile -g myresourcegroup --instance myinstance
            --instance-resource-group myinstanceresourcegroup
            --target-address http://onvif-rtsp-simulator:8000
            --username-ref rest-server-auth-creds/username --password-ref rest-server-auth-creds/password
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

                      For more information on how to configure asset endpoints for the OPC UA connector, please see https://aka.ms/opcua-quickstart
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
            az iot ops ns create -n myNamespace -g myResourceGroup

        - name: Create a namespace with custom location and tags
          text: >
            az iot ops ns create -n myNamespace -g myResourceGroup
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
            az iot ops ns delete -n myNamespace -g myResourceGroup
    """

    helps[
        "iot ops ns show"
    ] = """
        type: command
        short-summary: Show details of a Device Registry namespace.

        examples:
        - name: Show details of a namespace
          text: >
            az iot ops ns show -n myNamespace -g myResourceGroup
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
            az iot ops ns update -n myNamespace -g myResourceGroup --tags env=test department=iot
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
            az iot ops ns device create --name myDevice --namespace myNamespace -g myResourceGroup
            --instance myInstance --template-id "dtmi:sample:device;1"

        - name: Create a device with custom attributes and device group
          text: >
            az iot ops ns device create --name myDevice --namespace myNamespace -g myResourceGroup
            --instance myInstance --template-id "dtmi:sample:device;1"
            --device-group-id "critical-devices" --attr location=building1 floor=3

        - name: Create a device with manufacturer information and operating system details
          text: >
            az iot ops ns device create --name myDevice --namespace myNamespace -g myResourceGroup
            --instance myInstance --template-id "dtmi:sample:device;1"
            --manufacturer "Contoso" --model "Gateway X1" --os "Linux" --os-version "4.15"

        - name: Create a disabled device with tags
          text: >
            az iot ops ns device create --name myDevice --namespace myNamespace -g myResourceGroup
            --instance myInstance --template-id "dtmi:sample:device;1"
            --disabled --tags environment=test criticality=low
    """

    helps[
        "iot ops ns device list"
    ] = """
        type: command
        short-summary: List devices in a Device Registry namespace.

        examples:
        - name: List all devices in a namespace
          text: >
            az iot ops ns device list --namespace myNamespace -g myResourceGroup
    """

    helps[
        "iot ops ns device show"
    ] = """
        type: command
        short-summary: Show details of a device in a Device Registry namespace.

        examples:
        - name: Show details of a device
          text: >
            az iot ops ns device show --name myDevice --namespace myNamespace -g myResourceGroup
    """

    helps[
        "iot ops ns device delete"
    ] = """
        type: command
        short-summary: Delete a device from a Device Registry namespace.

        examples:
        - name: Delete a device
          text: >
            az iot ops ns device delete --name myDevice --namespace myNamespace -g myResourceGroup
    """

    helps[
        "iot ops ns device update"
    ] = """
        type: command
        short-summary: Update a device in a Device Registry namespace.

        examples:
        - name: Update device custom attributes
          text: >
            az iot ops ns device update --name myDevice --namespace myNamespace -g myResourceGroup
            --attr location=building2 floor=5

        - name: Move device to a different device group and update operating system version
          text: >
            az iot ops ns device update --name myDevice --namespace myNamespace -g myResourceGroup
            --device-group-id "maintenance-devices" --os-version "4.18"

        - name: Disable a device
          text: >
            az iot ops ns device update --name myDevice --namespace myNamespace -g myResourceGroup
            --disabled

        - name: Update device tags
          text: >
            az iot ops ns device update --name myDevice --namespace myNamespace -g myResourceGroup
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
            az iot ops ns device endpoint list --device myDevice --namespace myNamespace -g myResourceGroup
        - name: List only inbound endpoints of a device
          text: >
            az iot ops ns device endpoint list --device myDevice --namespace myNamespace -g myResourceGroup --inbound
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
            az iot ops ns device endpoint inbound list --device myDevice --namespace myNamespace -g myResourceGroup
    """

    helps[
        "iot ops ns device endpoint inbound remove"
    ] = """
        type: command
        short-summary: Remove inbound endpoints from a device in a Device Registry namespace.

        examples:
        - name: Remove a single inbound endpoint from a device
          text: >
            az iot ops ns device endpoint inbound remove --device myDevice --namespace myNamespace -g myResourceGroup --endpoint myEndpoint

        - name: Remove multiple inbound endpoints from a device
          text: >
            az iot ops ns device endpoint inbound remove --device myDevice --namespace myNamespace -g myResourceGroup --endpoint myEndpoint1 myEndpoint2
    """

    helps[
        "iot ops ns device endpoint inbound add"
    ] = """
        type: group
        short-summary: Add inbound endpoints to devices in Device Registry namespaces.
    """

    # TODO: this is pretty long for a command name - debate on if I should throw out inbound
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
            az iot ops ns device endpoint inbound add custom --device myDevice --namespace myNamespace -g myResourceGroup --name myCustomEndpoint --endpoint-type "Custom.Type" --endpoint-address "192.168.1.100:8080"

        - name: Add a custom endpoint with authentication
          text: >
            az iot ops ns device endpoint inbound add custom --device myDevice --namespace myNamespace -g myResourceGroup --name myCustomEndpoint --endpoint-type "Custom.Type" --endpoint-address "192.168.1.100:8080" --user-ref "secretRef:username" --pass-ref "secretRef:password"

        - name: Add a custom endpoint with certificate authentication
          text: >
            az iot ops ns device endpoint inbound add custom --device myDevice --namespace myNamespace -g myResourceGroup --name myCustomEndpoint --endpoint-type "Custom.Type" --endpoint-address "192.168.1.100:8080" --cert-ref "secretRef:certificate"

        - name: Add a custom endpoint with additional configuration
          text: >
            az iot ops ns device endpoint inbound add custom --device myDevice --namespace myNamespace -g myResourceGroup --name myCustomEndpoint --endpoint-type "Custom.Type" --endpoint-address "192.168.1.100:8080" --additional-config "{\\\"customSetting\\\": \\\"value\\\"}"
    """

    helps[
        "iot ops ns device endpoint inbound add media"
    ] = """
        type: command
        short-summary: Add a media inbound endpoint to a device in a Device Registry namespace.
        long-summary: |
          Media endpoints are used for media streaming devices like cameras.

        examples:
        - name: Add a basic media endpoint to a device
          text: >
            az iot ops ns device endpoint inbound add media --device myDevice --namespace myNamespace -g myResourceGroup --name myCameraEndpoint --endpoint-address "rtsp://192.168.1.100:554/stream"

        - name: Add a media endpoint with authentication
          text: >
            az iot ops ns device endpoint inbound add media --device myDevice --namespace myNamespace -g myResourceGroup --name myCameraEndpoint --endpoint-address "rtsp://192.168.1.100:554/stream" --user-ref "secretRef:username" --pass-ref "secretRef:password"
    """

    helps[
        "iot ops ns device endpoint inbound add onvif"
    ] = """
        type: command
        short-summary: Add an ONVIF inbound endpoint to a device in a Device Registry namespace.
        long-summary: |
          ONVIF endpoints are used for devices that support the ONVIF standard protocol.

        examples:
        - name: Add a basic ONVIF endpoint to a device
          text: >
            az iot ops ns device endpoint inbound add onvif --device myDevice --namespace myNamespace -g myResourceGroup --name myONVIFEndpoint --endpoint-address "http://192.168.1.100:8000/onvif/device_service"

        - name: Add an ONVIF endpoint with authentication
          text: >
            az iot ops ns device endpoint inbound add onvif --device myDevice --namespace myNamespace -g myResourceGroup --name myONVIFEndpoint --endpoint-address "http://192.168.1.100:8000/onvif/device_service" --user-ref "secretRef:username" --pass-ref "secretRef:password"

        - name: Add an ONVIF endpoint that accepts invalid hostnames and certificates
          text: >
            az iot ops ns device endpoint inbound add onvif --device myDevice --namespace myNamespace -g myResourceGroup --name myONVIFEndpoint --endpoint-address "https://192.168.1.100:8000/onvif/device_service" --accept-invalid-hostnames --accept-invalid-certificates
    """

    helps[
        "iot ops ns device endpoint inbound add opcua"
    ] = """
        type: command
        short-summary: Add an OPC UA inbound endpoint to a device in a Device Registry namespace.
        long-summary: |
          OPC UA endpoints are used for industrial automation devices that support the OPC UA protocol.

        examples:
        - name: Add a basic OPC UA endpoint to a device
          text: >
            az iot ops ns device endpoint inbound add opcua --device myDevice --namespace myNamespace -g myResourceGroup --name myOPCUAEndpoint --endpoint-address "opc.tcp://192.168.1.100:4840"

        - name: Add an OPC UA endpoint with authentication
          text: >
            az iot ops ns device endpoint inbound add opcua --device myDevice --namespace myNamespace -g myResourceGroup --name myOPCUAEndpoint --endpoint-address "opc.tcp://192.168.1.100:4840" --user-ref "secretRef:username" --pass-ref "secretRef:password"

        - name: Add an OPC UA endpoint with a custom application name
          text: >
            az iot ops ns device endpoint inbound add opcua --device myDevice --namespace myNamespace -g myResourceGroup --name myOPCUAEndpoint --endpoint-address "opc.tcp://192.168.1.100:4840" --application-name "My OPC UA App"

        - name: Add an OPC UA endpoint with customized session parameters
          text: >
            az iot ops ns device endpoint inbound add opcua --device myDevice --namespace myNamespace -g myResourceGroup --name myOPCUAEndpoint --endpoint-address "opc.tcp://192.168.1.100:4840" --keep-alive 15000 --session-timeout 90000 --publishing-interval 2000 --sampling-interval 1500

        - name: Add an OPC UA endpoint with security settings and asset discovery enabled
          text: >
            az iot ops ns device endpoint inbound add opcua --device myDevice --namespace myNamespace -g myResourceGroup --name myOPCUAEndpoint --endpoint-address "opc.tcp://192.168.1.100:4840" --security-policy "Basic256Sha256" --security-mode "SignAndEncrypt" --run-asset-discovery
    """

    helps[
        "iot ops ns asset"
    ] = """
        type: group
        short-summary: Manage assets in Device Registry namespaces.
    """

    helps[
        "iot ops ns asset create"
    ] = """
        type: group
        short-summary: Create assets in Device Registry namespaces.
    """

    helps[
        "iot ops ns asset create custom"
    ] = """
        type: command
        short-summary: Create a custom asset in a Device Registry namespace.

        examples:
        - name: Create a basic custom asset
          text: >
            az iot ops ns asset create custom --name myCustomAsset --namespace myNamespace -g myResourceGroup
            --device myDevice --endpoint-name myEndpoint

        - name: Create a custom asset with additional metadata
          text: >
            az iot ops ns asset create custom --name myCustomAsset --namespace myNamespace -g myResourceGroup
            --device myDevice --endpoint-name myEndpoint --description "Factory sensor" --display-name "Temperature Sensor"
            --model "TempSensor-X1" --manufacturer "Contoso" --serial-number "SN12345"

        - name: Create a custom asset with dataset and events configuration using inline JSON
          text: >
            az iot ops ns asset create custom --name myCustomAsset --namespace myNamespace -g myResourceGroup
            --device myDevice --endpoint-name myEndpoint --dataset-config "{\\\"publishingInterval\\\": 1000}"
            --event-config "{\\\"queueSize\\\": 5}"

        - name: Create a custom asset with datasets use a BrokerStateStore destination, events use a Mqtt destination, and streams use a Storage destination.
          text: >
            az iot ops ns asset create custom --name myCustomAsset --namespace myNamespace -g myResourceGroup
            --device myDevice --endpoint-name myEndpoint
            --dataset-dest key="myKey"
            --event-dest topic="factory/events/temperature/updated" qos=2 retain=false ttl=3600
            --stream-dest path="my/storage/path"
    """

    helps[
        "iot ops ns asset create media"
    ] = """
        type: command
        short-summary: Create a media asset in a Device Registry namespace.
        long-summary: The device endpoint must be of type Microsoft.Media.

        examples:
        - name: Create a basic media asset
          text: >
            az iot ops ns asset create media --name myCameraAsset --namespace myNamespace -g myResourceGroup
            --device myCamera --endpoint-name myCameraEndpoint

        - name: Create a media asset for MQTT snapshots with an MQTT destination
          text: >
            az iot ops ns asset create media --name myCameraAsset --namespace myNamespace -g myResourceGroup
            --device myCamera --endpoint-name myCameraEndpoint --task-type snapshot-to-mqtt
            --task-format jpeg --snapshots-per-sec 1
            --stream-dest topic="factory/cameras/snapshots" qos=1 retain=false ttl=60

        - name: Create a media asset for file system snapshots
          text: >
            az iot ops ns asset create media --name myCameraAsset --namespace myNamespace -g myResourceGroup
            --device myCamera --endpoint-name myCameraEndpoint --task-type snapshot-to-fs
            --task-format png --snapshots-per-sec 5 --path "/data/snapshots"

        - name: Create a media asset for file system clips
          text: >
            az iot ops ns asset create media --name myCameraAsset --namespace myNamespace -g myResourceGroup
            --device myCamera --endpoint-name myCameraEndpoint --task-type clip-to-fs
            --task-format mp4 --duration 300 --path "/data/clips"

        - name: Create a media asset for RTSP streaming
          text: >
            az iot ops ns asset create media --name myCameraAsset --namespace myNamespace -g myResourceGroup
            --device myCamera --endpoint-name myCameraEndpoint --task-type stream-to-rtsp
            --media-server-address "media-server.media-server.svc.cluster.local"
            --media-server-port 8554 --media-server-path "myCamera/stream"
    """

    helps[
        "iot ops ns asset create onvif"
    ] = """
        type: command
        short-summary: Create an ONVIF asset in a Device Registry namespace.
        long-summary: The device endpoint must be of type Microsoft.Onvif.

        examples:
        - name: Create a basic ONVIF asset
          text: >
            az iot ops ns asset create onvif --name myOnvifAsset --namespace myNamespace -g myResourceGroup
            --device myCamera --endpoint-name myOnvifEndpoint

        - name: Create an ONVIF asset with additional metadata
          text: >
            az iot ops ns asset create onvif --name myOnvifAsset --namespace myNamespace -g myResourceGroup
            --device myCamera --endpoint-name myOnvifEndpoint --description "Surveillance Camera"
            --display-name "Entry Camera" --model "SecureCam Pro" --manufacturer "SecurityCo"
            --serial-number "CAM-12345" --documentation-uri "https://example.com/docs/camera"

        - name: Create an ONVIF asset with custom attributes
          text: >
            az iot ops ns asset create onvif --name myOnvifAsset --namespace myNamespace -g myResourceGroup
            --device myCamera --endpoint-name myOnvifEndpoint --attribute location=entrance
            --attribute resolution=1080p --attribute ptz=true
    """

    helps[
        "iot ops ns asset create opcua"
    ] = """
        type: command
        short-summary: Create an OPC UA asset in a Device Registry namespace.
        long-summary: The device endpoint must be of type Microsoft.OpcUa.

        examples:
        - name: Create a basic OPC UA asset
          text: >
            az iot ops ns asset create opcua --name myOpcuaAsset --namespace myNamespace -g myResourceGroup
            --device myOpcuaDevice --endpoint-name myOpcuaEndpoint

        - name: Create an OPC UA asset with dataset configuration
          text: >
            az iot ops ns asset create opcua --name myOpcuaAsset --namespace myNamespace -g myResourceGroup
            --device myOpcuaDevice --endpoint-name myOpcuaEndpoint --dataset-publish-int 1000
            --dataset-sampling-int 500 --dataset-queue-size 5 --dataset-key-frame-count 1
            --dataset-start-inst "ns=1;i=1234"

        - name: Create an OPC UA asset with event configuration
          text: >
            az iot ops ns asset create opcua --name myOpcuaAsset --namespace myNamespace -g myResourceGroup
            --device myOpcuaDevice --endpoint-name myOpcuaEndpoint --event-publish-int 2000
            --event-queue-size 10 --event-start-inst "ns=1;i=5678"
            --event-filter-clause path="ns=1;i=1000" type="String" field="Temperature"

        - name: Create an OPC UA asset with MQTT destinations for datasets and events
          text: >
            az iot ops ns asset create opcua --name myOpcuaAsset --namespace myNamespace -g myResourceGroup
            --device myOpcuaDevice --endpoint-name myOpcuaEndpoint
            --dataset-dest topic="factory/opcua/data" retain=true qos=1 ttl=3600
            --event-dest topic="factory/opcua/events" retain=false qos=1 ttl=3600
    """

    helps[
        "iot ops ns asset update"
    ] = """
        type: group
        short-summary: Update assets in Device Registry namespaces.
    """

    helps[
        "iot ops ns asset update custom"
    ] = """
        type: command
        short-summary: Update a custom asset in a Device Registry namespace.

        examples:
        - name: Update a custom asset's basic properties
          text: >
            az iot ops ns asset update custom --name myCustomAsset --namespace myNamespace -g myResourceGroup
            --description "Updated factory sensor" --display-name "Temperature Sensor v2"

        - name: Update a custom asset with additional metadata
          text: >
            az iot ops ns asset update custom --name myCustomAsset --namespace myNamespace -g myResourceGroup
            --model "TempSensor-X2" --manufacturer "Contoso" --serial-number "SN98765" --disable

        - name: Update a custom asset's dataset and events configuration
          text: >
            az iot ops ns asset update custom --name myCustomAsset --namespace myNamespace -g myResourceGroup
            --dataset-config "{\\\"publishingInterval\\\": 2000}" --event-config "{\\\"queueSize\\\": 10}"

        - name: Update a custom asset's destinations so the datasets use a BrokerStateStore destination, events use a Mqtt destination, and streams use a Storage destination.
          text: >
            az iot ops ns asset update custom --name myCustomAsset --namespace myNamespace -g myResourceGroup
            --dataset-dest key="myKey"
            --event-dest topic="factory/events/temperature/updated" qos=2 retain=false ttl=3600
            --stream-dest path="my/storage/path"

        - name: Update a custom asset's custom attributes
          text: >
            az iot ops ns asset update custom --name myCustomAsset --namespace myNamespace -g myResourceGroup
            --attribute location=building2 floor=3 zone=production
    """

    helps[
        "iot ops ns asset update media"
    ] = """
        type: command
        short-summary: Update a media asset in a Device Registry namespace.
        long-summary: The device endpoint must be of type Microsoft.Media.

        examples:
        - name: Update a media asset's basic properties
          text: >
            az iot ops ns asset update media --name myCameraAsset --namespace myNamespace -g myResourceGroup
            --description "Updated surveillance camera" --display-name "Entry Camera HD"

        - name: Change a media asset from MQTT snapshots to file system snapshots
          text: >
            az iot ops ns asset update media --name myCameraAsset --namespace myNamespace -g myResourceGroup
            --task-type snapshot-to-fs --task-format png --path "/data/snapshots/hd"

        - name: Update a media asset's clip configuration
          text: >
            az iot ops ns asset update media --name myCameraAsset --namespace myNamespace -g myResourceGroup
            --task-type clip-to-fs --duration 600 --path "/data/clips/extended"

        - name: Update a media asset's RTSP streaming configuration
          text: >
            az iot ops ns asset update media --name myCameraAsset --namespace myNamespace -g myResourceGroup
            --task-type stream-to-rtsp --media-server-address "new-media-server.local"
            --media-server-port 8555 --media-server-path "cameras/main/stream"

        - name: Update a media asset's destination and metadata
          text: >
            az iot ops ns asset update media --name myCameraAsset --namespace myNamespace -g myResourceGroup
            --stream-dest topic="security/cameras/main" qos=1 retain=false ttl=300
            --manufacturer "SecureCam Inc." --model "HD-8000" --serial-number "CAM9876"
    """

    helps[
        "iot ops ns asset update onvif"
    ] = """
        type: command
        short-summary: Update an ONVIF asset in a Device Registry namespace.
        long-summary: The device endpoint must be of type Microsoft.Onvif.

        examples:
        - name: Update an ONVIF asset's basic properties
          text: >
            az iot ops ns asset update onvif --name myOnvifAsset --namespace myNamespace -g myResourceGroup
            --description "Updated surveillance camera" --display-name "Main Entrance Camera"

        - name: Update an ONVIF asset's metadata
          text: >
            az iot ops ns asset update onvif --name myOnvifAsset --namespace myNamespace -g myResourceGroup
            --model "SecureCam Pro X1" --manufacturer "SecurityCo" --serial-number "CAM-67890"
            --documentation-uri "https://example.com/docs/camera/v2"

        - name: Update an ONVIF asset's custom attributes
          text: >
            az iot ops ns asset update onvif --name myOnvifAsset --namespace myNamespace -g myResourceGroup
            --attribute location=main-entrance resolution=4K ptz=true night-vision=true

        - name: Disable an ONVIF asset and update its reference information
          text: >
            az iot ops ns asset update onvif --name myOnvifAsset --namespace myNamespace -g myResourceGroup
            --disable --external-asset-id "CAM-MAIN-01" --hardware-revision "v2.1"
    """

    helps[
        "iot ops ns asset update opcua"
    ] = """
        type: command
        short-summary: Update an OPC UA asset in a Device Registry namespace.
        long-summary: The device endpoint must be of type Microsoft.OpcUa.

        examples:
        - name: Update an OPC UA asset's basic properties
          text: >
            az iot ops ns asset update opcua --name myOpcuaAsset --namespace myNamespace -g myResourceGroup
            --description "Updated factory PLC" --display-name "Production Line Controller"

        - name: Update an OPC UA asset's dataset configuration
          text: >
            az iot ops ns asset update opcua --name myOpcuaAsset --namespace myNamespace -g myResourceGroup
            --dataset-publish-int 500 --dataset-sampling-int 250
            --dataset-queue-size 10 --dataset-key-frame-count 2

        - name: Update an OPC UA asset's event configuration
          text: >
            az iot ops ns asset update opcua --name myOpcuaAsset --namespace myNamespace -g myResourceGroup
            --event-publish-int 1000 --event-queue-size 5
            --event-filter-clause path="ns=1;i=2000" type="String" field="Alarm"

        - name: Update an OPC UA asset's destination configurations
          text: >
            az iot ops ns asset update opcua --name myOpcuaAsset --namespace myNamespace -g myResourceGroup
            --dataset-dest topic="factory/opcua/data/updated" retain=true qos=1 ttl=7200
            --event-dest topic="factory/opcua/events/updated" retain=false qos=1 ttl=3600

        - name: Update an OPC UA asset's metadata and attributes
          text: >
            az iot ops ns asset update opcua --name myOpcuaAsset --namespace myNamespace -g myResourceGroup
            --manufacturer "Automation Corp" --model "PLC-2000" --serial-number "PLC87654"
            --attribute location=factory-floor zone="production line"
    """

    helps[
        "iot ops ns asset delete"
    ] = """
        type: command
        short-summary: Delete an asset from a Device Registry namespace.

        examples:
        - name: Delete an asset with confirmation prompt
          text: >
            az iot ops ns asset delete --name myAsset --namespace myNamespace -g myResourceGroup

        - name: Delete an asset and skip the confirmation prompt
          text: >
            az iot ops ns asset delete --name myAsset --namespace myNamespace -g myResourceGroup -y
    """

    helps[
        "iot ops ns asset query"
    ] = """
        type: command
        short-summary: Query assets in Device Registry namespaces.
        long-summary: |
          Query assets across namespaces based on various search criteria including asset name,
          device name, endpoint name and more.

        examples:
        - name: Query for a specific asset by name
          text: >
            az iot ops ns asset query --name myAsset -g myResourceGroup

        - name: Query for assets associated with a specific device and endpoint
          text: >
            az iot ops ns asset query --device myDevice --endpoint-name myEndpoint -g myResourceGroup

        - name: Use a custom query to search for assets
          text: >
            az iot ops ns asset query --custom-query "where tags.environment=='production'" -g myResourceGroup
    """

    helps[
        "iot ops ns asset show"
    ] = """
        type: command
        short-summary: Show details of an asset in a Device Registry namespace.

        examples:
        - name: Show details of an asset
          text: >
            az iot ops ns asset show --name myAsset --namespace myNamespace -g myResourceGroup
    """
