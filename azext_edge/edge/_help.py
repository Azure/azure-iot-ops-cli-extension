# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------
"""
Help definitions for Digital Twins commands.
"""

from knack.help_files import helps

from azext_edge.edge.providers.edge_api import SECRETSTORE_API_V1, SECRETSYNC_API_V1

from .providers.support_bundle import (
    COMPAT_ARCCONTAINERSTORAGE_APIS,
    COMPAT_CLUSTER_CONFIG_APIS,
    COMPAT_DEVICEREGISTRY_APIS,
    COMPAT_MQTT_BROKER_APIS,
    COMPAT_OPCUA_APIS,
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
        short-summary: IoT Operations support operations.
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
            - {COMPAT_DEVICEREGISTRY_APIS.as_str()}
            - {COMPAT_CLUSTER_CONFIG_APIS.as_str()}
            - {COMPAT_DATAFLOW_APIS.as_str()}
            - {COMPAT_ARCCONTAINERSTORAGE_APIS.as_str()}
            - {SECRETSYNC_API_V1.as_str()}
            - {SECRETSTORE_API_V1.as_str()}

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

        - name: Include mqtt broker traces in the support bundle.
          text: >
            az iot ops support create-bundle --ops-service broker --broker-traces

        - name: Include arc container storage resources in the support bundle.
          text: >
            az iot ops support create-bundle --ops-service acs

        - name: Include secretstore resources in the support bundle.
          text: >
            az iot ops support create-bundle --ops-service secretstore

        - name: Include multiple services in the support bundle with single --ops-service flag.
          text: >
            az iot ops support create-bundle --ops-service broker opcua deviceregistry

        - name: Include multiple services in the support bundle with multiple --ops-service flags.
          text: >
            az iot ops support create-bundle --ops-service broker --ops-service opcua --ops-service deviceregistry
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
        short-summary: Mqtt broker management.
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
        short-summary: Bootstrap the Arc-enabled cluster for IoT Operations deployment.
        long-summary: |
                      An Arc-enabled cluster is required to deploy IoT Operations. See the following resource for
                      more info https://aka.ms/aziotops-arcconnect.

                      The init operation will do work in installing and configuring a foundation layer of edge
                      services necessary for IoT Operations deployment.

                      After the foundation layer has been installed the `az iot ops create` command should
                      be used to deploy an instance.
        examples:
        - name: Usage with minimum input. This form will deploy the IoT Operations foundation layer.
          text: >
             az iot ops init --cluster mycluster -g myresourcegroup
        - name: Similar to the prior example but with Arc Container Storage fault-tolerance enabled (requires at least 3 nodes).
          text: >
             az iot ops init --cluster mycluster -g myresourcegroup --enable-fault-tolerance
        - name: This example highlights enabling user trust settings for a custom cert-manager config.
            This will skip deployment of the system cert-manager and trust-manager.
          text: >
             az iot ops init --cluster mycluster -g myresourcegroup --user-trust

    """

    helps[
        "iot ops create"
    ] = """
        type: command
        short-summary: Create an IoT Operations instance.
        long-summary: |
                      A succesful execution of init is required before running this command.

                      The result of the command nets an IoT Operations instance with
                      a set of default resources configured for cohesive function.

        examples:
        - name: Create the target instance with minimum input.
          text: >
            az iot ops create --cluster mycluster -g myresourcegroup --name myinstance --sr-resource-id $SCHEMA_REGISTRY_RESOURCE_ID
        - name: The following example adds customization to the default broker instance resource
            as well as an instance description and tags.
          text: >
             az iot ops create --cluster mycluster -g myresourcegroup --name myinstance --sr-resource-id $SCHEMA_REGISTRY_RESOURCE_ID
             --broker-mem-profile High --broker-backend-workers 4 --description 'Contoso Factory'
             --tags tier=testX1
        - name: This example shows deploying an additional insecure (no authn or authz) broker listener
            configured for port 1883 of service type load balancer. Useful for testing and/or demos.
            Do not use the insecure option in production.
          text: >
             az iot ops create --cluster mycluster -g myresourcegroup --name myinstance --sr-resource-id $SCHEMA_REGISTRY_RESOURCE_ID
             --add-insecure-listener
        - name: This form shows how to enable resource sync for the instance deployment.
            To enable resource sync role assignment write is necessary on the target resource group.
          text: >
             az iot ops create --cluster mycluster -g myresourcegroup --name myinstance --sr-resource-id $SCHEMA_REGISTRY_RESOURCE_ID
             --enable-rsync
        - name: This example highlights trust settings for a user provided cert-manager config.
            Note that the cluster must have been initialized with `--user-trust` and a user cert-manager deployment must be present.
          text: >
              az iot ops create --cluster mycluster -g myresourcegroup --name myinstance --sr-resource-id $SCHEMA_REGISTRY_RESOURCE_ID
              --trust-settings configMapName=example-bundle configMapKey=trust-bundle.pem
              issuerKind=ClusterIssuer issuerName=trust-manager-selfsigned-issuer

    """

    helps[
        "iot ops delete"
    ] = """
        type: command
        short-summary: Delete IoT Operations from the cluster.
        long-summary: |
            The name of either the instance or cluster must be provided.

            The operation uses Azure Resource Graph to determine correlated resources.
            Resource Graph being eventually consistent does not guarantee a synchronized state at the
            time of execution.

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
        - name: Use cluster name instead of instance for lookup.
          text: >
            az iot ops delete --cluster mycluster -g myresourcegroup
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

          If this command fails, please use `az iot ops upgrade` to upgrade your instance to the latest version before continuing.

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
        long-summary: Currently instance tags and description can be updated. If you want to upgrade your instance to a newer version, please use `az iot ops upgrade` instead.

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
        "iot ops upgrade"
    ] = """
        type: command
        short-summary: Upgrade an IoT Operations instance to the latest version.
        long-summary: |
                      WARNING: This command may fail and require you to delete and re-create your cluster and instance.

                      Upgrade an IoT Operations instance, including updating the extensions to the latest versions.
                      Use this command if `az iot ops show` or similiar commands are failing.

                      Schema registry resource Id is an optional parameter and may be required in specific scenarios.
        examples:
        - name: Upgrade the instance with minimal inputs.
          text: >
            az iot ops upgrade --name myinstance -g myresourcegroup
        - name: Skip the conformation prompt during instance upgrade.
          text: >
            az iot ops upgrade --name myinstance -g myresourcegroup -y
        - name: Upgrade the instance and specify the schema registry resource Id.
          text: >
            az iot ops upgrade --name myinstance -g myresourcegroup --sr-resource-id $SCHEMA_REGISTRY_RESOURCE_ID
    """

    helps[
        "iot ops identity"
    ] = """
        type: group
        short-summary: Instance identity management.
    """

    helps[
        "iot ops identity assign"
    ] = """
        type: command
        short-summary: Assign a user-assigned managed identity with the instance.
        long-summary: |
            This operation includes federation of the identity.

        examples:
        - name: Assign and federate a desired user-assigned managed identity.
          text: >
            az iot ops identity assign --name myinstance -g myresourcegroup --mi-user-assigned $UA_MI_RESOURCE_ID
    """

    helps[
        "iot ops identity show"
    ] = """
        type: command
        short-summary: Show the instance identities.

        examples:
        - name: Show the identities associated with the target instance.
          text: >
            az iot ops identity show --name myinstance -g myresourcegroup
    """

    helps[
        "iot ops identity remove"
    ] = """
        type: command
        short-summary: Remove a user-assigned managed identity from the instance.

        examples:
        - name: Remove the desired user-assigned managed identity from the instance.
          text: >
            az iot ops identity remove --name myinstance -g myresourcegroup --mi-user-assigned $UA_MI_RESOURCE_ID
    """

    helps[
        "iot ops secretsync"
    ] = """
        type: group
        short-summary: Instance secret sync management.
    """

    helps[
        "iot ops secretsync enable"
    ] = """
        type: command
        short-summary: Enable secret sync for an instance.
        long-summary: |
            The operation handles federation, creation of a secret provider class
            and role assignments of the managed identity to the target Key Vault.

            Only one Secret Provider Class must be associated to the instance at a time.

        examples:
        - name: Enable the target instance for Key Vault secret sync.
          text: >
            az iot ops secretsync enable --name myinstance -g myresourcegroup
            --mi-user-assigned $UA_MI_RESOURCE_ID --kv-resource-id $KEYVAULT_RESOURCE_ID
        - name: Same as prior example except flag to skip Key Vault role assignments.
          text: >
            az iot ops secretsync enable --name myinstance -g myresourcegroup
            --mi-user-assigned $UA_MI_RESOURCE_ID --kv-resource-id $KEYVAULT_RESOURCE_ID --skip-ra
    """

    helps[
        "iot ops secretsync list"
    ] = """
        type: command
        short-summary: List the secret sync configs associated with an instance.

        examples:
        - name: List the secret sync configs associated with an instance.
          text: >
            az iot ops secretsync list --name myinstance -g myresourcegroup
    """

    helps[
        "iot ops secretsync disable"
    ] = """
        type: command
        short-summary: Disable secret sync for an instance.
        long-summary: |
          All the secret provider classes associated with the instance, and all the secret
          syncs associated with the secret provider classes will be deleted.

        examples:
        - name: Disable secret sync for an instance.
          text: >
            az iot ops secretsync disable --name myinstance -g myresourcegroup
    """

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
        "iot ops asset endpoint create opcua"
    ] = """
        type: command
        short-summary: Create an asset endpoint profile with an OPCUA connector.
        long-summary: |
                      Azure IoT OPC UA Connector (preview) uses the same client certificate for all secure
                      channels between itself and the OPC UA servers that it connects to.

                      For OPC UA connector arguments, a value of -1 means that parameter will not be used (ex: --session-reconnect-backoff -1 means that no exponential backoff should be used).
                      A value of 0 means use the fastest practical rate (ex: --default-sampling-int 0 means use the fastest sampling interval possible for the server).

                      For more information on how to create an OPCUA connector, please see aka.ms/opcua-quickstart
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
        - name: Create an asset endpoint with certificate user authentication using the given given instance in the same resource group.
          text: >
            az iot ops asset endpoint create opcua --name myprofile -g myresourcegroup --instance myinstance
            --target-address opc.tcp://opcplc-000000:50000 --certificate-ref mycertificate.pem
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

    helps[
        "iot ops schema"
    ] = """
        type: group
        short-summary: Schema and registry management.
        long-summary: |
          Schemas are documents that describe data to enable processing and contextualization.
          Message schemas describe the format of a message and its contents.
          A schema registry is required to create and manage schemas.
    """

    helps[
        "iot ops schema show"
    ] = """
        type: command
        short-summary: Show details of a schema within a schema registry.
        examples:
        - name: Show details of target schema 'myschema' within a schema registry 'myregistry'.
          text: >
            az iot ops schema show --name myschema --registry myregistry -g myresourcegroup
    """

    helps[
        "iot ops schema list"
    ] = """
        type: command
        short-summary: List schemas within a schema registry.
        examples:
        - name: List schema registeries in the schema registry 'myregistry'.
          text: >
            az iot ops schema list -g myresourcegroup --registry myregistry
    """

    helps[
        "iot ops schema delete"
    ] = """
        type: command
        short-summary: Delete a target schema within a schema registry.
        examples:
        - name: Delete a target schema 'myschema' within a schema registry 'myregistry'.
          text: >
            az iot ops schema delete --name myschema --registry myregistry -g myresourcegroup
    """

    helps[
        "iot ops schema create"
    ] = """
        type: command
        short-summary: Create a schema within a schema registry.
        long-summary: |
                      This operation requires a pre-created schema registry and will add a schema version.
                      To create the schema and add a version, the associated storage account will need to have public network access enabled.
                      For more information on the delta file format, please see aka.ms/lakehouse-delta-sample
        examples:
        - name: Create a schema called 'myschema' in the registry 'myregistry' with minimum inputs. Schema version 1 will be created for this schema with the file content.
          text: >
            az iot ops schema create -n myschema -g myresourcegroup --registry myregistry
            --format json --type message --version-content myschema.json
        - name: Create a schema called 'myschema' with additional customization. Schema version 14 will be created for this schema. The inline content is a powershell syntax example.
          text: >
            az iot ops schema create -n myschema -g myresourcegroup --registry myregistry
            --format delta --type message --desc "Schema for Assets" --display-name myassetschema
            --version-content '{\\\"hello\\\": \\\"world\\\"}' --ver 14 --vd "14th version"
        - name: Create a schema called 'myschema'. Schema version 1 will be created for this schema. The inline content is a cmd syntax example.
          text: >
            az iot ops schema create -n myschema -g myresourcegroup --registry myregistry
            --format json --type message --version-content "{\\\"hello\\\": \\\"world\\\"}"
        - name: Create a schema called 'myschema'. Schema version 1 will be created for this schema. The inline content is a bash syntax example.
          text: >
            az iot ops schema create -n myschema -g myresourcegroup --registry myregistry
            --format json --type message --version-content '{"hello": "world"}'
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
                      role against the storage account container scope by default. If necessary you can provide a
                      custom role via --custom-role-id to use instead.

                      If the indicated storage account container does not exist it will be created with default
                      settings.

                      This operation will also register the Microsoft.DeviceRegistry resource provider if it is
                      not registered.
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

    helps[
        "iot ops connector"
    ] = """
        type: group
        short-summary: Connector management.
    """

    helps[
        "iot ops connector opcua"
    ] = """
        type: group
        short-summary: OPC UA connector management.
        long-summary: |
          The connector for OPC UA enables your industrial OPC UA environment to input data into
          your local workloads running on a Kubernetes cluster, and into your cloud workloads.
          See the following resource for more info https://aka.ms/overview-connector-opcua-broker
    """

    helps[
        "iot ops connector opcua trust"
    ] = """
        type: group
        short-summary: Manage trusted certificates for the OPC UA Broker.
        long-summary: |
          The trusted certificate list contains the certificates of all the OPC UA servers that the
          connector for OPC UA trusts. If the connector for OPC UA trusts a certificate authority,
          it automatically trusts any server that has a valid application instance certificate signed
          by the certificate authority.
          For more info, see https://aka.ms/opcua-certificates
    """

    helps[
        "iot ops connector opcua trust add"
    ] = """
        type: command
        short-summary: Add a trusted certificate to the OPC UA Broker's trusted certificate list.
        long-summary: |
            The certificate file extension must be .der or .crt. Azure resource secretproviderclass
            'opc-ua-connector' and secretsync resource 'aio-opc-ua-broker-trust-list' will be created if not found.
        examples:
        - name: Add a trusted certificate to the OPC UA Broker's trusted certificate list.
          text: >
            az iot ops connector opcua trust add --instance instance --resource-group instanceresourcegroup
            --certificate-file "certificate.der"
        - name: Add a trusted certificate to the OPC UA Broker's trusted certificate list with custom secret name.
          text: >
            az iot ops connector opcua trust add --instance instance --resource-group instanceresourcegroup
            --certificate-file "certificate.crt" --secret custom-secret-name
    """

    helps[
        "iot ops connector opcua trust remove"
    ] = """
        type: command
        short-summary: Remove trusted certificate(s) from the OPC UA Broker's trusted certificate list.
        long-summary: |
            Note: Removing all trusted certificates from the OPC UA Broker's trusted certificate list will trigger
            deletion the secretsync resource 'aio-opc-ua-broker-trust-list'.
        examples:
          - name: Remove trusted certificates called 'testcert1.der' and 'testcert2.crt' from trusted certificate list.
            text: >
              az iot ops connector opcua trust remove --instance instance --resource-group instanceresourcegroup
              --certificate-names testcert1.der testcert2.crt
          - name: Remove trusted certificates from trusted certificate list, including remove related keyvault secret.
            text: >
              az iot ops connector opcua trust remove --instance instance --resource-group instanceresourcegroup
              --certificate-names testcert1.der testcert2.crt --include-secrets
          - name: Force remove certificates operation regardless of warnings. May lead to errors.
            text: >
              az iot ops connector opcua trust remove --instance instance --resource-group instanceresourcegroup
              --certificate-names testcert1.der testcert2.crt --force
    """

    helps[
        "iot ops connector opcua trust show"
    ] = """
        type: command
        short-summary: Show details of secretsync resource 'aio-opc-ua-broker-trust-list'.
        examples:
        - name: Show details of 'aio-opc-ua-broker-trust-list' resource.
          text: >
            az iot ops connector opcua trust show --instance instance --resource-group instanceresourcegroup
    """

    helps[
        "iot ops connector opcua issuer"
    ] = """
      type: group
      short-summary: Manage issuer certificates for the OPC UA Broker.
      long-summary: |
        The issuer certificate list stores the certificate authority certificates that the connector
        for OPC UA trusts. If user's OPC UA server's application instance certificate is signed by
        an intermediate certificate authority, but user does not want to automatically trust all the
        certificates issued by the certificate authority, an issuer certificate list can be used to
        manage the trust relationship.
        For more info, see https://aka.ms/opcua-certificates
    """

    helps[
        "iot ops connector opcua issuer add"
    ] = """
        type: command
        short-summary: Add an issuer certificate to the OPC UA Broker's issuer certificate list.
        long-summary: |
            The certificate file extension must be .der, .crt or .crl. When adding a .crl file, a .der
            or .crt file with same file name must be added first. Azure resource secretproviderclass
            'opc-ua-connector'and secretsync 'aio-opc-ua-broker-issuer-list' will be created if not found.
        examples:
        - name: Add an issuer certificate in the OPC UA Broker's issuer certificate list.
          text: >
            az iot ops connector opcua issuer add --instance instance --resource-group instanceresourcegroup
            --certificate-file "certificate.der"
        - name: Add an issuer certificate with .crl extension to the OPC UA Broker's issuer certificate list with same
                file name as the .der file mentioned above.
          text: >
            az iot ops connector opcua issuer add --instance instance --resource-group instanceresourcegroup
            --certificate-file "certificate.crl"
        - name: Add an issuer certificate to the OPC UA Broker's issuer certificate list with custom secret name.
          text: >
            az iot ops connector opcua issuer add --instance instance --resource-group instanceresourcegroup
            --certificate-file "certificate.der" --secret custom-secret-name
    """

    helps[
        "iot ops connector opcua issuer remove"
    ] = """
        type: command
        short-summary: Remove trusted certificate(s) from the OPC UA Broker's issuer certificate list.
        long-summary: |
            Note: Removing all issuer certificates from the OPC UA Broker's issuer certificate list will trigger
            deletion the secretsync resource 'aio-opc-ua-broker-issuer-list'.
            Please make sure to remove corresponding .crl if exist when removing .der/.crt certificate to avoid orphaned secret.
        examples:
          - name: Remove issuer certificates and its revocation list with .crl extension from issuer certificate list.
            text: >
              az iot ops connector opcua issuer remove --instance instance --resource-group instanceresourcegroup
              --certificate-names testcert.der testcert.crl
          - name: Remove issuer certificates from issuer certificate list, including remove related keyvault secret.
            text: >
              az iot ops connector opcua issuer remove --instance instance --resource-group instanceresourcegroup
              --certificate-names testcert.der --include-secrets
          - name: Force remove certificates operation regardless of warnings. May lead to errors.
            text: >
              az iot ops connector opcua issuer remove --instance instance --resource-group instanceresourcegroup
              --certificate-names testcert.der --force
    """

    helps[
        "iot ops connector opcua issuer show"
    ] = """
        type: command
        short-summary: Show details of secretsync resource 'aio-opc-ua-broker-issuer-list'.
        examples:
        - name: Show details of 'aio-opc-ua-broker-issuer-list' secretsync resource.
          text: >
            az iot ops connector opcua issuer show --instance instance --resource-group instanceresourcegroup
    """

    helps[
        "iot ops connector opcua client"
    ] = """
        type: group
        short-summary: Manage enterprise grade client application instance certificate for the OPC UA Broker.
        long-summary: |
          The connector for OPC UA makes use of a single OPC UA application instance certificate
          for all the sessions it establishes to collect telemetry data from OPC UA servers.
          For more info, see https://aka.ms/opcua-certificates
    """

    helps[
        "iot ops connector opcua client add"
    ] = """
        type: command
        short-summary: Add an enterprise grade client application instance certificate.
        long-summary: |
            The public key file extension must be .der and private key file extension
            must be .pem. Please make sure to use same filename for public key and
            private key file. Azure resource secretproviderclass 'opc-ua-connector'
            and secretsync 'aio-opc-ua-broker-client-certificate' will be created
            if not found.
        examples:
        - name: Add an client certificate.
          text: >
            az iot ops connector opcua client add --instance instance --resource-group instanceresourcegroup
            --public-key-file "newopc.der" --private-key-file "newopc.pem" --subject-name "aio-opc-opcuabroker"
            --application-uri "urn:microsoft.com:aio:opc:opcuabroker"
        - name: Add an client certificate with custom public and private key secret name.
          text: >
            az iot ops connector opcua client add
            --instance instance
            --resource-group instanceresourcegroup
            --public-key-file "newopc.der"
            --private-key-file "newopc.pem"
            --public-key-secret public-secret-name
            --private-key-secret private-secret-name
            --subject-name "aio-opc-opcuabroker"
            --application-uri "urn:microsoft.com:aio:opc:opcuabroker"
      """
    
    helps[
        "iot ops connector opcua client remove"
    ] = """
        type: command
        short-summary: Remove client application instance certificate from the OPC UA Broker.
        long-summary: |
            Note: Removing all certificates from the OPC UA Broker's client certificate store will trigger
            deletion of the secretsync resource 'aio-opc-ua-broker-client-certificate'. And this operation
            will trigger the fallback to default (cert-manager based) certificate. This fallback requires
            an aio extension update.
            Please make sure to remove both public(.der) and private key(.pem) certificate pair to avoid orphaned
            secret.
        examples:
          - name: Remove issuer certificates and its revocation list with .crl extension from issuer certificate list.
            text: >
              az iot ops connector opcua issuer remove --instance instance --resource-group instanceresourcegroup
              --certificate-names testcert.der testcert.crl
          - name: Remove issuer certificates from issuer certificate list, including remove related keyvault secret.
            text: >
              az iot ops connector opcua issuer remove --instance instance --resource-group instanceresourcegroup
              --certificate-names testcert.der --include-secrets
          - name: Force remove certificates operation regardless of warnings. May lead to errors.
            text: >
              az iot ops connector opcua issuer remove --instance instance --resource-group instanceresourcegroup
              --certificate-names testcert.der --force
    """

    helps[
        "iot ops schema version"
    ] = """
        type: group
        short-summary: Schema version management.
        long-summary: |
          A schema version contains the schema content associated with that version.
    """

    helps[
        "iot ops schema version show"
    ] = """
        type: command
        short-summary: Show details of a schema version.
        examples:
        - name: Show details of target schema version 1.
          text: >
            az iot ops schema version show --name 1 --schema myschema --registry myregistry -g myresourcegroup
    """

    helps[
        "iot ops schema version list"
    ] = """
        type: command
        short-summary: List schema versions for a specific schema.
        examples:
        - name: List all schema versions for the schema 'myschema' in the schema registry 'myregistry'.
          text: >
            az iot ops schema version list -g myresourcegroup --registry myregistry --schema myschema
    """

    helps[
        "iot ops schema version remove"
    ] = """
        type: command
        short-summary: Remove a target schema version.
        examples:
        - name: Remove schema version 1.
          text: >
            az iot ops schema version remove -n 1 -g myresourcegroup --registry myregistry --schema myschema
    """

    helps[
        "iot ops schema version add"
    ] = """
        type: command
        short-summary: Add a schema version to a schema.
        long-summary: |
                      To add a version, the associated storage account will need to have public network access enabled.
                      For more information on the delta file format, please see aka.ms/lakehouse-delta-sample
        examples:
        - name: Add a schema version 1 to a schema called 'myschema' within the registry 'myregistry' with
                minimum inputs. The content is inline json (powershell syntax example).
          text: >
            az iot ops schema version add -n 1 -g myresourcegroup --registry myregistry --schema myschema --content '{\\\"hello\\\": \\\"world\\\"}'
        - name: Add a schema version 1 to a schema called 'myschema' within the registry 'myregistry' with
                minimum inputs. The content is inline json (cmd syntax example).
          text: >
            az iot ops schema version add -n 1 -g myresourcegroup --registry myregistry --schema myschema --content "{\\\"hello\\\": \\\"world\\\"}"
        - name: Add a schema version 1 to a schema called 'myschema' within the registry 'myregistry' with
                minimum inputs. The content is inline json (bash syntax example).
          text: >
            az iot ops schema version add -n 1 -g myresourcegroup --registry myregistry --schema myschema --content '{"hello": "world"}'
        - name: Add a schema version 2 to a schema called 'myschema' within the registry 'myregistry' with
                a description. The file should contain the schema content.
          text: >
            az iot ops schema version add -n 2 -g myresourcegroup --registry myregistry --schema myschema --content myschemav2.json --desc "New schema"
    """

    helps[
        "iot ops schema show-dataflow-refs"
    ] = """
        type: command
        short-summary: Show the schema references used for dataflows.
        examples:
        - name: Show schema reference for schema "myschema" and version 1.
          text: >
            az iot ops schema show-dataflow-refs --version 1 --schema myschema --registry myregistry -g myresourcegroup
        - name: Show schema reference for all versions in schema "myschema".
          text: >
            az iot ops schema show-dataflow-refs --schema myschema --registry myregistry -g myresourcegroup
        - name: Show schema reference for all versions and schemas in schema registry "myregistry".
          text: >
            az iot ops schema show-dataflow-refs --registry myregistry -g myresourcegroup
        - name: Show schema reference for all schemas but only the latest versions in schema registry "myregistry".
          text: >
            az iot ops schema show-dataflow-refs --registry myregistry -g myresourcegroup --latest
    """
