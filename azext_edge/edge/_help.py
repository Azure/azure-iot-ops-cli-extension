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
            az edge asset create -n {asset_name} -g {resouce_group} --custom-location {custom_location}
            --endpoint-profile {endpoint_profile}

        - name: Create an asset using the given custom location and resource group for the custom location. The resource group should be included if there are multiple custom locations with the same name within a subscription.
          text: >
            az edge asset create -n {asset_name} -g {resouce_group} --custom-location {custom_location}
            --custom-location-resource-group {custom_location_resource_group}--endpoint-profile {endpoint_profile}

        - name: Create an asset using the given cluster name.  The resource group should be included if there are multiple clusters with the same name within a subscription.
          text: >
            az edge asset create -n {asset_name} -g {resouce_group} --cluster-name {cluster_name}
            --endpoint-profile {endpoint_profile}

        - name: Create an asset using the given cluster name. Note that if multiple custom locations are associated with the cluster, the first custom location will be picked.
          text: >
            az edge asset create -n {asset_name} -g {resouce_group} --cluster-name {cluster_name}
            --endpoint-profile {endpoint_profile}

        - name: Create an asset using the given cluster name and custom location.
          text: >
            az edge asset create -n {asset_name} -g {resouce_group} --cluster-name {cluster_name}
            --custom-location {custom_location}

        - name: Create an asset with custom data point and event defaults.
          text: >
            az edge asset create -n {asset_name} -g {resouce_group} --custom-location {custom_location}
            --endpoint-profile {endpoint_profile} --data-point-publishing-interval {data_point_publishing_interval}
            --data-point-queue-size {data_point_queue_size} --data-point-sampling-interval {data_point_sampling_interval}
            --event-publishing-interval {event_publishing_interval} --event-queue-size {event_queue_size}
            --event-sampling-interval {event_sampling_interval}

        - name: Create an asset with custom asset type, description, documentation uri, external asset id, hardware revision,
                product code, and software revision.
          text: >
            az edge asset create -n {asset_name} -g {resouce_group} --custom-location {custom_location}
            --endpoint-profile {endpoint_profile} --asset-type {asset_type} --description {description}
            --documentation-uri {documentation_uri} --external-asset-id {external_asset_id} --hardware-revision {hardware_revision}
            --product-code {product_code} --software-revision {software_revision}

        - name: Create an asset with two events, manufacturer, manufacturer uri, model, serial number. This asset will have two events.
          text: >
            az edge asset create -n {asset_name} -g {resouce_group} --custom-location {custom_location}
            --endpoint-profile {endpoint_profile} --event 'capability_id'={capability_id} 'event_notifier'={event_notifier}
            'name'={name} 'observability_mode'={observability_mode} 'sampling_interval'={sampling_interval} 'queue_size'={queue_size}
            --event 'event_notifier'={event_notifier} --manufacturer {manufacturer} --manufacturer-uri {manufacturer_uri} --model {model}
            --serial-number {serial_number}

        - name: Create a disabled asset with two data points.
          text: >
            az edge asset create -n {asset_name} -g {resouce_group} --custom-location {custom_location}
            --endpoint-profile {endpoint_profile} --disabled --data-point 'capability_id'={capability_id}
            'data_source'={data_source} 'name'={name} 'observability_mode'={observability_mode} 'sampling_interval'={sampling_interval}
            'queue_size'={queue_size} --data-point 'data_source'={data_source}
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
            az edge asset list -g {resouce_group}
    """

    helps[
        "edge asset query"
    ] = """
        type: command
        short-summary: Query the Resource Graph for assets.

        examples:
        - name: Query for assets that are disabled within a given resource group.
          text: >
            az edge asset query -g {resouce_group} --enabled False
        - name: Query for assets that have the given model, manufacturer, and serial number.
          text: >
            az edge asset query --model {model} --manufacturer {manufacturer} --serial-number {serial_number}
    """

    helps[
        "edge asset show"
    ] = """
        type: command
        short-summary: Show an asset.
        long-summary: If there are multiple assets with the same name within a subscription, please provide the
            resource group to ensure the correct asset is shown.

        examples:
        - name: Show the details of an asset.
          text: >
            az edge asset show -n {asset_name} -g {resouce_group}
    """

    helps[
        "edge asset update"
    ] = """
        type: command
        short-summary: Update an asset.
        long-summary: If there are multiple assets with the same name within a subscription, please provide the
            resource group to ensure the correct asset is updated.

        examples:
        - name: Update an asset's data point and event defaults.
          text: >
            az edge asset update -n {asset_name} -g {resouce_group} --data-point-publishing-interval {data_point_publishing_interval}
            --data-point-queue-size {data_point_queue_size} --data-point-sampling-interval {data_point_sampling_interval}
            --event-publishing-interval {event_publishing_interval} --event-queue-size {event_queue_size}
            --event-sampling-interval {event_sampling_interval}

        - name: Update an asset's asset type, description, documentation uri, external asset id, hardware revision, product code,
                and software revision.
          text: >
            az edge asset update -n {asset_name} -g {resouce_group} --asset-type {asset_type} --description {description}
            --documentation-uri {documentation_uri} --external-asset-id {external_asset_id} --hardware-revision {hardware_revision}
            --product-code {product_code} --software-revision {software_revision}

        - name: Update an asset's events, manufacturer, manufacturer uri, model, serial number. This will overwrite the events
                with the two given events.
          text: >
            az edge asset update -n {asset_name} -g {resouce_group} --event 'capability_id'={capability_id} 'event_notifier'={event_notifier}
            'name'={name} 'observability_mode'={observability_mode} 'sampling_interval'={sampling_interval} 'queue_size'={queue_size}
            --event 'event_notifier'={event_notifier} --manufacturer {manufacturer} --manufacturer-uri {manufacturer_uri} --model {model}
            --serial-number {serial_number}

        - name: Disable an asset and update it's data points. This will overwrite the data points with the two given data points.
          text: >
            az edge asset update -n {asset_name} -g {resouce_group} --disabled --data-point 'capability_id'={capability_id}
            'data_source'={data_source} 'name'={name} 'observability_mode'={observability_mode} 'sampling_interval'={sampling_interval}
            'queue_size'={queue_size} --data-point 'data_source'={data_source}
    """

    helps[
        "edge asset delete"
    ] = """
        type: command
        short-summary: Delete an asset.
        long-summary: If there are multiple assets with the same name within a subscription, please provide the
            resource group to ensure the correct asset is deleted.
        examples:
        - name: Delete an asset.
          text: >
            az edge asset delete -n {asset_name} -g {resouce_group}
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
        long-summary: If there are multiple assets with the same name within a subscription, please provide the
            resource group to ensure the correct asset is retrieved.
            To modify multiple data points at once, please use `az edge asset update` instead.

        examples:
        - name: Add a data point to an asset.
          text: >
            az edge asset data-point add -n {asset_name} -g {resouce_group} --data-source {data_source}

        - name: Add a data point to an asset with capability id, data point name, observability mode, custom queue size,
                and custom sampling interval.
          text: >
            az edge asset data-point add -n {asset_name} -g {resouce_group} --data-source {data_source} --data-point-name
            {data_point_name} --capability-id {capability_id} --observability-mode {observability_mode} --queue-size
            {queue_size} --sampling-interval {sampling_interval}
    """

    helps[
        "edge asset data-point list"
    ] = """
        type: command
        short-summary: List data points in an asset.
        long-summary: If there are multiple assets with the same name within a subscription, please provide the
            resource group to ensure the correct asset is retrieved.
        examples:
        - name: List all data-points in an asset.
          text: >
            az edge asset data-point list -n {asset_name} -g {resouce_group}
    """

    helps[
        "edge asset data-point remove"
    ] = """
        type: command
        short-summary: Remove a data point in an asset.
        long-summary: If there are multiple assets with the same name within a subscription, please provide the
            resource group to ensure the correct asset is retrieved.

            To modify multiple data points at once, please use `az edge asset update` instead.

        examples:
        - name: Remove a data point from an asset via the data source.
          text: >
            az edge asset data-point remove -n {asset_name} -g {resouce_group} --data-source {data_source}

        - name: Remove a data point from an asset via the data point name.
          text: >
            az edge asset data-point remove -n {asset_name} -g {resouce_group} --data-point-name {data_point_name}
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
        long-summary: If there are multiple assets with the same name within a subscription, please provide the
            resource group to ensure the correct asset is retrieved.
            To modify multiple events at once, please use `az edge asset update` instead.

        examples:
        - name: Add an event to an asset.
          text: >
            az edge asset event add -n {asset_name} -g {resouce_group} --event-notifier {event_notifier}

        - name: Add an event to an asset with capability id, event name, observability mode, custom queue size,
                and custom sampling interval.
          text: >
            az edge asset event add -n {asset_name} -g {resouce_group} --event-notifier {event_notifier}
            --event-name {event_name} --capability-id {capability_id} --observability-mode
            {observability_mode} --queue-size {queue_size} --sampling-interval {sampling_interval}
    """

    helps[
        "edge asset event list"
    ] = """
        type: command
        short-summary: List events in an asset.
        long-summary: If there are multiple assets with the same name within a subscription, please provide the
            resource group to ensure the correct asset is retrieved.

        examples:
        - name: List all events in an asset.
          text: >
            az edge asset event list -n {asset_name} -g {resouce_group}
    """

    helps[
        "edge asset event remove"
    ] = """
        type: command
        short-summary: Remove an event in an asset.
        long-summary: If there are multiple assets with the same name within a subscription, please provide the
            resource group to ensure the correct asset is retrieved.

            To modify multiple events at once, please use `az edge asset update` instead.

        examples:
        - name: Remove an event from an asset via the event notifier.
          text: >
            az edge asset event remove -n {asset_name} -g {resouce_group} --event-notifier {event_notifier}

        - name: Remove an event from an asset via the event name.
          text: >
            az edge asset event remove -n {asset_name} -g {resouce_group} --event-name {event_name}
    """
