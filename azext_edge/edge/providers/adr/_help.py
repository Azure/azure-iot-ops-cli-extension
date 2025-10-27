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
        short-summary: Add a datapoint to an asset dataset.
        long-summary: If no datasets exist yet, this will create a new dataset. Currently, only one dataset is supported with the name "default".

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
        "iot ops ns device endpoint inbound add"
    ] = """
        type: group
        short-summary: Add inbound endpoints to devices in Device Registry namespaces.
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
        long-summary: Currently, only one dataset with the name "default" is supported for assets.
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
    """

    helps[
        "iot ops ns asset opcua dataset"
    ] = """
        type: group
        short-summary: Manage datasets for OPC UA namespaced assets in an IoT Operations instance.
        long-summary: Currently, only one dataset with the name "default" is supported for assets.
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
            --name myManagementGroup --data-source mydatasource

        - name: Add a management group with default topic and timeout.
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
        long-summary: Currently, only one dataset with the name "default" is supported for assets.
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
