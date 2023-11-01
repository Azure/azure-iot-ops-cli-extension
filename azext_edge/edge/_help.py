# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------
"""
Help definitions for Digital Twins commands.
"""

from knack.help_files import helps
from .providers.edge_api import E4K_ACTIVE_API
from .providers.support_bundle import (
    COMPAT_DATA_PROCESSOR_APIS,
    COMPAT_E4K_APIS,
    COMPAT_LNM_APIS,
    COMPAT_OPCUA_APIS,
    COMPAT_SYMPHONY_APIS,
    COMPAT_DEVICEREGISTRY_APIS
)


def load_iotedge_help():
    helps[
        "iot ops"
    ] = """
        type: group
        short-summary: Manage AIO resources.
        long-summary: |
            Azure IoT Operations (AIO) is a set of highly aligned, but loosely coupled, first-party
            Kubernetes services that enable you to aggregate data from on-prem assets into an
            industrial-grade MQTT Broker, add edge compute and set up bi-directional data flow with
            a variety of services in the cloud.
    """

    helps[
        "iot ops support"
    ] = """
        type: group
        short-summary: Edge support operations.
    """

    helps[
        "iot ops support create-bundle"
    ] = f"""
        type: command
        short-summary: Creates a standard support bundle zip archive for use in troubleshooting and diagnostics.
        long-summary: |
            [Supported edge service APIs]
                {COMPAT_E4K_APIS.as_str()}
                {COMPAT_OPCUA_APIS.as_str()}
                {COMPAT_DATA_PROCESSOR_APIS.as_str()}
                {COMPAT_SYMPHONY_APIS.as_str()}
                {COMPAT_LNM_APIS.as_str()}
                {COMPAT_DEVICEREGISTRY_APIS.as_str()}
    """

    helps[
        "iot ops check"
    ] = f"""
        type: command
        short-summary: Evaluate AIO edge service deployments for health, configuration and usability.
        long-summary: |
            [Supported edge service APIs]
                {E4K_ACTIVE_API.as_str()}
    """

    helps[
        "iot ops mq"
    ] = """
        type: group
        short-summary: MQ specific tools.
    """

    helps[
        "iot ops mq stats"
    ] = f"""
        type: command
        short-summary: Show dmqtt running statistics.
        long-summary: |
            [Supported edge service APIs]
                {E4K_ACTIVE_API.as_str()}
    """

    helps[
        "iot ops mq get-password-hash"
    ] = """
        type: command
        short-summary: Generates a PBKDF2 hash of the passphrase applying PBKDF2-HMAC-SHA512. A 128-bit salt is used from os.urandom.
    """

    helps[
        "iot ops init"
    ] = """
        type: command
        short-summary: Bootstrap, configure and deploy AIO to the target cluster.
        long-summary: |
            After this operation completes the desired suite of AIO edge services will
            be deployed with baseline configuration on the target cluster.
    """

    helps[
        "iot ops asset"
    ] = """
        type: group
        short-summary: Manage assets.
    """

    helps[
        "iot ops asset create"
    ] = """
        type: command
        short-summary: Create an asset.
        long-summary: |
                      Either custom location or cluster name must be provided. This command will check
                      for the existance of the associated custom location and cluster and ensure that
                      both are set up correctly with the microsoft.deviceregistry.assets extension.

        examples:
        - name: Create an asset using the given custom location.
          text: >
            az iot ops asset create --asset {asset} -g {resource_group} --custom-location {custom_location}
            --endpoint {endpoint}

        - name: Create an asset using the given custom location and resource group for the custom location. The resource group
                must be included if there are multiple custom locations with the same name within a subscription.
          text: >
            az iot ops asset create --asset {asset} -g {resource_group} --custom-location {custom_location}
            --custom-location-resource-group {custom_location_resource_group} --endpoint {endpoint}

        - name: Create an asset using the given cluster name. The resource group must be included if there are multiple clusters
                with the same name within a subscription.
          text: >
            az iot ops asset create --asset {asset} -g {resource_group} --cluster {cluster} --cluster-resource-group {cluster_resource_group}
            --endpoint {endpoint}

        - name: Create an asset using the given cluster name and custom location.
          text: >
            az iot ops asset create --asset {asset} -g {resource_group} --cluster {cluster}
            --custom-location {custom_location} --endpoint {endpoint}

        - name: Create an asset with custom data point and event defaults.
          text: >
            az iot ops asset create --asset {asset} -g {resource_group} --custom-location {custom_location}
            --endpoint {endpoint} --data-publish-int {data_point_publishing_interval}
            --data-queue-size {data_point_queue_size} --data-sample-int {data_point_sampling_interval}
            --event-publish-int {event_publishing_interval} --event-queue-size {event_queue_size}
            --event-sample-int {event_sampling_interval}

        - name: Create an asset with custom asset type, description, documentation uri, external asset id, hardware revision,
                product code, and software revision.
          text: >
            az iot ops asset create --asset {asset} -g {resource_group} --custom-location {custom_location}
            --endpoint {endpoint} --asset-type {asset_type} --description {description}
            --documentation-uri {documentation_uri} --external-asset-id {external_asset_id} --hardware-revision {hardware_revision}
            --product-code {product_code} --software-revision {software_revision}

        - name: Create an asset with two events, manufacturer, manufacturer uri, model, serial number.
          text: >
            az iot ops asset create --asset {asset} -g {resource_group} --custom-location {custom_location}
            --endpoint {endpoint} --event capability_id={capability_id} event_notifier={event_notifier}
            name={name} observability_mode={observability_mode} sampling_interval={sampling_interval} queue_size={queue_size}
            --event event_notifier={event_notifier} --manufacturer {manufacturer} --manufacturer-uri {manufacturer_uri} --model {model}
            --serial-number {serial_number}

        - name: Create a disabled asset with two data points.
          text: >
            az iot ops asset create --asset {asset} -g {resource_group} --custom-location {custom_location}
            --endpoint {endpoint} --disable --data capability_id={capability_id}
            data_source={data_source} name={name} observability_mode={observability_mode} sampling_interval={sampling_interval}
            queue_size={queue_size} --data data_source={data_source}

        - name: Create an asset with the given pre-filled values.
          text: >
            az iot ops asset create --asset MyAsset -g MyRg --custom-location MyLocation --endpoint example.com
            --data capability_id=myTagId data_source=nodeId1 name=myTagName1
            observability_mode=counter sampling_interval=10 queue_size=2 --data
            data_source=nodeId2 --data-publish-int 1000 --data-queue-size 1 --data-sample-int 30
            --asset-type customAsset --description 'Description for a test asset.'
            --documentation-uri www.help.com --external-asset-id 000-000-0000 --hardware-revision 10.0
            --product-code XXX100 --software-revision 0.1 --manufacturer Contoso
            --manufacturer-uri constoso.com --model AssetModel --serial-number 000-000-ABC10
    """

    helps[
        "iot ops asset list"
    ] = """
        type: command
        short-summary: List assets.

        examples:
        - name: List all assets in the current subscription.
          text: >
            az iot ops asset list

        - name: List all assets in a resource group.
          text: >
            az iot ops asset list -g {resource_group}
    """

    helps[
        "iot ops asset query"
    ] = """
        type: command
        short-summary: Query the Resource Graph for assets.

        examples:
        - name: Query for assets that are disabled within a given resource group.
          text: >
            az iot ops asset query -g {resource_group} --disabled
        - name: Query for assets that have the given model, manufacturer, and serial number.
          text: >
            az iot ops asset query --model {model} --manufacturer {manufacturer} --serial-number {serial_number}
    """

    helps[
        "iot ops asset show"
    ] = """
        type: command
        short-summary: Show an asset.

        examples:
        - name: Show the details of an asset.
          text: >
            az iot ops asset show --asset {asset} -g {resource_group}
    """

    helps[
        "iot ops asset update"
    ] = """
        type: command
        short-summary: Update an asset.
        long-summary: To update data points and events, please use the command groups `az iot ops asset data-point` and
            `az iot ops asset events` respectively.

        examples:
        - name: Update an asset's data point and event defaults.
          text: >
            az iot ops asset update --asset {asset} -g {resource_group} --data-publish-int {data_point_publishing_interval}
            --data-queue-size {data_point_queue_size} --data-sample-int {data_point_sampling_interval}
            --event-publish-int {event_publishing_interval} --event-queue-size {event_queue_size}
            --event-sample-int {event_sampling_interval}

        - name: Update an asset's asset type, description, documentation uri, external asset id, hardware revision, product code,
                and software revision.
          text: >
            az iot ops asset update --asset {asset} -g {resource_group} --asset-type {asset_type} --description {description}
            --documentation-uri {documentation_uri} --external-asset-id {external_asset_id} --hardware-revision {hardware_revision}
            --product-code {product_code} --software-revision {software_revision}

        - name: Update an asset's manufacturer, manufacturer uri, model, serial number.
          text: >
            az iot ops asset update --asset {asset} -g {resource_group} --manufacturer {manufacturer} --manufacturer-uri {manufacturer_uri} --model {model}
            --serial-number {serial_number}

        - name: Disable an asset.
          text: >
            az iot ops asset update --asset {asset} -g {resource_group} --disable
    """

    helps[
        "iot ops asset delete"
    ] = """
        type: command
        short-summary: Delete an asset.
        examples:
        - name: Delete an asset.
          text: >
            az iot ops asset delete --asset {asset} -g {resource_group}
    """

    helps[
        "iot ops asset data-point"
    ] = """
        type: group
        short-summary: Manage data points in an asset.
    """

    helps[
        "iot ops asset data-point add"
    ] = """
        type: command
        short-summary: Add a data point to an asset.

        examples:
        - name: Add a data point to an asset.
          text: >
            az iot ops asset data-point add --asset {asset} -g {resource_group} --data-source {data_source}

        - name: Add a data point to an asset with capability id, data point name, observability mode, custom queue size,
                and custom sampling interval.
          text: >
            az iot ops asset data-point add --asset {asset} -g {resource_group} --data-source {data_source} --data-point-name
            {data_point_name} --capability-id {capability_id} --observability-mode {observability_mode} --queue-size
            {queue_size} --sampling-interval {sampling_interval}

        - name: Add a data point to an asset with the given pre-filled values.
          text: >
            az iot ops asset data-point add --asset MyAsset -g MyRG --data-source nodeId1 --data-point-name tagName1
            --capability-id tagId1 --observability-mode log --queue-size 5 --sampling-interval 200
    """

    helps[
        "iot ops asset data-point list"
    ] = """
        type: command
        short-summary: List data points in an asset.
        examples:
        - name: List all data-points in an asset.
          text: >
            az iot ops asset data-point list --asset {asset} -g {resource_group}
    """

    helps[
        "iot ops asset data-point remove"
    ] = """
        type: command
        short-summary: Remove a data point in an asset.

        examples:
        - name: Remove a data point from an asset via the data source.
          text: >
            az iot ops asset data-point remove --asset {asset} -g {resource_group} --data-source {data_source}

        - name: Remove a data point from an asset via the data point name.
          text: >
            az iot ops asset data-point remove --asset {asset} -g {resource_group} --data-point-name {data_point_name}
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
            az iot ops asset event add --asset {asset} -g {resource_group} --event-notifier {event_notifier}

        - name: Add an event to an asset with capability id, event name, observability mode, custom queue size,
                and custom sampling interval.
          text: >
            az iot ops asset event add --asset {asset} -g {resource_group} --event-notifier {event_notifier}
            --event-name {event_name} --capability-id {capability_id} --observability-mode
            {observability_mode} --queue-size {queue_size} --sampling-interval {sampling_interval}

        - name: Add an event to an asset with the given pre-filled values.
          text: >
            az iot ops asset event add --asset MyAsset -g MyRG --event-notifier eventId --event-name eventName
            --capability-id tagId1 --observability-mode histogram --queue-size 2 --sampling-interval 500
    """

    helps[
        "iot ops asset event list"
    ] = """
        type: command
        short-summary: List events in an asset.

        examples:
        - name: List all events in an asset.
          text: >
            az iot ops asset event list --asset {asset} -g {resource_group}
    """

    helps[
        "iot ops asset event remove"
    ] = """
        type: command
        short-summary: Remove an event in an asset.

        examples:
        - name: Remove an event from an asset via the event notifier.
          text: >
            az iot ops asset event remove --asset {asset} -g {resource_group} --event-notifier {event_notifier}

        - name: Remove an event from an asset via the event name.
          text: >
            az iot ops asset event remove --asset {asset} -g {resource_group} --event-name {event_name}
    """
