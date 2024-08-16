# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------
"""
Help definitions for Digital Twins commands.
"""

from knack.help_files import helps

from .providers.edge_api import MQ_ACTIVE_API
from .providers.support_bundle import (
    COMPAT_AKRI_APIS,
    COMPAT_CLUSTER_CONFIG_APIS,
    COMPAT_DEVICEREGISTRY_APIS,
    COMPAT_MQTT_BROKER_APIS,
    COMPAT_OPCUA_APIS,
    COMPAT_ORC_APIS,
    COMPAT_DATAFLOW_APIS,
)


def load_iotops_help():
    helps[
        "iot ops"
    ] = """
        type: group
        short-summary: Manage Azure IoT Operations.
        long-summary: |
            Azure IoT Operations is a set of highly aligned, but loosely coupled, first-party
            Kubernetes services that enable you to aggregate data from on-prem assets into an
            industrial-grade MQTT Broker, add edge compute and set up bi-directional data flow with
            a variety of services in the cloud.

            By default IoT Operations CLI commands will periodically check to see if a new extension version is available.
            This behavior can be disabled with `az config set iotops.check_latest=false`.
    """

    helps[
        "iot ops support"
    ] = """
        type: group
        short-summary: IoT Operations support command space.
    """

    helps[
        "iot ops support create-bundle"
    ] = f"""
        type: command
        short-summary: Creates a standard support bundle zip archive for use in troubleshooting and diagnostics.
        long-summary: |
            {{Supported service APIs}}
            - {COMPAT_MQTT_BROKER_APIS.as_str()}
            - {COMPAT_OPCUA_APIS.as_str()}
            - {COMPAT_ORC_APIS.as_str()}
            - {COMPAT_AKRI_APIS.as_str()}
            - {COMPAT_DEVICEREGISTRY_APIS.as_str()}
            - {COMPAT_CLUSTER_CONFIG_APIS.as_str()}
            - {COMPAT_DATAFLOW_APIS.as_str()}

            Note: logs from evicted pod will not be captured, as they are inaccessible. For details
            on why a pod was evicted, please refer to the related pod and node files.

        examples:
        - name: Basic usage with default options. This form of the command will auto detect IoT Operations APIs and build a suitable bundle
                capturing the last 24 hours of container logs. The bundle will be produced in the current working directory.
          text: >
            az iot ops support create-bundle

        - name: Constrain data capture on a specific service as well as producing the bundle in a custom output dir.
          text: >
            az iot ops support create-bundle --ops-service opcua --bundle-dir ~/ops

        - name: Specify a custom container log age in seconds.
          text: >
            az iot ops support create-bundle --ops-service broker --log-age 172800

        - name: Include mqtt broker traces in the support bundle. This is an alias for stats trace fetch capability.
          text: >
            az iot ops support create-bundle --ops-service broker --broker-traces
    """

    helps[
        "iot ops check"
    ] = f"""
        type: command
        short-summary: Evaluate cluster-side runtime health of deployed IoT Operations services.
        long-summary: |
            The command by default shows a human friendly _summary_ view of the selected service.
            More detail can be requested via `--detail-level`.

            {{Supported service APIs}}
            - {COMPAT_AKRI_APIS.as_str()}
            - {COMPAT_DEVICEREGISTRY_APIS.as_str()}
            - {COMPAT_MQTT_BROKER_APIS.as_str()}
            - {COMPAT_OPCUA_APIS.as_str()}

            For more information on cluster requirements, please check https://aka.ms/iot-ops-cluster-requirements

        examples:
        - name: Basic usage. Checks `broker` health with summary output.
          text: >
            az iot ops check

        - name: Evaluates `broker` like prior example, however output is optimized for CI.
          text: >
            az iot ops check --as-object

        - name: Checks `opcua` health and configuration with detailed output.
          text: >
            az iot ops check --svc opcua --detail-level 1

        - name: Checks 'deviceregistry' health, but constrains results to `asset` resources.
          text: >
            az iot ops check --svc deviceregistry --detail-level 1 --resources asset

        - name: Use resource name to constrain results to `asset` resources with `my-asset-` name prefix
          text: >
            az iot ops check --svc deviceregistry --resources asset --resource-name 'my-asset-*'
    """

    helps[
        "iot ops broker"
    ] = """
        type: group
        short-summary: Mqtt broker management and operations.
    """

    helps[
        "iot ops broker stats"
    ] = f"""
        type: command
        short-summary: Show dmqtt running statistics.
        long-summary: |
            {{Supported service APIs}}
            - {MQ_ACTIVE_API.as_str()}

        examples:
        - name: Fetch key performance indicators from the diagnostics Prometheus metrics endpoint.
          text: >
            az iot ops broker stats

        - name: Same as prior example except with a dynamic display that refreshes periodically.
          text: >
            az iot ops broker stats --watch

        - name: Return the raw output of the metrics endpoint with minimum processing.
          text: >
            az iot ops broker stats --raw

        - name: Fetch all available mq traces from the diagnostics Protobuf endpoint.
                This will produce a `.zip` with both `Otel` and Grafana `tempo` file formats.
                A trace files last modified attribute will match the trace timestamp.
          text: >
            az iot ops broker stats --trace-dir .

        - name: Fetch traces by trace Ids provided in space-separated hex format. Only `Otel` format is shown.
          text: >
            az iot ops broker stats --trace-ids 4e84000155a98627cdac7de46f53055d
    """

    helps[
        "iot ops broker show"
    ] = """
        type: command
        short-summary: Show details of an mqtt broker.

        examples:
        - name: Show details of the default broker 'broker' in the instance 'mycluster-ops-instance'.
          text: >
            az iot ops broker show -n broker --in mycluster-ops-instance -g myresourcegroup
    """

    helps[
        "iot ops broker list"
    ] = """
        type: command
        short-summary: List mqtt brokers associated with an instance.

        examples:
        - name: Enumerate all brokers in the instance 'mycluster-ops-instance'.
          text: >
            az iot ops broker list --in mycluster-ops-instance -g myresourcegroup
    """

    helps[
        "iot ops broker listener"
    ] = """
        type: group
        short-summary: Broker listener management.
    """

    helps[
        "iot ops broker listener show"
    ] = """
        type: command
        short-summary: Show details of an mqtt broker listener.

        examples:
        - name: Show details of the default listener 'listener' associated with the default broker.
          text: >
            az iot ops broker listener show -n listener -b broker --in mycluster-ops-instance -g myresourcegroup
    """

    helps[
        "iot ops broker listener list"
    ] = """
        type: command
        short-summary: List mqtt broker listeners associated with a broker.

        examples:
        - name: Enumerate all broker listeners associated with the default broker.
          text: >
            az iot ops broker listener list -b broker --in mycluster-ops-instance -g myresourcegroup
    """

    helps[
        "iot ops broker authn"
    ] = """
        type: group
        short-summary: Broker authentication management.
    """

    helps[
        "iot ops broker authn show"
    ] = """
        type: command
        short-summary: Show details of an mqtt broker authentication resource.

        examples:
        - name: Show details of the default broker authentication resource 'authn' associated with the default broker.
          text: >
            az iot ops broker authn show -n authn -b broker --in mycluster-ops-instance -g myresourcegroup
    """

    helps[
        "iot ops broker authn list"
    ] = """
        type: command
        short-summary: List mqtt broker authentication resources associated with an instance.

        examples:
        - name: Enumerate all broker authentication resources associated with the default broker.
          text: >
            az iot ops broker authn list -b broker --in mycluster-ops-instance -g myresourcegroup
    """

    helps[
        "iot ops broker authz"
    ] = """
        type: group
        short-summary: Broker authorization management.
    """

    helps[
        "iot ops broker authz show"
    ] = """
        type: command
        short-summary: Show details of an mqtt broker authorization resource.

        examples:
        - name: Show details of a broker authorization resource 'authz' associated with the default broker.
          text: >
            az iot ops broker authz show -n authz -b broker --in mycluster-ops-instance -g myresourcegroup
    """

    helps[
        "iot ops broker authz list"
    ] = """
        type: command
        short-summary: List mqtt broker authorization resources associated with an instance.

        examples:
        - name: Enumerate all broker authorization resources associated with the default broker.
          text: >
            az iot ops broker authz list -b broker --in mycluster-ops-instance -g myresourcegroup
    """

    helps[
        "iot ops dataflow"
    ] = """
        type: group
        short-summary: Dataflow management.
    """

    helps[
        "iot ops dataflow show"
    ] = """
        type: command
        short-summary: Show details of a dataflow associated with a dataflow profile.

        examples:
        - name: Show details of a dataflow 'mydataflow' associated with a profile 'myprofile'.
          text: >
            az iot ops dataflow show -n mydataflow -p myprofile --in mycluster-ops-instance -g myresourcegroup
    """

    helps[
        "iot ops dataflow list"
    ] = """
        type: command
        short-summary: List dataflows associated with a dataflow profile.

        examples:
        - name: Enumerate dataflows associated with the profile 'myprofile'.
          text: >
            az iot ops dataflow list -p myprofile --in mycluster-ops-instance -g myresourcegroup
    """

    helps[
        "iot ops dataflow profile"
    ] = """
        type: group
        short-summary: Dataflow profile management.
    """

    helps[
        "iot ops dataflow profile show"
    ] = """
        type: command
        short-summary: Show details of a dataflow profile.

        examples:
        - name: Show details of a dataflow profile 'myprofile'.
          text: >
            az iot ops dataflow profile show -n myprofile --in mycluster-ops-instance -g myresourcegroup
    """

    helps[
        "iot ops dataflow profile list"
    ] = """
        type: command
        short-summary: List dataflow profiles associated with an instance.

        examples:
        - name: Enumerate dataflow profiles in the instance 'mycluster-ops-instance'.
          text: >
            az iot ops dataflow profile list --in mycluster-ops-instance -g myresourcegroup
    """

    helps[
        "iot ops dataflow endpoint"
    ] = """
        type: group
        short-summary: Dataflow endpoint management.
    """

    helps[
        "iot ops dataflow endpoint show"
    ] = """
        type: command
        short-summary: Show details of a dataflow endpoint resource.

        examples:
        - name: Show details of a dataflow endpoint 'myendpoint'.
          text: >
            az iot ops dataflow endpoint show -n myendpoint --in mycluster-ops-instance -g myresourcegroup
    """

    helps[
        "iot ops dataflow endpoint list"
    ] = """
        type: command
        short-summary: List dataflow endpoint resources associated with an instance.

        examples:
        - name: Enumerate dataflow endpoints in the instance 'mycluster-ops-instance'.
          text: >
            az iot ops dataflow endpoint list --in mycluster-ops-instance -g myresourcegroup
    """

    helps[
        "iot ops verify-host"
    ] = """
        type: command
        short-summary: Runs a set of cluster host verifications for IoT Operations deployment compatibility.
        long-summary: Intended to be run directly on a target cluster host.
          The command may prompt to apply a set of privileged actions such as installing a dependency.
          In this case the CLI must be run with elevated permissions. For example

            `sudo AZURE_EXTENSION_DIR=~/.azure/cliextensions az iot ops verify-host`.
    """

    helps[
        "iot ops init"
    ] = """
        type: command
        short-summary: Bootstrap, configure and deploy IoT Operations to the target Arc-enabled cluster.
        long-summary: |
                      For additional resources including how to Arc-enable a cluster see
                      https://learn.microsoft.com/en-us/azure/iot-operations/deploy-iot-ops/howto-prepare-cluster

                      IoT Operations depends on a service principal (SP) for Key Vault CSI driver secret synchronization.

                      By default, init will do work in creating and configuring a suitable app registration
                      via Microsoft Graph then apply it to the cluster.

                      You can short-circuit this work, by pre-creating an app registration, then providing values
                      for --sp-app-id, --sp-object-id and --sp-secret. By providing the SP fields, no additional
                      work via Microsoft Graph operations will be done.

                      Pre-creating an app registration is useful when the logged-in principal has constrained
                      Entra Id permissions. For example in CI/automation scenarios, or an orgs separation of user
                      responsibility.

        examples:
        - name: Minimum input for complete setup. This includes Key Vault configuration, CSI driver deployment, TLS config and deployment of IoT Operations.
          text: >
            az iot ops init --cluster mycluster -g myresourcegroup --kv-id /subscriptions/2cb3a427-1abc-48d0-9d03-dd240819742a/resourceGroups/myresourcegroup/providers/Microsoft.KeyVault/vaults/mykeyvault

        - name: Same setup as prior example, except with the usage of an existing app Id and a flag to include a simulated PLC server as part of the deployment.
                Including the app Id will prevent init from creating an app registration.
          text: >
            az iot ops init --cluster mycluster -g myresourcegroup --kv-id $KEYVAULT_ID --sp-app-id a14e216b-6802-4e9c-a6ac-844f9ffd230d --simulate-plc

        - name: To skip deployment and focus only on the Key Vault CSI driver and TLS config workflows simple pass in --no-deploy.
                This can be useful when desiring to deploy from a different tool such as Portal.
          text: >
            az iot ops init --cluster mycluster -g myresourcegroup --kv-id $KEYVAULT_ID --sp-app-id a14e216b-6802-4e9c-a6ac-844f9ffd230d --no-deploy

        - name: To only deploy IoT Operations on a cluster that has already been prepped, simply omit --kv-id and include --no-tls.
          text: >
            az iot ops init --cluster mycluster -g myresourcegroup --no-tls

        - name: Use --no-block to do other work while the deployment is on-going vs waiting for the deployment to finish before starting the other work.
          text: >
            az iot ops init --cluster mycluster -g myresourcegroup --kv-id $KEYVAULT_ID --sp-app-id a14e216b-6802-4e9c-a6ac-844f9ffd230d --no-block

        - name: This example shows providing values for --sp-app-id, --sp-object-id and --sp-secret. These values should reflect the desired service principal
                that will be used for the Key Vault CSI driver secret synchronization. Please review the command summary for additional details.
          text: >
            az iot ops init --cluster mycluster -g myresourcegroup --kv-id $KEYVAULT_ID --sp-app-id a14e216b-6802-4e9c-a6ac-844f9ffd230d
            --sp-object-id 224a7a3f-c63d-4923-8950-c4a85f0d2f29 --sp-secret $SP_SECRET

        - name: To customize runtime configuration of the Key Vault CSI driver, --csi-config can be used. For example setting resource limits on the telegraf container dependency.
          text: >
            az iot ops init --cluster mycluster -g myresourcegroup --kv-id $KEYVAULT_ID --sp-app-id a14e216b-6802-4e9c-a6ac-844f9ffd230d
            --csi-config telegraf.resources.limits.memory=500Mi telegraf.resources.limits.cpu=100m
    """

    helps[
        "iot ops delete"
    ] = """
        type: command
        short-summary: Delete IoT Operations from the cluster.
        long-summary: The operation uses Azure Resource Graph to determine correlated resources.
          Resource Graph being eventually consistent does not guarantee a synchronized state at the time of execution.

        examples:
        - name: Minimum input for complete deletion.
          text: >
            az iot ops delete --cluster mycluster -g myresourcegroup
        - name: Skip confirmation prompt and continue to deletion process. Useful for CI scenarios.
          text: >
            az iot ops delete --cluster mycluster -g myresourcegroup -y
        - name: Force deletion regardless of warnings. May lead to errors.
          text: >
            az iot ops delete --cluster mycluster -g myresourcegroup --force
    """

    helps[
        "iot ops show"
    ] = """
        type: command
        short-summary: Show an IoT Operations instance.
        long-summary: Optionally the command can output a tree structure of associated resources representing
          the IoT Operations deployment against the backing cluster.

        examples:
        - name: Basic usage to show an instance.
          text: >
            az iot ops show --name myinstance -g myresourcegroup
        - name: Output a tree structure of associated resources representing the IoT Operations deployment.
          text: >
            az iot ops show --name myinstance -g myresourcegroup --tree
    """

    helps[
        "iot ops list"
    ] = """
        type: command
        short-summary: List IoT Operations instances.
        long-summary: Use --query with desired JMESPath syntax to query the result.

        examples:
        - name: List all instances in the subscription.
          text: >
            az iot ops list
        - name: List all instances of a particular resource group.
          text: >
            az iot ops list -g myresourcegroup
        - name: List the instances in the subscription that have a particular tag value.
          text: >
            az iot ops list -g myresourcegroup --query "[?tags.env == 'prod']"
    """

    helps[
        "iot ops update"
    ] = """
        type: command
        short-summary: Update an IoT Operations instance.
        long-summary: Currently instance tags and description can be updated.

        examples:
        - name: Update instance tags. This is equivalent to a replace.
          text: >
            az iot ops update --name myinstance -g myresourcegroup --tags a=b c=d
        - name: Remove instance tags.
          text: >
            az iot ops update --name myinstance -g myresourcegroup --tags ""
        - name: Update the instance description.
          text: >
            az iot ops update --name myinstance -g myresourcegroup --desc "Fabrikam Widget Factory B42"
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

                      At least one data point or event must be defined during asset creation. For examples
                      of file formats, please see aka.ms/aziotops-assets

        examples:
        - name: Create an asset using the given custom location.
          text: >
            az iot ops asset create --name {asset_name} -g {resource_group} --custom-location {custom_location}
            --endpoint {endpoint} --data data_source={data_source}

        - name: Create an asset using the given custom location and resource group for the custom location. The resource group
                must be included if there are multiple custom locations with the same name within a subscription.
          text: >
            az iot ops asset create --name {asset_name} -g {resource_group} --custom-location {custom_location}
            --custom-location-resource-group {custom_location_resource_group} --endpoint {endpoint} --data data_source={data_source}

        - name: Create an asset using the given cluster name. The resource group must be included if there are multiple clusters
                with the same name within a subscription.
          text: >
            az iot ops asset create --name {asset_name} -g {resource_group} --cluster {cluster} --cluster-resource-group {cluster_resource_group}
            --endpoint {endpoint} --event event_notifier={event_notifier}

        - name: Create an asset using the given cluster name and custom location.
          text: >
            az iot ops asset create --name {asset_name} -g {resource_group} --cluster {cluster}
            --custom-location {custom_location} --endpoint {endpoint} --event event_notifier={event_notifier}

        - name: Create an asset with custom data point and event defaults.
          text: >
            az iot ops asset create --name {asset_name} -g {resource_group} --custom-location {custom_location}
            --endpoint {endpoint} --data-publish-int {data_point_publishing_interval}
            --data-queue-size {data_point_queue_size} --data-sample-int {data_point_sampling_interval}
            --event-publish-int {event_publishing_interval} --event-queue-size {event_queue_size}
            --event-sample-int {event_sampling_interval} --event event_notifier={event_notifier}

        - name: Create an asset with additional custom attributes.
          text: >
            az iot ops asset create --name {asset_name} -g {resource_group} --custom-location {custom_location}
            --endpoint {endpoint} --custom-attribute {attribute_key}={attribute_value} --custom-attribute {attribute_key}={attribute_value}

        - name: Create an asset with custom asset type, description, documentation uri, external asset id, hardware revision,
                product code, and software revision.
          text: >
            az iot ops asset create --name {asset_name} -g {resource_group} --custom-location {custom_location}
            --endpoint {endpoint} --asset-type {asset_type} --description {description}
            --documentation-uri {documentation_uri} --external-asset-id {external_asset_id} --hardware-revision {hardware_revision}
            --product-code {product_code} --software-revision {software_revision} --data data_source={data_source}

        - name: Create an asset with two events, manufacturer, manufacturer uri, model, serial number.
          text: >
            az iot ops asset create --name {asset_name} -g {resource_group} --custom-location {custom_location}
            --endpoint {endpoint} --event capability_id={capability_id} event_notifier={event_notifier}
            name={name} observability_mode={observability_mode} sampling_interval={sampling_interval} queue_size={queue_size}
            --event event_notifier={event_notifier} --manufacturer {manufacturer} --manufacturer-uri {manufacturer_uri} --model {model}
            --serial-number {serial_number}

        - name: Create a disabled asset with two data points.
          text: >
            az iot ops asset create --name {asset_name} -g {resource_group} --custom-location {custom_location}
            --endpoint {endpoint} --disable --data capability_id={capability_id}
            data_source={data_source} name={name} observability_mode={observability_mode} sampling_interval={sampling_interval}
            queue_size={queue_size} --data data_source={data_source}

        - name: Create an asset using a file containing data-points and another file containing events.
          text: >
            az iot ops asset create --name MyAsset -g MyRg --custom-location MyLocation --endpoint exampleEndpoint
            --data-file /path/to/myasset_datapoints.json --event-file /path/to/myasset_events.csv

        - name: Create an asset with the given pre-filled values.
          text: >
            az iot ops asset create --name MyAsset -g MyRg --custom-location MyLocation --endpoint exampleEndpoint
            --data capability_id=myTagId data_source=NodeID1 name=myTagName1
            observability_mode=counter sampling_interval=10 queue_size=2 --data
            data_source=NodeID2 --data-publish-int 1000 --data-queue-size 1 --data-sample-int 30
            --asset-type customAsset --description 'Description for a test asset.'
            --documentation-uri www.help.com --external-asset-id 000-000-0000 --hardware-revision 10.0
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
            az iot ops asset show --name {asset_name} -g {resource_group}
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
            az iot ops asset update --name {asset_name} -g {resource_group} --data-publish-int {data_point_publishing_interval}
            --data-queue-size {data_point_queue_size} --data-sample-int {data_point_sampling_interval}
            --event-publish-int {event_publishing_interval} --event-queue-size {event_queue_size}
            --event-sample-int {event_sampling_interval}

        - name: Update an asset's asset type, description, documentation uri, external asset id, hardware revision, product code,
                and software revision.
          text: >
            az iot ops asset update --name {asset_name} -g {resource_group} --asset-type {asset_type} --description {description}
            --documentation-uri {documentation_uri} --external-asset-id {external_asset_id} --hardware-revision {hardware_revision}
            --product-code {product_code} --software-revision {software_revision}

        - name: Update an asset's manufacturer, manufacturer uri, model, serial number, and custom attribute.
          text: >
            az iot ops asset update --name {asset_name} -g {resource_group} --manufacturer {manufacturer} --manufacturer-uri {manufacturer_uri} --model {model}
            --serial-number {serial_number} --custom-attribute {attribute_key}={attribute_value}

        - name: Disable an asset and remove a custom attribute called "work_site".
          text: >
            az iot ops asset update --name {asset_name} -g {resource_group} --disable --custom-attribute work_site=""
    """

    helps[
        "iot ops asset delete"
    ] = """
        type: command
        short-summary: Delete an asset.
        examples:
        - name: Delete an asset.
          text: >
            az iot ops asset delete --name {asset_name} -g {resource_group}
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
            az iot ops asset data-point add --asset {asset} -g {resource_group} --data-source {data_source} --name
            {name} --capability-id {capability_id} --observability-mode {observability_mode} --queue-size
            {queue_size} --sampling-interval {sampling_interval}

        - name: Add a data point to an asset with the given pre-filled values.
          text: >
            az iot ops asset data-point add --asset MyAsset -g MyRG --data-source NodeID1 --name tagName1
            --capability-id tagId1 --observability-mode log --queue-size 5 --sampling-interval 200
    """

    helps[
        "iot ops asset data-point export"
    ] = """
        type: command
        short-summary: Export data points in an asset.
        long-summary: The file name will be {asset_name}_dataPoints.{file_type}.
        examples:
        - name: Export all data points in an asset in JSON format.
          text: >
            az iot ops asset data-point export --asset {asset} -g {resource_group}
        - name: Export all data points in an asset in CSV format in a specific output directory.
          text: >
            az iot ops asset data-point export --asset {asset} -g {resource_group} --format csv --output-dir {output_directory}
        - name: Export all data points in an asset in CSV format that can be uploaded via the DOE portal.
          text: >
            az iot ops asset data-point export --asset {asset} -g {resource_group} --format portal-csv
        - name: Export all data points in an asset in YAML format. Replace the file if one is present already.
          text: >
            az iot ops asset data-point export --asset {asset} -g {resource_group} --format yaml --replace
    """

    helps[
        "iot ops asset data-point import"
    ] = """
        type: command
        short-summary: Import data points in an asset.
        long-summary: For examples of file formats, please see aka.ms/aziotops-assets
        examples:
        - name: Import all data points from a file. These data points will be appended to the asset's current data points. Data-points with duplicate dataSources will be ignored.
          text: >
            az iot ops asset data-point import --asset {asset} -g {resource_group} --input-file {input_file}
        - name: Import all data points from a file. These data points will be appended to the asset's current data points. Data-points with duplicate dataSources will be replaced.
          text: >
            az iot ops asset data-point import --asset {asset} -g {resource_group} --input-file {input_file} --replace
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
            az iot ops asset data-point remove --asset {asset} -g {resource_group} --name {name}
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
            --name {name} --capability-id {capability_id} --observability-mode
            {observability_mode} --queue-size {queue_size} --sampling-interval {sampling_interval}

        - name: Add an event to an asset with the given pre-filled values.
          text: >
            az iot ops asset event add --asset MyAsset -g MyRG --event-notifier eventId --name eventName
            --capability-id tagId1 --observability-mode log --queue-size 2 --sampling-interval 500
    """

    helps[
        "iot ops asset event export"
    ] = """
        type: command
        short-summary: Export events in an asset.
        long-summary: The file name will be {asset_name}_dataPoints.{file_type}.
        examples:
        - name: Export all events in an asset in JSON format.
          text: >
            az iot ops asset event export --asset {asset} -g {resource_group}
        - name: Export all events in an asset in CSV format in a specific output directory.
          text: >
            az iot ops asset event export --asset {asset} -g {resource_group} --format csv --output-dir {output_directory}
        - name: Export all events in an asset in CSV format that can be uploaded to the DOE portal.
          text: >
            az iot ops asset event export --asset {asset} -g {resource_group} --format portal-csv
        - name: Export all events in an asset in YAML format. Replace the file if one is present already.
          text: >
            az iot ops asset event export --asset {asset} -g {resource_group} --format yaml --replace
    """

    helps[
        "iot ops asset event import"
    ] = """
        type: command
        short-summary: Import events in an asset.
        long-summary: For examples of file formats, please see aka.ms/aziotops-assets
        examples:
        - name: Import all events from a file. These events will be appended to the asset's current events.
          text: >
            az iot ops asset event import --asset {asset} -g {resource_group} --input-file {input_file}
        - name: Import all events from a file. These events will replace the asset's current events.
          text: >
            az iot ops asset event import --asset {asset} -g {resource_group} --input-file {input_file} --replace
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
            az iot ops asset event remove --asset {asset} -g {resource_group} --name {name}
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
        type: command
        short-summary: Create an asset endpoint.
        long-summary: |
                      Either custom location or cluster name must be provided. This command will check
                      for the existance of the associated custom location and cluster and ensure that
                      both are set up correctly with the microsoft.deviceregistry.assets extension.

                      Azure IoT OPC UA Broker (preview) uses the same client certificate for all secure
                      channels between itself and the OPC UA servers that it connects to.
        examples:
        - name: Create an asset endpoint with anonymous user authentication using the given custom location.
          text: >
            az iot ops asset endpoint create --name {asset_endpoint} -g {resource_group} --custom-location {custom_location}
            --target-address {target_address}
        - name: Create an asset endpoint with anonymous user authentication using the given custom location and resource group
                for the custom location. The resource group must be included if there are multiple custom locations with the
                same name within a subscription.
          text: >
            az iot ops asset endpoint create --name {asset_endpoint} -g {resource_group} --custom-location {custom_location}
            --custom-location-resource-group {custom_location_resource_group} --target-address {target_address}
        # - name: Create an asset endpoint with username-password user authentication using the given cluster name. The resource
        #         group must be included if there are multiple clusters with the same name within a subscription.
        #   text: >
        #     az iot ops asset endpoint create --name {asset_endpoint} -g {resource_group} --cluster {cluster}
        #     --cluster-resource-group {cluster_resource_group} --target-address {target_address}
        #     --username-ref {username_reference} --password-ref {password_reference}
        # - name: Create an asset endpoint with certificate user authentication and additional configuration using the given custom
        #         location and cluster name.
        #   text: >
        #     az iot ops asset endpoint create --name {asset_endpoint} -g {resource_group} --cluster {cluster}
        #     --custom-location {custom_location} --target-address {target_address} --certificate-ref {certificate_reference}
        #     --additional-config {additional_configuration}
        # - name: Create an asset endpoint with anonymous user authentication with preconfigured owned certificates.
        #   text: >
        #     az iot ops asset endpoint create --name {asset_endpoint} -g {resource_group} --custom-location {custom_location}
        #     --target-address {target_address} --cert secret={secret_reference} password={password_reference} thumbprint {thumbprint}
        #     --cert secret={secret_reference} password={password_reference} thumbprint={thumbprint}
        - name: Create an asset endpoint with username-password user authentication and preconfigurated owned certificates with
                prefilled values.The username and password references are set via the Azure Keyvault Container Storage Interface
                driver.
          text: >
            az iot ops asset endpoint create --name myAssetEndpoint -g myRG --cluster myCluster
            --target-address "opc.tcp://opcplc-000000:50000" --username-ref "aio-opc-ua-broker-user-authentication/opc-plc-username"
            --password-ref "aio-opc-ua-broker-user-authentication/opc-plc-password" --cert secret=aio-opc-ua-broker-client-certificate
            thumbprint=000000000000000000 password=aio-opc-ua-broker-client-certificate-password
        - name: Create an asset endpoint with username-password user authentication and additional configuration with prefilled values
                (powershell syntax example).
          text: >
            az iot ops asset endpoint create --name myAssetEndpoint -g myRG --cluster myCluster
            --target-address "opc.tcp://opcplc-000000:50000" --username-ref "aio-opc-ua-broker-user-authentication/opc-plc-username"
            --password-ref "aio-opc-ua-broker-user-authentication/opc-plc-password"
            --additional-config '{\\\"applicationName\\\": \\\"opcua-connector\\\", \\\"defaults\\\": {
            \\\"publishingIntervalMilliseconds\\\": 100,  \\\"samplingIntervalMilliseconds\\\": 500,  \\\"queueSize\\\": 15,},
            \\\"session\\\": {\\\"timeout\\\": 60000}, \\\"subscription\\\": {\\\"maxItems\\\": 1000}, \\\"security\\\": {
            \\\"autoAcceptUntrustedServerCertificates\\\": true}}'
        - name: Create an asset endpoint with username-password user authentication and additional configuration with prefilled values
                (cmd syntax example).
          text: >
            az iot ops asset endpoint create --name myAssetEndpoint -g myRG --cluster myCluster
            --target-address "opc.tcp://opcplc-000000:50000" --username-ref "aio-opc-ua-broker-user-authentication/opc-plc-username"
            --password-ref "aio-opc-ua-broker-user-authentication/opc-plc-password"
            --additional-config "{\\\"applicationName\\\": \\\"opcua-connector\\\", \\\"defaults\\\": {
            \\\"publishingIntervalMilliseconds\\\": 100,  \\\"samplingIntervalMilliseconds\\\": 500,  \\\"queueSize\\\": 15,},
            \\\"session\\\": {\\\"timeout\\\": 60000}, \\\"subscription\\\": {\\\"maxItems\\\": 1000}, \\\"security\\\": {
            \\\"autoAcceptUntrustedServerCertificates\\\": true}}"
        - name: Create an asset endpoint with username-password user authentication and additional configuration with prefilled values
                (bash syntax example).
          text: >
            az iot ops asset endpoint create --name myAssetEndpoint -g myRG --cluster myCluster
            --target-address "opc.tcp://opcplc-000000:50000" --username-ref "aio-opc-ua-broker-user-authentication/opc-plc-username"
            --password-ref "aio-opc-ua-broker-user-authentication/opc-plc-password"
            --additional-config '{"applicationName": "opcua-connector", "defaults": {
            "publishingIntervalMilliseconds": 100,  "samplingIntervalMilliseconds": 500,  "queueSize": 15,},
            "session": {"timeout": 60000}, "subscription": {"maxItems": 1000}, "security": {
            "autoAcceptUntrustedServerCertificates": true}}'
    """

    helps[
        "iot ops asset endpoint query"
    ] = """
        type: command
        short-summary: Query the Resource Graph for asset endpoints.
        examples:
        - name: Query for asset endpoints that hae anonymous authentication.
          text: >
            az iot ops asset endpoint query --authentication-mode Anonymous
        - name: Query for asset endpoints that have the given target address and custom location.
          text: >
            az iot ops asset endpoint query --target-address {target_address} --custom-location {custom_location}
    """

    helps[
        "iot ops asset endpoint show"
    ] = """
        type: command
        short-summary: Show an asset endpoint.
        examples:
        - name: Show the details of an asset endpoint.
          text: >
            az iot ops asset endpoint show --name {asset_endpoint} -g {resource_group}
    """

    helps[
        "iot ops asset endpoint update"
    ] = """
        type: command
        short-summary: Update an asset endpoint.
        long-summary: To update owned certificates, please use the command group `az iot ops asset endpoint certificate`.
        examples:
        - name: Update an asset endpoint's authentication mode to use anonymous user authentication.
          text: >
            az iot ops asset endpoint update --name {asset_endpoint} -g {resource_group}
            --authentication-mode Anonymous
        - name: Update an asset endpoint's username and password reference with prefilled values. This will transform the
                authentication mode to username-password if it is not so already.
          text: >
            az iot ops asset endpoint update --name myAssetEndpoint -g myRG
            --username-ref "aio-opc-ua-broker-user-authentication/opc-plc-username"
            --password-ref "aio-opc-ua-broker-user-authentication/opc-plc-password"
        - name: Update an asset endpoint's target address and additional configuration with prefilled values
                (powershell syntax example).
          text: >
            az iot ops asset endpoint update --name myAssetEndpoint -g myRG
            --target-address "opc.tcp://opcplc-000000:50000"
            --additional-config '{\\\"applicationName\\\": \\\"opcua-connector\\\", \\\"defaults\\\": {
            \\\"publishingIntervalMilliseconds\\\": 100,  \\\"samplingIntervalMilliseconds\\\": 500,  \\\"queueSize\\\": 15,},
            \\\"session\\\": {\\\"timeout\\\": 60000}, \\\"subscription\\\": {\\\"maxItems\\\": 1000}, \\\"security\\\": {
            \\\"autoAcceptUntrustedServerCertificates\\\": true}}'
        - name: Update an asset endpoint's target address and additional configuration with prefilled values
                (cmd syntax example).
          text: >
            az iot ops asset endpoint update --name myAssetEndpoint -g myRG
            --target-address "opc.tcp://opcplc-000000:50000"
            --additional-config "{\\\"applicationName\\\": \\\"opcua-connector\\\", \\\"defaults\\\": {
            \\\"publishingIntervalMilliseconds\\\": 100,  \\\"samplingIntervalMilliseconds\\\": 500,  \\\"queueSize\\\": 15,},
            \\\"session\\\": {\\\"timeout\\\": 60000}, \\\"subscription\\\": {\\\"maxItems\\\": 1000}, \\\"security\\\": {
            \\\"autoAcceptUntrustedServerCertificates\\\": true}}"
        - name: Update an asset endpoint's target address and additional configuration with prefilled values
                (bash syntax example).
          text: >
            az iot ops asset endpoint update --name myAssetEndpoint -g myRG
            --target-address "opc.tcp://opcplc-000000:50000"
            --additional-config '{"applicationName": "opcua-connector", "defaults": {
            "publishingIntervalMilliseconds": 100,  "samplingIntervalMilliseconds": 500,  "queueSize": 15,},
            "session": {"timeout": 60000}, "subscription": {"maxItems": 1000}, "security": {
            "autoAcceptUntrustedServerCertificates": true}}'
    """

    helps[
        "iot ops asset endpoint delete"
    ] = """
        type: command
        short-summary: Delete an asset endpoint.
        examples:
        - name: Delete an asset endpoint.
          text: >
            az iot ops asset endpoint delete --name {asset_endpoint} -g {resource_group}
    """

    helps[
        "iot ops asset endpoint certificate"
    ] = """
        type: group
        short-summary: Manage owned certificates in an asset endpoint.
    """

    helps[
        "iot ops asset endpoint certificate add"
    ] = """
        type: command
        short-summary: Add an owned certificate to an asset endpoint.
        examples:
        - name: Add a certificate to an asset endpoint.
          text: >
            az iot ops asset endpoint certificate add --endpoint {asset_endpoint} -g {resource_group}
            --secret-ref {secret_reference} --thumbprint {thumbprint} --password-ref {password_reference}
        - name: Add a certificate to an asset endpoint that uses a password with prefilled values.
          text: >
            az iot ops asset endpoint certificate add --endpoint myAssetEndpoint -g myRG
            --secret-ref "aio-opc-ua-broker-client/certificate" --thumbprint 000000000000000000
            --password-ref "aio-opc-ua-broker-client/certificate-password"
    """

    helps[
        "iot ops asset endpoint certificate list"
    ] = """
        type: command
        short-summary: List owned certificates in an asset endpoint.
        examples:
        - name: List all owned certificates in an asset endpoint.
          text: >
            az iot ops asset endpoint certificate list --endpoint {asset_endpoint} -g {resource_group}
    """

    helps[
        "iot ops asset endpoint certificate remove"
    ] = """
        type: command
        short-summary: Remove an owned certificate in an asset endpoint.
        examples:
        - name: Remove a certificate from an asset endpoint.
          text: >
            az iot ops asset endpoint certificate remove --endpoint {asset_endpoint} -g {resource_group}
            --thumbprint {thumbprint}
    """

    helps[
        "iot ops schema"
    ] = """
        type: group
        short-summary: Schema management.
    """

    helps[
        "iot ops schema registry"
    ] = """
        type: group
        short-summary: Schema registry management.
    """

    helps[
        "iot ops schema registry show"
    ] = """
        type: command
        short-summary: Show details of a schema registry.
        examples:
        - name: Show details of target schema registry 'myregistry'.
          text: >
            az iot ops schema registry show --name myregistry -g myresourcegroup
    """

    helps[
        "iot ops schema registry list"
    ] = """
        type: command
        short-summary: List schema registries in a resource group or subscription.
        examples:
        - name: List schema registeries in the resource group 'myresourcegroup'.
          text: >
            az iot ops schema registry list -g myresourcegroup
        - name: List schema registeries in the default subscription filtering on a particular tag.
          text: >
            az iot ops schema registry list --query "[?tags.env == 'prod']"
    """

    helps[
        "iot ops schema registry delete"
    ] = """
        type: command
        short-summary: Delete a target schema registry.
        examples:
        - name: Delete schema registry 'myregistry'.
          text: >
            az iot ops schema registry delete -n myregistry -g myresourcegroup
    """

    helps[
        "iot ops schema registry create"
    ] = """
        type: command
        short-summary: Create a schema registry.
        long-summary: |
                      This operation will create a schema registry with system managed identity enabled.

                      It will then assign the system identity the built-in "Storage Blob Data Contributor"
                      role against the storage account scope by default.

                      If necessary you can provide a custom role via --custom-role-id to use instead.
        examples:
        - name: Create a schema registry called 'myregistry' with minimum inputs.
          text: >
            az iot ops schema registry create -n myregistry -g myresourcegroup --namespace myschemas
              --sa-resource-id $STORAGE_ACCOUNT_RESOURCE_ID --sa-container mycontainer
        - name: Create a schema registry called 'myregistry' in region westus2 with additional customization.
          text: >
            az iot ops schema registry create -n myregistry -g myresourcegroup --namespace myschemas
              --sa-resource-id $STORAGE_ACCOUNT_RESOURCE_ID --sa-container mycontainer
              -l westus2 --desc 'Contoso factory X1 schemas" --display-name "Contoso X1" --tags env=prod
    """
