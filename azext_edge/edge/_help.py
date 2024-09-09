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
        short-summary: Evaluate cluster-side readiness and runtime health of deployed IoT Operations services.
        long-summary: |
            The command by default shows a high-level human friendly _summary_ view of all services.
            Use the '--svc' option to specify checks for a single service, and configure verbosity via the `--detail-level` argument.
            Note: Resource kind (--resources) and name (--resource-name) filtering can only be used with the '--svc' argument.

            {{Supported service APIs}}
            - {COMPAT_AKRI_APIS.as_str()}
            - {COMPAT_DEVICEREGISTRY_APIS.as_str()}
            - {COMPAT_MQTT_BROKER_APIS.as_str()}
            - {COMPAT_OPCUA_APIS.as_str()}
            - {COMPAT_DATAFLOW_APIS.as_str()}

            For more information on cluster requirements, please check https://aka.ms/iot-ops-cluster-requirements

        examples:
        - name: Basic usage. Checks overall IoT Operations health with summary output.
          text: >
            az iot ops check

        - name: Checks `broker` service health and configuration with detailed output.
          text: >
            az iot ops check --svc broker --detail-level 1

        - name: Evaluate only the `dataflow` service with output optimized for CI.
          text: >
            az iot ops check --svc dataflow --as-object

        - name: Checks `deviceregistry` health with verbose output, but constrains results to `asset` resources.
          text: >
            az iot ops check --svc deviceregistry --detail-level 2 --resources asset

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

        - name: Fetch all available mqtt broker traces from the diagnostics Protobuf endpoint.
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
        "iot ops broker delete"
    ] = """
        type: command
        short-summary: Delete an mqtt broker.

        examples:
        - name: Delete the broker called 'broker' in the instance 'mycluster-ops-instance'.
          text: >
            az iot ops broker delete -n broker --in mycluster-ops-instance -g myresourcegroup
        - name: Same as prior example but skipping the confirmation prompt.
          text: >
            az iot ops broker delete -n broker --in mycluster-ops-instance -g myresourcegroup -y
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
        "iot ops broker listener delete"
    ] = """
        type: command
        short-summary: Delete an mqtt broker listener.

        examples:
        - name: Delete the broker listener called 'listener' associated with broker 'broker'.
          text: >
            az iot ops broker listener delete -n listener -b broker --in mycluster-ops-instance -g myresourcegroup
        - name: Same as prior example but skipping the confirmation prompt.
          text: >
            az iot ops broker listener delete -n listener -b broker --in mycluster-ops-instance -g myresourcegroup -y
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
        "iot ops broker authn delete"
    ] = """
        type: command
        short-summary: Delete an mqtt broker authentication resource.

        examples:
        - name: Delete the broker authentication resource called 'authn' associated with broker 'broker'.
          text: >
            az iot ops broker authn delete -n authn -b broker --in mycluster-ops-instance -g myresourcegroup
        - name: Same as prior example but skipping the confirmation prompt.
          text: >
            az iot ops broker authn delete -n authn -b broker --in mycluster-ops-instance -g myresourcegroup -y
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
        "iot ops broker authz delete"
    ] = """
        type: command
        short-summary: Delete an mqtt broker authorization resource.

        examples:
        - name: Delete the broker authorization resource called 'authz' associated with broker 'broker'.
          text: >
            az iot ops broker authz delete -n authz -b broker --in mycluster-ops-instance -g myresourcegroup
        - name: Same as prior example but skipping the confirmation prompt.
          text: >
            az iot ops broker authz delete -n authz -b broker --in mycluster-ops-instance -g myresourcegroup -y
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
            az iot ops delete -n myinstance -g myresourcegroup
        - name: Skip confirmation prompt and continue to deletion process. Useful for CI scenarios.
          text: >
            az iot ops delete -n myinstance -g myresourcegroup -y
        - name: Force deletion regardless of warnings. May lead to errors.
          text: >
            az iot ops delete -n myinstance -g myresourcegroup --force
        - name: Reverse application of init.
          text: >
            az iot ops delete -n myinstance -g myresourcegroup --include-deps
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
        "iot ops create"
    ] = """
        type: command
        short-summary: Create an IoT Operations instance.

        examples:
        - name: Create the target instance with minimum input.
          text: >
            az iot ops create --name myinstance --cluster mycluster -g myresourcegroup
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
        long-summary: For examples of file formats, please see aka.ms/aziotops-assets

        examples:
        - name: Create an asset using the given instance in the same resource group.
          text: >
            az iot ops asset create --name myasset -g myresourcegroup --endpoint-profile myassetendpoint --instance myinstance

        - name: Create an asset using the given instance in a different resource group and subscription.
          text: >
            az iot ops asset create --name myasset -g myresourcegroup --endpoint-profile myassetendpoint --instance myinstance
            --instance-resource-group myinstanceresourcegroup --instance-subscription myinstancesubscription

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
            --documentation-uri www.help.com --external-asset-id 000-000-1234 --hardware-revision 10.0
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
            --documentation-uri www.help2.com --hardware-revision 11.0
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
            az iot ops asset dataset show -g myresourcegroup --asset myasset -n dataset1
    """

    helps[
        "iot ops asset dataset data-point"
    ] = """
        type: group
        short-summary: Manage data points in an asset dataset.
    """

    helps[
        "iot ops asset dataset data-point add"
    ] = """
        type: command
        short-summary: Add a data point to an asset dataset.

        # examples:
        # - name: Add a data point to an asset.
        #   text: >
        #     az iot ops asset dataset data-point add --asset myasset -g myresourcegroup --dataset dataset1 --data-source mydatasource --name data1

        # - name: Add a data point to an asset with data point name, observability mode, custom queue size,
        #         and custom sampling interval.
        #   text: >
        #     az iot ops asset dataset data-point add --asset myasset -g myresourcegroup --dataset dataset1 --data-source mydatasource --name data1
        #     --observability-mode log --queue-size5 --sampling-interval 200
    """

    helps[
        "iot ops asset dataset data-point export"
    ] = """
        type: command
        short-summary: Export data points in an asset dataset.
        long-summary: The file name will be {asset_name}_{dataset_name}_dataPoints.{file_type}.
        # examples:
        # - name: Export all data points in an asset in JSON format.
        #   text: >
        #     az iot ops asset dataset data-point export --asset myasset -g myresourcegroup --dataset dataset1
        # - name: Export all data points in an asset in CSV format in a specific output directory.
        #   text: >
        #     az iot ops asset dataset data-point export --asset myasset -g myresourcegroup --dataset dataset1 --format csv --output-dir myAssetsFiles
        # - name: Export all data points in an asset in CSV format that can be uploaded via the DOE portal.
        #   text: >
        #     az iot ops asset dataset data-point export --asset myasset -g myresourcegroup --dataset dataset1 --format portal-csv
        # - name: Export all data points in an asset in YAML format. Replace the file if one is present already.
        #   text: >
        #     az iot ops asset dataset data-point export --asset myasset -g myresourcegroup --dataset dataset1 --format yaml --replace
    """

    helps[
        "iot ops asset dataset data-point import"
    ] = """
        type: command
        short-summary: Import data points in an asset dataset. ### TODO: update once dup param is decided
        long-summary: For examples of file formats, please see aka.ms/aziotops-assets
        # examples:
        # - name: Import all data points from a file. These data points will be appended to the asset dataset's current data points. Data-points with duplicate dataSources will be ignored.
        #   text: >
        #     az iot ops asset dataset data-point import --asset myasset -g myresourcegroup --dataset dataset1 --input-file myasset_dataset1_dataPoints.csv
        # - name: Import all data points from a file. These data points will be appended to the asset dataset's current data points. Data-points with duplicate dataSources will be replaced.
        #   text: >
        #     az iot ops asset dataset data-point import --asset myasset -g myresourcegroup --dataset dataset1 --input-file myasset_dataset1_dataPoints.json --replace
    """

    helps[
        "iot ops asset dataset data-point list"
    ] = """
        type: command
        short-summary: List data points in an asset dataset.
        # examples:
        # - name: List all data-points in an asset dataset.
        #   text: >
        #     az iot ops asset dataset data-point list --asset myasset -g myresourcegroup --dataset dataset1
    """

    helps[
        "iot ops asset dataset data-point remove"
    ] = """
        type: command
        short-summary: Remove a data point in an asset dataset.

        # examples:
        # - name: Remove a data point from an asset via the data point name.
        #   text: >
        #     az iot ops asset dataset data-point remove --asset myasset -g myresourcegroup --dataset dataset1 --name data1
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

        # examples:
        # - name: Add an event to an asset.
        #   text: >
        #     az iot ops asset event add --asset myasset -g myresourcegroup --event-notifier eventId --name eventName

        # - name: Add an event to an asset with event name, observability mode, custom queue size,
        #         and custom sampling interval.
        #   text: >
        #     az iot ops asset event add --asset MyAsset -g MyRG --event-notifier eventId --name eventName
        #     --observability-mode log --queue-size 2 --sampling-interval 500
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
        - name: Export all events in an asset in CSV format in a specific output directory.
          text: >
            az iot ops asset event export --asset myasset -g myresourcegroup --format csv --output-dir myAssetFiles
        - name: Export all events in an asset in CSV format that can be uploaded to the DOE portal.
          text: >
            az iot ops asset event export --asset myasset -g myresourcegroup --format portal-csv
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
        - name: Import all events from a file. These events will be appended to the asset's current events.
          text: >
            az iot ops asset event import --asset myasset -g myresourcegroup --input-file myasset_events.yaml
        - name: Import all events from a file. These events will replace the asset's current events.
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

        # examples:
        # - name: Remove an event from an asset via the event name.
        #   text: >
        #     az iot ops asset event remove --asset myasset -g myresourcegroup --name myevent
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
        short-summary: Create an asset endpoint profile with an OPCUA connector.
        long-summary: Azure IoT OPC UA Broker (preview) uses the same client certificate for all secure
                      channels between itself and the OPC UA servers that it connects to.
        examples:
        - name: Create an asset endpoint with anonymous user authentication using the given instance in the same resource group.
          text: >
            az iot ops asset endpoint create opcua --name myprofile -g myresourcegroup --instance myinstance
            --target-address opc.tcp://opcplc-000000:50000
        - name: Create an asset endpoint with anonymous user authentication using the given instance in a different resource group and subscription.
          text: >
            az iot ops asset endpoint create opcua --name myprofile -g myresourcegroup --instance myinstance
            --instance-resource-group myinstanceresourcegroup --instance-subscription myinstancesubscription
            --target-address opc.tcp://opcplc-000000:50000
        - name: Create an asset endpoint with username-password user authentication using the given instance in the same resource group.
          text: >
            az iot ops asset endpoint create opcua --name myprofile -g myresourcegroup --instance myinstance
            --target-address opc.tcp://opcplc-000000:50000
            --username-ref myusername --password-ref mypassword
        - name: Create an asset endpoint with certificate user authentication using the given given instance in the same resource group.
          text: >
            az iot ops asset endpoint create opcua --name myprofile -g myresourcegroup --instance myinstance
            --target-address opc.tcp://opcplc-000000:50000 --certificate-ref mycertificate.pem
        - name: Create an asset endpoint with anonymous user authentication and prefilled values for the OPCUA configuration using the given instance in the same resource group.
          text: >
            az iot ops asset endpoint create opcua --name myprofile -g myresourcegroup --instance myinstance
            --target-address opc.tcp://opcplc-000000:50000 --accept-untrusted-certs --application myopcuaconnector
            --default-publishing-int 200 --default-queue-size 2 --default-sampling-int 50 --keep-alive 300 --run-asset-discovery
            --security-mode sign --security-policy signonly --session-keep-alive 500 --session-reconnect-backoff 50 --session-reconnect-period 400
            --session-timeout 550 --subscription-life-time 3000 --subscription-max-items 20
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

    helps[
        "iot ops schema"
    ] = """
        type: group
        short-summary: Schema management.
        long-summary: |
          Schemas are documents that describe data to enable processing and contextualization.
          Message schemas describe the format of a message and its contents.
    """

    helps[
        "iot ops schema registry"
    ] = """
        type: group
        short-summary: Schema registry management.
        long-summary: |
          A schema registry is a centralized repository for managing schemas. Schema registry enables
          schema generation and retrieval both at the edge and in the cloud. It ensures consistency
          and compatibility across systems by providing a single source of truth for schema
          definitions.
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
                      role against the storage account scope by default. If necessary you can provide a custom
                      role via --custom-role-id to use instead.

                      If the indicated storage account container does not exist it will be created with default
                      settings.
        examples:
        - name: Create a schema registry called 'myregistry' with minimum inputs.
          text: >
            az iot ops schema registry create -n myregistry -g myresourcegroup --registry-namespace myschemas
            --sa-resource-id $STORAGE_ACCOUNT_RESOURCE_ID
        - name: Create a schema registry called 'myregistry' in region westus2 with additional customization.
          text: >
            az iot ops schema registry create -n myregistry -g myresourcegroup --registry-namespace myschemas
            --sa-resource-id $STORAGE_ACCOUNT_RESOURCE_ID --sa-container myschemacontainer
            -l westus2 --desc 'Contoso factory X1 schemas' --display-name 'Contoso X1' --tags env=prod
    """
