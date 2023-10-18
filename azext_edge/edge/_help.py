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
from .providers.support_bundle import COMPAT_BLUEFIN_APIS, COMPAT_E4K_APIS, COMPAT_OPCUA_APIS, COMPAT_SYMPHONY_APIS


def load_iotedge_help():
    helps[
        "edge"
    ] = """
        type: group
        short-summary: Manage PAS resources.
        long-summary: |
            Project Alice Springs (PAS) is a set of highly aligned, but loosely coupled, first-party
            Kubernetes services that enable you to aggregate data from on-prem assets into an
            industrial-grade MQTT Broker, add edge compute and set up bi-directional data flow with
            a variety of services in the cloud.
    """

    helps[
        "edge support"
    ] = """
        type: group
        short-summary: Edge service support operations.
    """

    helps[
        "edge support create-bundle"
    ] = f"""
        type: command
        short-summary: Creates a standard support bundle zip archive for use in troubleshooting and diagnostics.
        long-summary: |
            [Supported edge service APIs]
                {COMPAT_E4K_APIS.as_str()}
                {COMPAT_OPCUA_APIS.as_str()}
                {COMPAT_BLUEFIN_APIS.as_str()}
                {COMPAT_SYMPHONY_APIS.as_str()}
    """

    helps[
        "edge check"
    ] = f"""
        type: command
        short-summary: Evaluate PAS edge service deployments for health, configuration and usability.
        long-summary: |
            [Supported edge service APIs]
                {E4K_ACTIVE_API.as_str()}
    """

    helps[
        "edge e4k"
    ] = """
        type: group
        short-summary: E4K specific tools.
    """

    helps[
        "edge e4k stats"
    ] = f"""
        type: command
        short-summary: Show dmqtt running statistics.
        long-summary: |
            [Supported edge service APIs]
                {E4K_ACTIVE_API.as_str()}
    """

    helps[
        "edge e4k get-password-hash"
    ] = """
        type: command
        short-summary: Generates a PBKDF2 hash of the passphrase applying PBKDF2-HMAC-SHA512. A 128-bit salt is used from os.urandom.
    """

    helps[
        "edge init"
    ] = """
        type: command
        short-summary: Initialize and deploy a PAS service bundle to the target cluster.
        long-summary: |
            After this operation completes the desired suite of PAS edge services will
            be deployed with baseline configuration on the target cluster. Deployment is done incrementally.

            Customize deployable PAS version via --pas-version or --custom-version.
    """

    helps[
        "edge asset"
    ] = """
        type: group
        short-summary: Manage assets.
    """

    helps[
        "edge asset create"
    ] = """
        type: command
        short-summary: Create an asset.
        long-summary: |
                      Custom location or cluster name can be provided. This command will check for the
                      existance of the associated custom location and cluster and ensure that both are
                      set up correctly with the microsoft.deviceregistry.assets extension.

        examples:
        - name: Create an asset using the given custom location.
          text: >
            az edge asset create -n {asset_name} -g {resource_group} --custom-location {custom_location}
            --endpoint {endpoint}

        - name: Create an asset using the given custom location and resource group for the custom location. The resource group
                should be included if there are multiple custom locations with the same name within a subscription.
          text: >
            az edge asset create -n {asset_name} -g {resource_group} --custom-location {custom_location}
            --custom-location-resource-group {custom_location_resource_group} --endpoint {endpoint}

        - name: Create an asset using the given cluster name. The resource group should be included if there are multiple clusters
                with the same name within a subscription.
          text: >
            az edge asset create -n {asset_name} -g {resource_group} --cluster {cluster} --cluster-resource-group {cluster_resource_group}
            --endpoint {endpoint}

        - name: Create an asset using the given cluster name and custom location.
          text: >
            az edge asset create -n {asset_name} -g {resource_group} --cluster {cluster}
            --custom-location {custom_location} --endpoint {endpoint}

        - name: Create an asset with custom data point and event defaults.
          text: >
            az edge asset create -n {asset_name} -g {resource_group} --custom-location {custom_location}
            --endpoint {endpoint} --data-point-publishing-interval {data_point_publishing_interval}
            --data-point-queue-size {data_point_queue_size} --data-point-sampling-interval {data_point_sampling_interval}
            --event-publishing-interval {event_publishing_interval} --event-queue-size {event_queue_size}
            --event-sampling-interval {event_sampling_interval}

        - name: Create an asset with custom asset type, description, documentation uri, external asset id, hardware revision,
                product code, and software revision.
          text: >
            az edge asset create -n {asset_name} -g {resource_group} --custom-location {custom_location}
            --endpoint {endpoint} --asset-type {asset_type} --description {description}
            --documentation-uri {documentation_uri} --external-asset-id {external_asset_id} --hardware-revision {hardware_revision}
            --product-code {product_code} --software-revision {software_revision}

        - name: Create an asset with two events, manufacturer, manufacturer uri, model, serial number. This asset will have two events.
          text: >
            az edge asset create -n {asset_name} -g {resource_group} --custom-location {custom_location}
            --endpoint {endpoint} --event capability_id={capability_id} event_notifier={event_notifier}
            name={name} observability_mode={observability_mode} sampling_interval={sampling_interval} queue_size={queue_size}
            --event event_notifier={event_notifier} --manufacturer {manufacturer} --manufacturer-uri {manufacturer_uri} --model {model}
            --serial-number {serial_number}

        - name: Create a disabled asset with two data points.
          text: >
            az edge asset create -n {asset_name} -g {resource_group} --custom-location {custom_location}
            --endpoint {endpoint} --disable --data-point capability_id={capability_id}
            data_source={data_source} name={name} observability_mode={observability_mode} sampling_interval={sampling_interval}
            queue_size={queue_size} --data-point data_source={data_source}

        - name: Create an asset with the given pre-filled values.
          text: >
            az edge asset create -n MyAsset -g MyRg --custom-location MyLocation --endpoint example.com --data-point
            capability_id=myTagId data_source=nodeId1 name=myTagName1 observability_mode=counter sampling_interval=10
            queue_size=2 --data-point data_source=nodeId2 --data-point-publishing-interval 1000 --data-point-queue-size 1
            --data-point-sampling-interval 30 --asset-type customAsset --description 'Description for a test asset.'
            --documentation-uri www.help.com --external-asset-id 000-000-0000 --hardware-revision 10.0 --product-code XXX100
            --software-revision 0.1 --manufacturer Contoso --manufacturer-uri constoso.com --model AssetModel
            --serial-number 000-000-ABC10
    """

    helps[
        "edge asset list"
    ] = """
        type: command
        short-summary: List assets.

        examples:
        - name: List all assets in the current subscription.
          text: >
            az edge asset list

        - name: List all assets in a resource group.
          text: >
            az edge asset list -g {resource_group}
    """

    helps[
        "edge asset query"
    ] = """
        type: command
        short-summary: Query the Resource Graph for assets.

        examples:
        - name: Query for assets that are disabled within a given resource group.
          text: >
            az edge asset query -g {resource_group} --disabled
        - name: Query for assets that have the given model, manufacturer, and serial number.
          text: >
            az edge asset query --model {model} --manufacturer {manufacturer} --serial-number {serial_number}
    """

    helps[
        "edge asset show"
    ] = """
        type: command
        short-summary: Show an asset.

        examples:
        - name: Show the details of an asset.
          text: >
            az edge asset show -n {asset_name} -g {resource_group}
    """

    helps[
        "edge asset update"
    ] = """
        type: command
        short-summary: Update an asset.
        long-summary: To update data points and events, please use the command groups `az edge asset data-point` and
            `az edge asset events` respectively.

        examples:
        - name: Update an asset's data point and event defaults.
          text: >
            az edge asset update -n {asset_name} -g {resource_group} --data-point-publishing-interval {data_point_publishing_interval}
            --data-point-queue-size {data_point_queue_size} --data-point-sampling-interval {data_point_sampling_interval}
            --event-publishing-interval {event_publishing_interval} --event-queue-size {event_queue_size}
            --event-sampling-interval {event_sampling_interval}

        - name: Update an asset's asset type, description, documentation uri, external asset id, hardware revision, product code,
                and software revision.
          text: >
            az edge asset update -n {asset_name} -g {resource_group} --asset-type {asset_type} --description {description}
            --documentation-uri {documentation_uri} --external-asset-id {external_asset_id} --hardware-revision {hardware_revision}
            --product-code {product_code} --software-revision {software_revision}

        - name: Update an asset's manufacturer, manufacturer uri, model, serial number.
          text: >
            az edge asset update -n {asset_name} -g {resource_group} --manufacturer {manufacturer} --manufacturer-uri {manufacturer_uri} --model {model}
            --serial-number {serial_number}

        - name: Disable an asset.
          text: >
            az edge asset update -n {asset_name} -g {resource_group} --disable
    """

    helps[
        "edge asset delete"
    ] = """
        type: command
        short-summary: Delete an asset.
        examples:
        - name: Delete an asset.
          text: >
            az edge asset delete -n {asset_name} -g {resource_group}
    """

    helps[
        "edge asset data-point"
    ] = """
        type: group
        short-summary: Manage data points in an asset.
    """

    helps[
        "edge asset data-point add"
    ] = """
        type: command
        short-summary: Add a data point to an asset.

        examples:
        - name: Add a data point to an asset.
          text: >
            az edge asset data-point add -n {asset_name} -g {resource_group} --data-source {data_source}

        - name: Add a data point to an asset with capability id, data point name, observability mode, custom queue size,
                and custom sampling interval.
          text: >
            az edge asset data-point add -n {asset_name} -g {resource_group} --data-source {data_source} --data-point-name
            {data_point_name} --capability-id {capability_id} --observability-mode {observability_mode} --queue-size
            {queue_size} --sampling-interval {sampling_interval}

        - name: Add a data point to an asset with the given pre-filled values.
          text: >
            az edge asset data-point add -n MyAsset -g MyRG --data-source nodeId1 --data-point-name tagName1
            --capability-id tagId1 --observability-mode log --queue-size 5 --sampling-interval 200
    """

    helps[
        "edge asset data-point list"
    ] = """
        type: command
        short-summary: List data points in an asset.
        examples:
        - name: List all data-points in an asset.
          text: >
            az edge asset data-point list -n {asset_name} -g {resource_group}
    """

    helps[
        "edge asset data-point remove"
    ] = """
        type: command
        short-summary: Remove a data point in an asset.

        examples:
        - name: Remove a data point from an asset via the data source.
          text: >
            az edge asset data-point remove -n {asset_name} -g {resource_group} --data-source {data_source}

        - name: Remove a data point from an asset via the data point name.
          text: >
            az edge asset data-point remove -n {asset_name} -g {resource_group} --data-point-name {data_point_name}
    """

    helps[
        "edge asset event"
    ] = """
        type: group
        short-summary: Manage events in an asset.
    """

    helps[
        "edge asset event add"
    ] = """
        type: command
        short-summary: Add an event to an asset.

        examples:
        - name: Add an event to an asset.
          text: >
            az edge asset event add -n {asset_name} -g {resource_group} --event-notifier {event_notifier}

        - name: Add an event to an asset with capability id, event name, observability mode, custom queue size,
                and custom sampling interval.
          text: >
            az edge asset event add -n {asset_name} -g {resource_group} --event-notifier {event_notifier}
            --event-name {event_name} --capability-id {capability_id} --observability-mode
            {observability_mode} --queue-size {queue_size} --sampling-interval {sampling_interval}

        - name: Add an event to an asset with the given pre-filled values.
          text: >
            az edge asset event add -n myAsset -g myRG --event-notifier eventId --event-name eventName
            --capability-id tagId1 --observability-mode histogram --queue-size 2 --sampling-interval 500
    """

    helps[
        "edge asset event list"
    ] = """
        type: command
        short-summary: List events in an asset.

        examples:
        - name: List all events in an asset.
          text: >
            az edge asset event list -n {asset_name} -g {resource_group}
    """

    helps[
        "edge asset event remove"
    ] = """
        type: command
        short-summary: Remove an event in an asset.

        examples:
        - name: Remove an event from an asset via the event notifier.
          text: >
            az edge asset event remove -n {asset_name} -g {resource_group} --event-notifier {event_notifier}

        - name: Remove an event from an asset via the event name.
          text: >
            az edge asset event remove -n {asset_name} -g {resource_group} --event-name {event_name}
    """
