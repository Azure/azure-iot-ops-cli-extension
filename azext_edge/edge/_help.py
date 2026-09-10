# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------
"""
Help content for Azure IoT Operations commands.
"""

from knack.help_files import helps

from azext_edge.edge.providers.edge_api import (
    ARCCONTAINERSTORAGE_API_V1,
    CERTMANAGER_API_V1,
    CONTAINERSTORAGE_API_V1,
    SECRETSTORE_API_V1,
    SECRETSYNC_API_V1,
    TRUSTMANAGER_API_V1,
)

from .common import GET_VERSIONS_URL
from .providers.orchestration.common import (
    CLONE_INSTANCE_VERS_MAX,
    CLONE_INSTANCE_VERS_MIN,
    MIN_INSTANCE_VERSION_V2,
)
from .providers.support_bundle import (
    COMPAT_CLUSTER_CONFIG_APIS,
    COMPAT_DATAFLOW_APIS,
    COMPAT_DEVICEREGISTRY_APIS,
    COMPAT_MQTT_BROKER_APIS,
)

# cause help barfs on anything not indented correctly
DEVICEREGISTRY_API_STR_FOR_HELP = COMPAT_DEVICEREGISTRY_APIS.as_str().strip().replace("\n", "\n            - ")


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
            - {DEVICEREGISTRY_API_STR_FOR_HELP}
            - {CERTMANAGER_API_V1.as_str()}
            - {COMPAT_CLUSTER_CONFIG_APIS.as_str()}
            - {COMPAT_DATAFLOW_APIS.as_str()}
            - {ARCCONTAINERSTORAGE_API_V1.as_str()}
            - {CONTAINERSTORAGE_API_V1.as_str()}
            - {SECRETSYNC_API_V1.as_str()}
            - {SECRETSTORE_API_V1.as_str()}
            - {TRUSTMANAGER_API_V1.as_str()}

            Note: logs from evicted pod will not be captured, as they are inaccessible. For details
            on why a pod was evicted, please refer to the related pod and node files.

        examples:
        - name: Basic usage with default options. This form of the command will auto detect IoT Operations APIs and build a suitable bundle
                capturing the last 24 hours of container logs. The bundle will be produced in the current working directory.
          text: >
            az iot ops support create-bundle

        - name: Constrain data capture on a specific service as well as producing the bundle in a custom output dir.
          text: >
            az iot ops support create-bundle --ops-service connectors --bundle-dir ~/ops

        - name: Produce the bundle in a custom output directory and use a custom name.
          text: >
            az iot ops support create-bundle --bundle-name mybundle --bundle-dir ~/ops

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
            az iot ops support create-bundle --ops-service broker connectors deviceregistry

        - name: Include multiple services in the support bundle with multiple --ops-service flags.
          text: >
            az iot ops support create-bundle --ops-service broker --ops-service connectors --ops-service deviceregistry
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
            - {DEVICEREGISTRY_API_STR_FOR_HELP}
            - {COMPAT_MQTT_BROKER_APIS.as_str()}
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
        - name: Show details of the default instance mqtt broker.
          text: >
            az iot ops broker show -n default --in myinstance -g myresourcegroup
    """

    helps[
        "iot ops broker list"
    ] = """
        type: command
        short-summary: List mqtt brokers associated with an instance.

        examples:
        - name: Enumerate all mqtt brokers in the instance.
          text: >
            az iot ops broker list --in myinstance -g myresourcegroup
    """

    helps[
        "iot ops broker delete"
    ] = """
        type: command
        short-summary: Delete an mqtt broker.

        examples:
        - name: Delete the default mqtt broker from the instance.
          text: >
            az iot ops broker delete --in myinstance -g myresourcegroup
        - name: Same as prior example but skipping the confirmation prompt.
          text: >
            az iot ops broker delete --in myinstance -g myresourcegroup -y
    """

    helps[
        "iot ops broker persist"
    ] = """
        type: group
        short-summary: Mqtt broker disk persistence management.
    """

    helps[
        "iot ops broker persist update"
    ] = """
        type: command
        short-summary: Update an mqtt broker's disk persistence settings.
        long-summary: |
          Updating disk persistence depends on enablement at broker create time.
          Setting the persistence mode of a broker component will reset its configuration.

        examples:
        - name: Update the persistence mode of subscriber message queues, retain topics and state store.
          text: >
            az iot ops broker persist update --in myinstance -g myresourcegroup --persist-mode subscriberQueue=All retain=All stateStore=All
        - name: Update a custom persistence policy for retain messages.
          text: >
            az iot ops broker persist update --in myinstance -g myresourcegroup --persist-mode retain=Custom --retain-topics "sensor1" "factory/#" "groundfloor/+/temperature"
        - name: Set up state store persistence with multiple key groups including string, pattern, and binary (base64 encoded) keys.
          text: >
            az iot ops broker persist update --in myinstance -g myresourcegroup --persist-mode stateStore=Custom
            --state-store-str-keys "device-001" "device-002" --state-store-glob-keys "sensors/*" --state-store-bin-keys "bXlrZXkx" "bXlrZXky"
        - name: Configure subscriber queue persistence for specific client IDs.
          text: >
            az iot ops broker persist update --in myinstance -g myresourcegroup --persist-mode subscriberQueue=Custom
            --subscriber-client-ids "factory-client-*" "sensor-gateway-01"
        - name: Advanced configuration with multiple persistence modes, state store key groupings, and dynamic settings for a custom broker.
          text: >
            az iot ops broker persist update --in myinstance -g myresourcegroup --name default --persist-mode retain=Custom stateStore=Custom subscriberQueue=All
            --retain-topics "alerts/#" "diagnostics/#" --state-store-str-keys "user:admin" "session:active" --state-store-str-keys "config:database" "config:security"
            --state-store-glob-keys "logs/*" "backups/*" --disable-dynamic stateStore
    """

    helps[
        "iot ops broker listener"
    ] = """
        type: group
        short-summary: Mqtt broker listener management.
    """

    helps[
        "iot ops broker listener apply"
    ] = """
        type: command
        short-summary: Create or replace an mqtt broker listener service.
        long-summary: |
          An example of the config file format is as follows:

          ```
          {
            "serviceType": "LoadBalancer",
            "ports": [
                {
                    "port": 1883,
                    "protocol": "Mqtt"
                },
                {
                    "authenticationRef": "default",
                    "port": 8883,
                    "protocol": "Mqtt",
                    "tls": {
                        "mode": "Automatic",
                        "certManagerCertificateSpec": {
                            "issuerRef": {
                                "name": "azure-iot-operations-aio-certificate-issuer",
                                "kind": "ClusterIssuer",
                                "group": "cert-manager.io"
                            }
                        }
                    }
                }
            ]
          }
          ```

          When used with apply the above content will create or replace a target listener
          with a two port configuration.

        examples:
        - name: Create or replace a listener for the default broker using a config file.
          text: >
            az iot ops broker listener apply -n listener --in myinstance -g myresourcegroup --config-file /path/to/listener/config.json

    """

    helps[
        "iot ops broker listener port"
    ] = """
        type: group
        short-summary: Mqtt broker listener port operations.
    """

    helps[
        "iot ops broker listener port add"
    ] = """
        type: command
        short-summary: Add a tcp port config to an mqtt broker listener service.
        long-summary: This is an add or replace (port) operation. If the target listener resource does not exist the command will create it.

        examples:
        - name: Add a port config to the default cluster Ip listener, using port 8883 and an authn resource.
          text: >
            az iot ops broker listener port add --port 8883 --authn authn --listener default --in myinstance -g mygroup
        - name: Create a new listener with service type load balancer using a port config accepting tcp connections on port 1883 with no authz or authn.
          text: >
            az iot ops broker listener port add --port 1883 --listener newlistener --in myinstance -g mygroup
        - name: Add a port config to an existing listener using basic auto tls settings on port 8883 with authn.
          text: >
            az iot ops broker listener port add --port 8883 --authn authn --tls-issuer-ref issuer=azure-iot-operations-aio-certificate-issuer kind=ClusterIssuer
            --listener newlistener --in myinstance -g mygroup
    """

    helps[
        "iot ops broker listener port remove"
    ] = """
        type: command
        short-summary: Remove a tcp port config from an mqtt broker listener service.
        long-summary: If no tcp ports will exist after removal the command will delete the listener resource.

        examples:
        - name: Remove tcp port 1883 config from a listener. The listener will be deleted if no ports remain.
          text: >
            az iot ops broker listener port remove --port 1883 --listener mylistener --in myinstance -g mygroup
    """

    helps[
        "iot ops broker listener show"
    ] = """
        type: command
        short-summary: Show details of an mqtt broker listener.

        examples:
        - name: Show details of the default listener associated with the default broker.
          text: >
            az iot ops broker listener show -n default --in myinstance -g myresourcegroup
    """

    helps[
        "iot ops broker listener list"
    ] = """
        type: command
        short-summary: List mqtt broker listeners associated with a broker.

        examples:
        - name: Enumerate all mqtt broker listeners associated with the default broker.
          text: >
            az iot ops broker listener list --in myinstance -g myresourcegroup
    """

    helps[
        "iot ops broker listener delete"
    ] = """
        type: command
        short-summary: Delete an mqtt broker listener.

        examples:
        - name: Delete an mqtt broker listener associated with the default broker.
          text: >
            az iot ops broker listener delete -n listener --in myinstance -g myresourcegroup
        - name: Same as prior example but skipping the confirmation prompt.
          text: >
            az iot ops broker listener delete -n listener --in myinstance -g myresourcegroup -y
    """

    helps[
        "iot ops broker authn"
    ] = """
        type: group
        short-summary: Mqtt broker authentication management.
    """

    helps[
        "iot ops broker authn apply"
    ] = """
        type: command
        short-summary: Create or replace an mqtt broker authentication resource.
        long-summary: |
          An example of the config file format is as follows:

          ```
          {
              "authenticationMethods": [
                  {
                      "method": "Custom",
                      "customSettings": {
                          "endpoint": "https://auth-server-template",
                          "caCertConfigMap": "custom-auth-ca",
                          "auth": {
                              "x509": {
                                  "secretRef": "custom-auth-client-cert"
                              }
                          },
                          "headers": {
                              "header_key": "header_value"
                          }
                      }
                  },
                  {
                      "method": "ServiceAccountToken",
                      "serviceAccountTokenSettings": {
                          "audiences": [
                              "aio-internal",
                              "my-audience"
                          ]
                      }
                  },
                  {
                      "method": "X509",
                      "x509Settings": {
                          "trustedClientCaCert": "client-ca",
                          "authorizationAttributes": {
                              "root": {
                                  "attributes": {
                                      "organization": "contoso"
                                  },
                                  "subject": "CN = Contoso Root CA Cert, OU = Engineering, C = US"
                              },
                              "intermediate": {
                                  "attributes": {
                                      "city": "seattle",
                                      "foo": "bar"
                                  },
                                  "subject": "CN = Contoso Intermediate CA"
                              },
                              "smartfan": {
                                  "attributes": {
                                      "building": "17"
                                  },
                                  "subject": "CN = smart-fan"
                              }
                          }
                      }
                  }
              ]
          }
          ```

          When used with apply the above content will create or replace a target authentication
          resource configured with three authn methods.

        examples:
        - name: Create or replace an authentication resource for the default broker using a config file.
          text: >
            az iot ops broker authn apply -n authn --in myinstance -g myresourcegroup --config-file /path/to/authn/config.json
    """

    helps[
        "iot ops broker authn method"
    ] = """
        type: group
        short-summary: Mqtt broker authn method operations.
    """

    helps[
        "iot ops broker authn method add"
    ] = """
        type: command
        short-summary: Add authentication methods to an mqtt broker authentication resource.
        long-summary: This is an add method(s) operation. If the target authentication resource
          does not exist the command will create it.

        examples:
        - name: Configure a SAT authn method and add it to the existing default authn resource.
          text: >
            az iot ops broker authn method add --authn default --in myinstance -g myresourcegroup --sat-aud my-audience1 my-audience2
        - name: Configure an x509 authn method and add it to a newly created authn resource.
          text: >
            az iot ops broker authn method add --authn myauthn --in myinstance -g myresourcegroup
            --x509-client-ca-ref client-ca
            --x509-attr root.subject='CN = Contoso Root CA Cert, OU = Engineering, C = US' root.attributes.organization=contoso
            --x509-attr intermediate.subject='CN = Contoso Intermediate CA' intermediate.attributes.city=seattle intermediate.attributes.foo=bar
            --x509-attr smartfan.subject='CN = smart-fan' smartfan.attributes.building=17
        - name: Configure a custom authentication service authn method and add it to a newly created authn resource.
          text: >
            az iot ops broker authn method add --authn myauthn --in myinstance -g myresourcegroup
            --custom-ep https://myauthserver --custom-ca-ref myconfigmap --custom-x509-secret-ref mysecret --custom-header a=b c=d
        - name: Configure and add two separate authn methods to an existing authn resource.
          text: >
            az iot ops broker authn method add --authn myexistingauthn --in myinstance -g myresourcegroup --sat-aud my-audience1 my-audience2
            --x509-client-ca-ref client-ca
    """

    helps[
        "iot ops broker authn show"
    ] = """
        type: command
        short-summary: Show details of an mqtt broker authentication resource.

        examples:
        - name: Show details of the default authentication resource associated with the default broker.
          text: >
            az iot ops broker authn show -n authn --in myinstance -g myresourcegroup
    """

    helps[
        "iot ops broker authn list"
    ] = """
        type: command
        short-summary: List mqtt broker authentication resources associated with a broker.

        examples:
        - name: Enumerate all broker authentication resources associated with the default broker.
          text: >
            az iot ops broker authn list --in myinstance -g myresourcegroup
    """

    helps[
        "iot ops broker authn delete"
    ] = """
        type: command
        short-summary: Delete an mqtt broker authentication resource.

        examples:
        - name: Delete the broker authentication resource called 'authn' associated with the default broker.
          text: >
            az iot ops broker authn delete -n authn --in myinstance -g myresourcegroup
        - name: Same as prior example but skipping the confirmation prompt.
          text: >
            az iot ops broker authn delete -n authn --in myinstance -g myresourcegroup -y
    """

    helps[
        "iot ops broker authz"
    ] = """
        type: group
        short-summary: Mqtt broker authorization management.
    """

    helps[
        "iot ops broker authz apply"
    ] = """
        type: command
        short-summary: Create or replace an mqtt broker authorization resource.
        long-summary: |
          An example of the config file format is as follows:

          ```
          {
              "authorizationPolicies": {
                  "cache": "Enabled",
                  "rules": [
                      {
                          "principals": {
                              "clientIds": [
                                  "temperature-sensor",
                                  "humidity-sensor"
                              ],
                              "attributes": [
                                  {
                                      "city": "seattle",
                                      "organization": "contoso"
                                  }
                              ]
                          },
                          "brokerResources": [
                              {
                                  "method": "Connect"
                              },
                              {
                                  "method": "Publish",
                                  "topics": [
                                      "/telemetry/{principal.clientId}",
                                      "/telemetry/{principal.attributes.organization}"
                                  ]
                              },
                              {
                                  "method": "Subscribe",
                                  "topics": [
                                      "/commands/{principal.attributes.organization}"
                                  ]
                              }
                          ]
                      }
                  ]
              }
          }
          ```

          When used with apply the above content will create or replace a target authorization
          resource configured with a single authz rule.

        examples:
        - name: Create or replace an authorization resource for the default broker using a config file.
          text: >
            az iot ops broker authz apply -n authz --in myinstance -g myresourcegroup --config-file /path/to/authz/config.json
    """

    helps[
        "iot ops broker authz show"
    ] = """
        type: command
        short-summary: Show details of an mqtt broker authorization resource.

        examples:
        - name: Show details of the default authorization resource associated with the default broker.
          text: >
            az iot ops broker authz show -n authz --in myinstance -g myresourcegroup
    """

    helps[
        "iot ops broker authz list"
    ] = """
        type: command
        short-summary: List mqtt broker authorization resources associated with a broker.

        examples:
        - name: Enumerate all mqtt broker authorization resources associated with the default broker.
          text: >
            az iot ops broker authz list --in myinstance -g myresourcegroup
    """

    helps[
        "iot ops broker authz delete"
    ] = """
        type: command
        short-summary: Delete an mqtt broker authorization resource.

        examples:
        - name: Delete the mqtt broker authorization resource called 'authz' associated with the default broker.
          text: >
            az iot ops broker authz delete -n authz --in myinstance -g myresourcegroup
        - name: Same as prior example but skipping the confirmation prompt.
          text: >
            az iot ops broker authz delete -n authz --in myinstance -g myresourcegroup -y
    """

    helps[
        "iot ops dataflow"
    ] = """
        type: group
        short-summary: Dataflow management.
    """

    helps[
        "iot ops dataflow apply"
    ] = """
        type: command
        short-summary: Create or replace a dataflow associated with a dataflow profile.
        long-summary: |
          An example of the config file format is as follows:

          ```
          {
            "mode": "Enabled",
            "operations": [
              {
                "operationType": "Source",
                "sourceSettings": {
                  "endpointRef": "myenpoint1",
                  "assetRef": "",
                  "serializationFormat": "Json",
                  "schemaRef": "myschema1",
                  "dataSources": [
                    "testfrom"
                  ]
                }
              },
              {
                "operationType": "BuiltInTransformation",
                "builtInTransformationSettings": {
                  "serializationFormat": "Json",
                  "datasets": [],
                  "filter": [
                    {
                      "type": "Filter",
                      "description": "",
                      "inputs": [
                        "$metadata.user_property.value"
                      ],
                      "expression": "$1 > 100"
                    }
                  ],
                  "map": [
                    {
                      "type": "PassThrough",
                      "inputs": [
                        "*"
                      ],
                      "output": "*"
                    }
                  ]
                }
              },
              {
                "operationType": "Destination",
                "destinationSettings": {
                  "endpointRef": "myenpoint2",
                  "dataDestination": "test"
                }
              }
            ]
          }
          ```

          When used with apply the above content will create or replace a target dataflow resource.

        examples:
        - name: Create or replace a dataflow 'mydataflow' associated with a profile 'myprofile' using a config file.
          text: >
            az iot ops dataflow apply -n mydataflow -p myprofile --in myinstance -g myresourcegroup --config-file /path/to/dataflow/config.json
    """

    helps[
        "iot ops dataflow delete"
    ] = """
        type: command
        short-summary: Delete a dataflow associated with a dataflow profile.

        examples:
        - name: Delete a dataflow 'mydataflow' associated with a profile 'myprofile'.
          text: >
            az iot ops dataflow delete -n mydataflow -p myprofile --in mycluster-ops-instance -g myresourcegroup
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
        "iot ops dataflowgraph"
    ] = """
        type: group
        short-summary: DataflowGraph management.
    """

    helps[
        "iot ops dataflowgraph apply"
    ] = """
        type: command
        short-summary: Create or replace a DataflowGraph associated with a dataflow profile.
        long-summary: |
          An example of the config file format is as follows:

          ```
          {
            "mode": "Enabled",
            "nodes": [
              {
                "name": "source-mqtt",
                "nodeType": "Source",
                "sourceSettings": {
                  "endpointRef": "default-broker",
                  "dataSources": ["sensors/temperature/#"]
                }
              },
              {
                "name": "dest-broker",
                "nodeType": "Destination",
                "destinationSettings": {
                  "endpointRef": "my-kafka-endpoint",
                  "dataDestination": "telemetry/temperature"
                }
              },
              {
                "name": "dest-otel",
                "nodeType": "Destination",
                "destinationSettings": {
                  "endpointRef": "my-otel-endpoint",
                  "dataDestination": "telemetry/all"
                }
              },
              {
                "name": "graph-processor",
                "nodeType": "Graph",
                "graphSettings": {
                  "registryEndpointRef": "my-registry-endpoint",
                  "artifact": "my-processing-module:1.0.0",
                  "configuration": [
                    { "key": "paramName", "value": "paramValue" },
                    { "key": "anotherParam", "value": "anotherValue" }
                  ]
                }
              }
            ],
            "nodeConnections": [
              { "from": { "name": "source-mqtt" }, "to": { "name": "graph-processor" } },
              { "from": { "name": "graph-processor" }, "to": { "name": "dest-broker" } },
              { "from": { "name": "graph-processor" }, "to": { "name": "dest-otel" } }
            ]
          }
          ```

          The above example defines a graph with an MQTT source flowing through a Graph processing
          node that fans out to a Kafka destination and an OpenTelemetry destination. Graph nodes
          reference an artifact (format: `<name>:<version>`) from a registry endpoint. The
          example above includes graphSettings.configuration only to illustrate the format when
          an artifact requires configuration parameters; in that case, supply them as a list of
          {"key", "value"} string pairs. Omit graphSettings.configuration entirely when no
          configuration is needed.
          Supported nodeTypes are: Source, Destination, and Graph. Data flow graphs support only
          MQTT, Kafka, and OpenTelemetry endpoints. The file can also be the full ARM resource
          wrapper (properties is auto-extracted). extendedLocation is always auto-populated from
          --instance and -g and must not be included in the file.

          When used with apply the above content will create or replace a target DataflowGraph resource.

        examples:
        - name: Create or replace a DataflowGraph 'mygraph' associated with a profile 'myprofile' using a config file.
          text: >
            az iot ops dataflowgraph apply -n mygraph -p myprofile -i myinstance -g myresourcegroup --config-file /path/to/graph/config.json
    """

    helps[
        "iot ops dataflowgraph delete"
    ] = """
        type: command
        short-summary: Delete a DataflowGraph associated with a dataflow profile.

        examples:
        - name: Delete a DataflowGraph 'mygraph' associated with a profile 'myprofile'.
          text: >
            az iot ops dataflowgraph delete -n mygraph -p myprofile -i mycluster-ops-instance -g myresourcegroup
        - name: Delete a DataflowGraph 'mygraph' without a confirmation prompt.
          text: >
            az iot ops dataflowgraph delete -n mygraph -p myprofile -i mycluster-ops-instance -g myresourcegroup -y
    """

    helps[
        "iot ops dataflowgraph show"
    ] = """
        type: command
        short-summary: Show details of a DataflowGraph associated with a dataflow profile.

        examples:
        - name: Show details of a DataflowGraph 'mygraph' associated with a profile 'myprofile'.
          text: >
            az iot ops dataflowgraph show -n mygraph -p myprofile -i mycluster-ops-instance -g myresourcegroup
    """

    helps[
        "iot ops dataflowgraph list"
    ] = """
        type: command
        short-summary: List DataflowGraphs associated with a dataflow profile.

        examples:
        - name: Enumerate DataflowGraphs associated with the profile 'myprofile'.
          text: >
            az iot ops dataflowgraph list -p myprofile -i mycluster-ops-instance -g myresourcegroup
    """

    helps[
        "iot ops registry"
    ] = """
        type: group
        short-summary: Manage container registry endpoints.
    """

    helps[
        "iot ops registry create"
    ] = """
        type: command
        short-summary: Create a container registry endpoint for an instance.
        long-summary: |
          By default, the registry endpoint will use System Assigned Managed Identity authentication.
          Use the --no-auth flag to explicitly configure anonymous authentication.

        examples:
        - name: Create a registry endpoint with default System Assigned Managed Identity authentication.
          text: >
            az iot ops registry create -n myregistry --host myregistry.azurecr.io -i myinstance -g myresourcegroup
        - name: Create a registry endpoint with explicit anonymous authentication.
          text: >
            az iot ops registry create -n myregistry --host myregistry.azurecr.io -i myinstance -g myresourcegroup --no-auth
        - name: Create a registry endpoint with system-assigned managed identity and optional audience configuration
          text: >
            az iot ops registry create -n myregistry --host myregistry.azurecr.io -i myinstance -g myresourcegroup
            --auth-type SystemAssignedManagedIdentity --aud myaudience
        - name: Create a registry endpoint with kubernetes secret reference authentication
          text: >
            az iot ops registry create -n myregistry --host myregistry.azurecr.io -i myinstance -g myresourcegroup
            --auth-type ArtifactPullSecret --secret-ref mysecret
        - name: Create a registry endpoint with user-assigned managed identity configuration
          text: >
            az iot ops registry create -n myregistry --host myregistry.azurecr.io -i myinstance -g myresourcegroup
            --auth-type UserAssignedManagedIdentity --scope myscope --cid myclientid --tid mytenantid
        - name: Create a registry endpoint with a code signing CA secret reference
          text: >
            az iot ops registry create -n myregistry --host myregistry.azurecr.io -i myinstance -g myresourcegroup
            --cs-secret-refs mysecret
        - name: Create a registry endpoint with multiple code signing CA secret and configmap references
          text: >
            az iot ops registry create -n myregistry --host myregistry.azurecr.io -i myinstance -g myresourcegroup
            --cs-config-map-refs configmap1 configmap2 --cs-secret-refs secret1 secret2
    """

    helps[
        "iot ops registry update"
    ] = """
        type: command
        short-summary: Update a container registry endpoint.
        long-summary: |
          Note: updating code signing CA reference properties will overwrite existing config map and secret references.

        examples:
        - name: Update an endpoint's hostname and auth-type to use a system-assigned managed identity
          text: >
            az iot ops registry update -n myregistry --host newregistry.azurecr.io -i myinstance -g myresourcegroup --auth-type SystemAssignedManagedIdentity
        - name: Update an endpoint to set a code signing CA config map reference
          text: >
            az iot ops registry update -n myregistry -i myinstance -g myresourcegroup --cs-config-map-refs myconfigmap
        - name: Update an endpoint to set multiple code signing CA secret references
          text: >
            az iot ops registry update -n myregistry -i myinstance -g myresourcegroup --cs-secret-refs secret1 secret2
    """

    helps[
        "iot ops registry list"
    ] = """
        type: command
        short-summary: List configured container registry endpoints.

        examples:
        - name: List all registry endpoints for an instance.
          text: >
            az iot ops registry list -i myinstance -g myresourcegroup
    """

    helps[
        "iot ops registry show"
    ] = """
        type: command
        short-summary: Show details of a container registry endpoint.

        examples:
        - name: Show details of a registry endpoint.
          text: >
            az iot ops registry show -n myregistry -i myinstance -g myresourcegroup
    """

    helps[
        "iot ops registry delete"
    ] = """
        type: command
        short-summary: Delete a container registry endpoint.

        examples:
        - name: Delete a registry endpoint.
          text: >
            az iot ops registry delete -n myregistry -i myinstance -g myresourcegroup
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
        "iot ops dataflow profile create"
    ] = """
        type: command
        short-summary: Create or replace a dataflow profile.

        examples:
        - name: Create a dataflow profile in the instance 'mycluster-ops-instance' with default properties.
          text: >
            az iot ops dataflow profile create -n myprofile --in mycluster-ops-instance -g myresourcegroup
        - name: Create a dataflow profile in the instance 'mycluster-ops-instance' with 2 profile instances.
          text: >
            az iot ops dataflow profile create -n myprofile --in mycluster-ops-instance -g myresourcegroup --profile-instances 2
    """

    helps[
        "iot ops dataflow profile update"
    ] = """
        type: command
        short-summary: Update a dataflow profile.

        examples:
        - name: Update the log level of the dataflow profile 'myprofile' to 'debug'.
          text: >
            az iot ops dataflow profile update -n myprofile --in mycluster-ops-instance -g myresourcegroup --log-level debug
    """

    helps[
        "iot ops dataflow profile delete"
    ] = """
        type: command
        short-summary: Delete a dataflow profile.
        long-summary: Deleting a dataflow profile will also delete associated dataflows.

        examples:
        - name: Delete the dataflow profile 'myprofile' in the instance 'mycluster-ops-instance'.
          text: >
            az iot ops dataflow profile delete -n myprofile --in mycluster-ops-instance -g myresourcegroup
        - name: Skip the delete confirmation prompt while deleting the dataflow profile 'myprofile' in the instance 'mycluster-ops-instance'.
          text: >
            az iot ops dataflow profile delete -n myprofile --in mycluster-ops-instance -g myresourcegroup -y
    """

    helps[
        "iot ops dataflow endpoint"
    ] = """
        type: group
        short-summary: Dataflow endpoint management.
    """

    helps[
        "iot ops dataflow endpoint create"
    ] = """
        type: group
        short-summary: Create or replace a dataflow endpoint resource.
    """

    helps[
        "iot ops dataflow endpoint create adls"
    ] = """
        type: command
        short-summary: Create or replace a dataflow endpoint resource for Azure Data Lake Storage Gen2.
        long-summary: |
          For more information on Azure Data Lake Storage Gen2 dataflow endpoint, see
          https://aka.ms/adlsv2.
          Note: When using user assigned managed identity authentication method,
          scope will default to `https://storage.azure.com/.default` if not
          specified by `--scope`.

        examples:
        - name: Create or replace a dataflow endpoint resource with minimum input.
          text: >
            az iot ops dataflow endpoint create adls
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --storage-account mystorageaccount
        - name: Create or replace a dataflow endpoint resource using user assigned managed identity authentication method.
          text: >
            az iot ops dataflow endpoint create adls
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --storage-account mystorageaccount
            --client-id 425cb1e9-1247-4cbc-8cdb-1aac9b429696
            --tenant-id bca45660-49a2-4bad-862a-0b9459b4b836
            --scope "https://storage.azure.com/.default"
        - name: Show config for creating a dataflow endpoint resource.
          text: >
            az iot ops dataflow endpoint create adls
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --storage-account mystorageaccount
            --latency 70
            --message-count 100
            --secret-name mysecret
            --show-config
    """

    helps[
        "iot ops dataflow endpoint create adx"
    ] = """
        type: command
        short-summary: Create or replace a dataflow endpoint resource for Azure Data Explorer.
        long-summary: For more information on Azure Data Explorer dataflow endpoint, see https://aka.ms/aio-adx.

        examples:
        - name: Create or replace a dataflow endpoint resource with minimum input.
          text: >
            az iot ops dataflow endpoint create adx
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --database mydatabase
            --host "https://cluster.region.kusto.windows.net"
        - name: Create or replace a dataflow endpoint resource using user assigned managed identity authentication method.
          text: >
            az iot ops dataflow endpoint create adx
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --database mydatabase
            --host "https://cluster.region.kusto.windows.net"
            --client-id 425cb1e9-1247-4cbc-8cdb-1aac9b429696
            --tenant-id bca45660-49a2-4bad-862a-0b9459b4b836
        - name: Show config for creating a dataflow endpoint resource.
          text: >
            az iot ops dataflow endpoint create adx
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --database mydatabase
            --host "https://cluster.region.kusto.windows.net"
            --latency 70
            --message-count 100
            --audience myaudience
            --show-config
    """

    helps[
        "iot ops dataflow endpoint create custom-kafka"
    ] = """
        type: command
        short-summary: Create or replace a dataflow endpoint resource for custom kafka broker.
        long-summary: For more information on custom kafka dataflow endpoint, see https://aka.ms/aio-custom-kafka.

        examples:
        - name: Create or replace a dataflow endpoint resource with minimum input.
          text: >
            az iot ops dataflow endpoint create custom-kafka
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --hostname mykafkabroker
            --port 9092
        - name: Create or replace a dataflow endpoint resource using SASL authentication method.
          text: >
            az iot ops dataflow endpoint create custom-kafka
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --hostname mykafkabroker
            --port 9092
            --sasl-type ScramSha256
            --secret-name mysecret
        - name: Create or replace a dataflow endpoint resource with no auth.
          text: >
            az iot ops dataflow endpoint create custom-kafka
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --hostname mykafkabroker
            --port 9092
            --no-auth
        - name: Show config for creating a dataflow endpoint resource.
          text: >
            az iot ops dataflow endpoint create custom-kafka
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --hostname mykafkabroker
            --port 9092
            --disable-batching
            --latency 70
            --max-bytes 200000
            --message-count 100
            --audience myaudience
            --config-map-ref myconfigmap
            --disable-tls
            --show-config
    """

    helps[
        "iot ops dataflow endpoint create custom-mqtt"
    ] = """
        type: command
        short-summary: Create or replace a dataflow endpoint resource for custom MQTT broker.
        long-summary: For more information on custom MQTT dataflow endpoint, see https://aka.ms/aio-custom-mqtt.

        examples:
        - name: Create or replace a dataflow endpoint resource with minimum input.
          text: >
            az iot ops dataflow endpoint create custom-mqtt
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --hostname mymqttbroker
            --port 9092
        - name: Create or replace a dataflow endpoint resource using Kubernetes Service Account Token authentication method.
          text: >
            az iot ops dataflow endpoint create custom-mqtt
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --hostname mymqttbroker
            --port 9092
            --sat-audience myaudience
            --secret-name mysecret
        - name: Create or replace a dataflow endpoint resource with no auth.
          text: >
            az iot ops dataflow endpoint create custom-mqtt
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --hostname mymqttbroker
            --port 9092
            --no-auth
        - name: Show config for creating a dataflow endpoint resource.
          text: >
            az iot ops dataflow endpoint create custom-mqtt
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --hostname mymqttbroker
            --port 9092
            --client-id-prefix myclientprefix
            --keep-alive 100
            --max-inflight-msg 60
            --protocol WebSockets
            --qos 1
            --retain Never
            --session-expiry 100
            --cloud-event-attribute CreateOrRemap
            --secret-name mysecret
            --disable-tls
            --show-config
    """

    helps[
        "iot ops dataflow endpoint create eventgrid"
    ] = """
        type: command
        short-summary: Create or replace a dataflow endpoint resource for Azure Event Grid.
        long-summary: For more information on Azure Event Grid dataflow endpoint, see https://aka.ms/aio-eventgrid.

        examples:
        - name: Create or replace a dataflow endpoint resource with minimum input.
          text: >
            az iot ops dataflow endpoint create eventgrid
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --hostname "namespace.region-1.ts.eventgrid.azure.net"
            --port 9092
        - name: Create or replace a dataflow endpoint resource using X509 authentication method.
          text: >
            az iot ops dataflow endpoint create eventgrid
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --hostname "namespace.region-1.ts.eventgrid.azure.net"
            --port 9092
            --secret-name mysecret
        - name: Show config for creating a dataflow endpoint resource.
          text: >
            az iot ops dataflow endpoint create eventgrid
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --hostname "namespace.region-1.ts.eventgrid.azure.net"
            --port 9092
            --client-id-prefix myclientprefix
            --keep-alive 100
            --max-inflight-msg 60
            --protocol WebSockets
            --qos 1
            --retain Never
            --session-expiry 100
            --cloud-event-attribute CreateOrRemap
            --secret-name mysecret
            --config-map-ref myconfigmap
            --show-config
    """

    helps[
        "iot ops dataflow endpoint create eventhub"
    ] = """
        type: command
        short-summary: Create or replace a dataflow endpoint resource for kafka-enabled Azure Event Hubs namespace.
        long-summary: For more information on Azure Event Hubs dataflow endpoint, see https://aka.ms/aio-eventhub.

        examples:
        - name: Create or replace a dataflow endpoint resource with minimum input.
          text: >
            az iot ops dataflow endpoint create eventhub
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --eventhub-namespace myeventhubnamespace
        - name: Create or replace a dataflow endpoint resource using user assigned managed identity authentication method.
          text: >
            az iot ops dataflow endpoint create eventhub
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --eventhub-namespace myeventhubnamespace
            --client-id 425cb1e9-1247-4cbc-8cdb-1aac9b429696
            --tenant-id bca45660-49a2-4bad-862a-0b9459b4b836
            --scope "https://eventhubs.azure.net/.default"
        - name: Show config for creating a dataflow endpoint resource.
          text: >
            az iot ops dataflow endpoint create eventhub
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --eventhub-namespace myeventhubnamespace
            --acks One
            --compression Gzip
            --disable-broker-props-copy
            --group-id mygroupid
            --partition-strategy Static
            --max-bytes 200000
            --message-count 100
            --latency 70
            --cloud-event-attribute CreateOrRemap
            --sasl-type ScramSha256
            --secret-name mysecret
            --config-map-ref myconfigmap
            --show-config
    """

    helps[
        "iot ops dataflow endpoint create fabric-onelake"
    ] = """
        type: command
        short-summary: Create or replace a dataflow endpoint resource for Microsoft Fabric OneLake.
        long-summary: For more information on Microsoft Fabric OneLake dataflow endpoint, see https://aka.ms/fabric-onelake.

        examples:
        - name: Create or replace a dataflow endpoint resource with minimum input.
          text: >
            az iot ops dataflow endpoint create fabric-onelake
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --lakehouse mylakehouse
            --workspace myworkspace
            --path-type Files
        - name: Create or replace a dataflow endpoint resource using user assigned managed identity authentication method.
          text: >
            az iot ops dataflow endpoint create fabric-onelake
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --lakehouse mylakehouse
            --workspace myworkspace
            --path-type Files
            --client-id 425cb1e9-1247-4cbc-8cdb-1aac9b429696
            --tenant-id bca45660-49a2-4bad-862a-0b9459b4b836
        - name: Show config for creating a dataflow endpoint resource.
          text: >
            az iot ops dataflow endpoint create fabric-onelake
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --lakehouse mylakehouse
            --workspace myworkspace
            --path-type Files
            --latency 70
            --message-count 100
            --audience myaudience
            --show-config
    """

    helps[
        "iot ops dataflow endpoint create fabric-realtime"
    ] = """
        type: command
        short-summary: Create or replace a Microsoft Fabric Real-Time Intelligence data flow endpoint.
        long-summary: For more information on Microsoft Fabric Real-Time Intelligence dataflow endpoint, see https://aka.ms/aio-fabric-real-time.

        examples:
        - name: Create or replace a dataflow endpoint resource with minimum input.
          text: >
            az iot ops dataflow endpoint create fabric-realtime
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --host "fabricrealtime.servicebus.windows.net:9093"
        - name: Create or replace a dataflow endpoint resource using SASL authentication method.
          text: >
            az iot ops dataflow endpoint create fabric-realtime
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --host "fabricrealtime.servicebus.windows.net:9093"
            --sasl-type ScramSha256
            --secret-name mysecret
        - name: Show config for creating a dataflow endpoint resource.
          text: >
            az iot ops dataflow endpoint create fabric-realtime
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --host "fabricrealtime.servicebus.windows.net:9093"
            --acks One
            --compression Gzip
            --group-id mygroupid
            --partition-strategy Static
            --max-bytes 200000
            --cloud-event-attribute CreateOrRemap
            --disable-tls
            --show-config
    """

    helps[
        "iot ops dataflow endpoint create local-mqtt"
    ] = """
        type: command
        short-summary: Create or replace a Azure IoT Operations Local MQTT dataflow endpoint.
        long-summary: For more information on Azure IoT Operations Local MQTT dataflow endpoint, see https://aka.ms/local-mqtt-broker.

        examples:
        - name: Create or replace a dataflow endpoint resource with minimum input.
          text: >
            az iot ops dataflow endpoint create local-mqtt
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --hostname aio-broker
            --port 1883
        - name: Create or replace a dataflow endpoint resource using X509 authentication method.
          text: >
            az iot ops dataflow endpoint create local-mqtt
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --hostname aio-broker
            --port 1883
            --secret-name mysecret
        - name: Create or replace a dataflow endpoint resource with no auth.
          text: >
            az iot ops dataflow endpoint create local-mqtt
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --hostname aio-broker
            --port 1883
            --no-auth
        - name: Show config for creating a dataflow endpoint resource.
          text: >
            az iot ops dataflow endpoint create local-mqtt
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --hostname aio-broker
            --port 1883
            --client-id-prefix myclientprefix
            --keep-alive 100
            --max-inflight-msg 70
            --protocol WebSockets
            --qos 0
            --retain Never
            --show-config
    """

    helps[
        "iot ops dataflow endpoint create local-storage"
    ] = """
        type: command
        short-summary: Create or replace a local storage dataflow endpoint.
        long-summary: For more information on local storage dataflow endpoint, see https://aka.ms/local-storage-endpoint.

        examples:
        - name: Create or replace a dataflow endpoint resource with minimum input.
          text: >
            az iot ops dataflow endpoint create local-storage
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --pvc-ref mypvc
        - name: Show config for creating a dataflow endpoint resource.
          text: >
            az iot ops dataflow endpoint create local-storage
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --pvc-ref mypvc
            --show-config
    """

    helps[
        "iot ops dataflow endpoint create otel"
    ] = """
        type: command
        short-summary: Create or replace an OpenTelemetry dataflow endpoint.
        long-summary: For more information on OpenTelemetry dataflow endpoint, see https://aka.ms/opentelemetry-endpoint.

        examples:
        - name: Create or replace a dataflow endpoint resource with minimum input.
          text: >
            az iot ops dataflow endpoint create otel
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --name myendpoint
            --hostname https://otel-collector.monitoring.svc.cluster.local
            --port 4317
            --no-auth
        - name: Show config for creating a dataflow endpoint resource.
          text: >
            az iot ops dataflow endpoint create otel
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --hostname https://otel-collector.monitoring.svc.cluster.local
            --port 4317
            --no-auth
            --show-config
        - name: Create or replace a dataflow endpoint resource using X509 authentication method.
          text: >
            az iot ops dataflow endpoint create otel
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --hostname https://otel-collector.monitoring.svc.cluster.local
            --port 4317
            --secret-name mysecret
    """

    helps[
        "iot ops dataflow endpoint update"
    ] = """
        type: group
        short-summary: Update the properties of an existing dataflow endpoint resource.
    """

    helps[
        "iot ops dataflow endpoint update adls"
    ] = """
        type: command
        short-summary: Update the properties of an existing dataflow endpoint resource for Azure Data Lake Storage Gen2.
        long-summary: For more information on Azure Data Lake Storage Gen2 dataflow endpoint, see https://aka.ms/adlsv2.

        examples:
        - name: Update the storage account name of the dataflow endpoint resource called 'myendpoint'.
          text: >
            az iot ops dataflow endpoint update adls
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --storage-account newstorageaccount
        - name: Update to use user assigned managed identity authentication method of the dataflow endpoint resource called 'myendpoint'.
          text: >
            az iot ops dataflow endpoint update adls
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --client-id 425cb1e9-1247-4cbc-8cdb-1aac9b429696
            --tenant-id bca45660-49a2-4bad-862a-0b9459b4b836
            --scope "https://storage.azure.com/.default"
    """

    helps[
        "iot ops dataflow endpoint update adx"
    ] = """
        type: command
        short-summary: Update the properties of an existing dataflow endpoint resource for Azure Data Explorer.
        long-summary: For more information on Azure Data Explorer dataflow endpoint, see https://aka.ms/aio-adx.

        examples:
        - name: Update the batching configurations of the dataflow endpoint resource called 'myendpoint'.
          text: >
            az iot ops dataflow endpoint update adx
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --latency 70
            --message-count 100
        - name: Update to use system assigned managed identity authentication method of the dataflow endpoint resource called 'myendpoint'.
          text: >
            az iot ops dataflow endpoint update adx
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --auth-type SystemAssignedManagedIdentity
    """

    helps[
        "iot ops dataflow endpoint update custom-kafka"
    ] = """
        type: command
        short-summary: Update the properties of an existing dataflow endpoint resource for custom kafka broker.
        long-summary: For more information on custom kafka dataflow endpoint, see https://aka.ms/aio-custom-kafka.

        examples:
        - name: Update the hostname of the dataflow endpoint resource called 'myendpoint'.
          text: >
            az iot ops dataflow endpoint update custom-kafka
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --hostname newkafkabroker
        - name: Update to use SASL authentication method of the dataflow endpoint resource called 'myendpoint'.
          text: >
            az iot ops dataflow endpoint update custom-kafka
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --sasl-type ScramSha256
            --secret-name mysecret
    """

    helps[
        "iot ops dataflow endpoint update custom-mqtt"
    ] = """
        type: command
        short-summary: Update the properties of an existing dataflow endpoint resource for custom MQTT broker.
        long-summary: For more information on custom MQTT dataflow endpoint, see https://aka.ms/aio-custom-mqtt.

        examples:
        - name: Update the cloud event setting type of the dataflow endpoint resource called 'myendpoint'.
          text: >
            az iot ops dataflow endpoint update custom-mqtt
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --cloud-event-attribute CreateOrRemap
        - name: Update to use X509 authentication method of the dataflow endpoint resource called 'myendpoint'.
          text: >
            az iot ops dataflow endpoint update custom-mqtt
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --auth-type X509Certificate
            --secret-name mysecret
    """

    helps[
        "iot ops dataflow endpoint update eventgrid"
    ] = """
        type: command
        short-summary: Update the properties of an existing dataflow endpoint resource for Azure Event Grid.
        long-summary: For more information on Azure Event Grid dataflow endpoint, see https://aka.ms/aio-eventgrid.

        examples:
        - name: Update the session expiry interval of the dataflow endpoint resource called 'myendpoint'.
          text: >
            az iot ops dataflow endpoint update eventgrid
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --session-expiry 100
        - name: Update to use X509 authentication method of the dataflow endpoint resource called 'myendpoint'.
          text: >
            az iot ops dataflow endpoint update eventgrid
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --secret-name mysecret
    """

    helps[
        "iot ops dataflow endpoint update eventhub"
    ] = """
        type: command
        short-summary: Update the properties of an existing dataflow endpoint resource for kafka-enabled Azure Event Hubs namespace.
        long-summary: For more information on Azure Event Hubs dataflow endpoint, see https://aka.ms/aio-eventhub.

        examples:
        - name: Update the compression type of the dataflow endpoint resource called 'myendpoint'.
          text: >
            az iot ops dataflow endpoint update eventhub
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --compression Gzip
        - name: Update to use SASL authentication method of the dataflow endpoint resource called 'myendpoint'.
          text: >
            az iot ops dataflow endpoint update eventhub
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --sasl-type ScramSha256
            --secret-name mysecret
    """

    helps[
        "iot ops dataflow endpoint update fabric-onelake"
    ] = """
        type: command
        short-summary: Update the properties of an existing dataflow endpoint resource for Microsoft Fabric OneLake.
        long-summary: For more information on Microsoft Fabric OneLake dataflow endpoint, see https://aka.ms/fabric-onelake.

        examples:
        - name: Update the lakehouse name of the dataflow endpoint resource called 'myendpoint'.
          text: >
            az iot ops dataflow endpoint update fabric-onelake
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --lakehouse newlakehouse
        - name: Update to use system assigned managed identity authentication method of the dataflow endpoint resource called 'myendpoint'.
          text: >
            az iot ops dataflow endpoint update fabric-onelake
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --audience newaudience
    """

    helps[
        "iot ops dataflow endpoint update fabric-realtime"
    ] = """
        type: command
        short-summary: Update the properties of an existing Microsoft Fabric Real-Time Intelligence data flow endpoint.
        long-summary: For more information on Microsoft Fabric Real-Time Intelligence dataflow endpoint, see https://aka.ms/aio-fabric-real-time.

        examples:
        - name: Update the partition strategy of the dataflow endpoint resource called 'myendpoint'.
          text: >
            az iot ops dataflow endpoint update fabric-realtime
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --partition-strategy Static
        - name: Update to use SASL authentication method of the dataflow endpoint resource called 'myendpoint'.
          text: >
            az iot ops dataflow endpoint update fabric-realtime
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --sasl-type ScramSha256
            --secret-name mysecret
    """

    helps[
        "iot ops dataflow endpoint update local-mqtt"
    ] = """
        type: command
        short-summary: Update the properties of an existing Azure IoT Operations Local MQTT data flow endpoint.
        long-summary: For more information on Azure IoT Operations Local MQTT dataflow endpoint, see https://aka.ms/local-mqtt-broker.

        examples:
        - name: Update the config map reference for trusted CA certificate of the dataflow endpoint resource called 'myendpoint'.
          text: >
            az iot ops dataflow endpoint update local-mqtt
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --config-map-ref mynewconfigmap
        - name: Update to use Kubernetes Service Account Token authentication method of the dataflow endpoint resource called 'myendpoint'.
          text: >
            az iot ops dataflow endpoint update local-mqtt
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --auth-type ServiceAccountToken
            --audience myaudience
    """

    helps[
        "iot ops dataflow endpoint update local-storage"
    ] = """
        type: command
        short-summary: Update the properties of an existing local storage data flow endpoint.
        long-summary: For more information on local storage dataflow endpoint, see https://aka.ms/local-storage-endpoint.

        examples:
        - name: Update the PVC reference of the dataflow endpoint resource called 'myendpoint'.
          text: >
            az iot ops dataflow endpoint update local-storage
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --pvc-ref newpvc
    """

    helps[
        "iot ops dataflow endpoint update otel"
    ] = """
        type: command
        short-summary: Update the properties of an existing OpenTelemetry dataflow endpoint.
        long-summary: For more information on OpenTelemetry dataflow endpoint, see https://aka.ms/opentelemetry-endpoint.

        examples:
        - name: Update the config map reference for trusted CA certificate of the dataflow endpoint resource called 'myendpoint'.
          text: >
            az iot ops dataflow endpoint update otel
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --config-map-ref mynewconfigmap
        - name: Update to use Kubernetes Service Account Token authentication method of the dataflow endpoint resource called 'myendpoint'.
          text: >
            az iot ops dataflow endpoint update otel
            --name myendpoint
            --instance mycluster-ops-instance
            --resource-group myresourcegroup
            --auth-type ServiceAccountToken
            --audience myaudience
    """

    helps[
        "iot ops dataflow endpoint apply"
    ] = """
        type: command
        short-summary: Create or replace a dataflow endpoint resource.
        long-summary: |
          An example of the config file format is as follows:

          ```
          {
            "endpointType": "Kafka",
            "kafkaSettings": {
              "authentication": {
                "method": "SystemAssignedManagedIdentity",
                "systemAssignedManagedIdentitySettings": {
                  "audience": "aio-internal"
                }
              },
              "batching": {
                "latencyMs": 5,
                "maxBytes": 1000000,
                "maxMessages": 100000,
                "mode": "Enabled"
              },
              "cloudEventAttributes": "Propagate",
              "compression": "None",
              "copyMqttProperties": "Disabled",
              "host": "test.servicebus.windows.net:9093",
              "kafkaAcks": "All",
              "partitionStrategy": "Default",
              "tls": {
                "mode": "Enabled"
              }
            },
          }
          ```

          When used with apply the above content will create or replace a target kafka dataflow endpoint
          resource configured with system assigned managed identity authentication method.

        examples:
        - name: Create or replace an dataflow endpoint resource using a config file.
          text: >
            az iot ops dataflow endpoint apply -n dataflowep --in myinstance -g myresourcegroup --config-file /path/to/dataflowep/config.json
    """

    helps[
        "iot ops dataflow endpoint delete"
    ] = """
        type: command
        short-summary: Delete a dataflow endpoint resource.

        examples:
        - name: Delete the dataflow endpoint resource called 'dataflowep'.
          text: >
            az iot ops dataflow endpoint delete -n dataflowep --in myinstance -g myresourcegroup
        - name: Same as prior example but skipping the confirmation prompt.
          text: >
            az iot ops dataflow endpoint delete -n dataflowep --in myinstance -g myresourcegroup -y
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

                      Note: --*-config options allow override of default config settings.

                      The default config settings for secret store are:
                        rotationPollIntervalInSeconds=120
                        validatingAdmissionPolicies.applyPolicies=false

                      The default config settings for cert-manager are:
                        AgentOperationTimeoutInMinutes=20
                        global.telemetry.enabled=true
                        trust-manager.secretTargets.enabled=false
                        trust-manager.secretTargets.authorizedSecretsAll=false

        examples:
        - name: Usage with minimum input. This form will deploy the IoT Operations foundation layer.
          text: >
             az iot ops init --cluster mycluster -g myresourcegroup
        - name: The following example highlights enabling user trust settings for a custom cert-manager config.
            This will skip deployment of the system cert-manager and trust-manager.
          text: >
             az iot ops init --cluster mycluster -g myresourcegroup --user-trust
        - name: Provide custom deploy-time configs for Arc Secret Store.
          text: >
             az iot ops init --cluster mycluster -g myresourcegroup --ssc-config rotationPollIntervalInSeconds=60
        - name: Check if the cluster meets necessary prerequisite configuration before continuing with init. A valid kubeconfig is required with this option.
          text: >
             az iot ops init --cluster mycluster -g myresourcegroup --check-cluster
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

          To enable broker disk persistence at least a value for --persist-max-size
          must be provided. When enabled the default configuration is constrained to
          dynamic persistence across state store, retain messages and subscriber
          queues.

          To enable edge to cloud resource hydration please use the
          `az iot ops enable-rsync` command post instance creation.

        examples:
        - name: Create the target instance with minimum input.
          text: >
            az iot ops create --cluster mycluster -g myresourcegroup --name myinstance --sr-resource-id $SCHEMA_REGISTRY_RESOURCE_ID
            --ns-resource-id $NAMESPACE_RESOURCE_ID
        - name: The following example adds customization to the default broker instance resource
            as well as an instance description and tags.
          text: >
             az iot ops create --cluster mycluster -g myresourcegroup --name myinstance --sr-resource-id $SCHEMA_REGISTRY_RESOURCE_ID
             --ns-resource-id $NAMESPACE_RESOURCE_ID --broker-mem-profile High --broker-backend-workers 4 --description 'Contoso Factory'
             --tags tier=testX1
        - name: This example shows deploying an additional insecure (no authn or authz) broker listener
            configured for port 1883 of service type load balancer. Useful for testing and/or demos.
            Do not use the insecure option in production.
          text: >
             az iot ops create --cluster mycluster -g myresourcegroup --name myinstance --sr-resource-id $SCHEMA_REGISTRY_RESOURCE_ID
             --ns-resource-id $NAMESPACE_RESOURCE_ID --add-insecure-listener
        - name: This example highlights trust settings for a user provided cert-manager config.
            Note that the cluster must have been initialized with `--user-trust` and a user cert-manager deployment must be present.
          text: >
              az iot ops create --cluster mycluster -g myresourcegroup --name myinstance --sr-resource-id $SCHEMA_REGISTRY_RESOURCE_ID
              --ns-resource-id $NAMESPACE_RESOURCE_ID --trust-settings configMapName=example-bundle configMapKey=trust-bundle.pem
              issuerKind=ClusterIssuer issuerName=trust-manager-selfsigned-issuer
        - name: Deploy the mqtt broker with the min options to enable disk persistence.
          text: >
             az iot ops create --cluster mycluster -g myresourcegroup --name myinstance --sr-resource-id $SCHEMA_REGISTRY_RESOURCE_ID
             --ns-resource-id $NAMESPACE_RESOURCE_ID --persist-max-size 10Gi
        - name: Deploy the mqtt broker with disk persistence, configuring volume claim storage class and persistence mode.
          text: >
             az iot ops create --cluster mycluster -g myresourcegroup --name myinstance --sr-resource-id $SCHEMA_REGISTRY_RESOURCE_ID
             --ns-resource-id $NAMESPACE_RESOURCE_ID --persist-max-size 10Gi --persist-pvc-sc mystorageclass
             --persist-mode retain=All stateStore=None
    """

    helps[
        "iot ops delete"
    ] = """
        type: command
        short-summary: Delete IoT Operations from the cluster.
        long-summary: |
            Either --name (instance) or --cluster must be provided.

            By default the command deletes the IoT Operations instance
            (cascading to all child resources), the custom location,
            resource sync rules, and the IoT Operations arc extension.

            Use --include-deps to also remove dependency extensions
            such as cert manager, secret store, and container
            storage (when deployed by init).

            Use --cluster when the instance has already been deleted
            and residual resources need cleanup.

        examples:
        - name: Delete an IoT Operations instance by name.
          text: >
            az iot ops delete -n myinstance -g myresourcegroup
        - name: Skip the confirmation prompt. Useful for CI.
          text: >
            az iot ops delete -n myinstance -g myresourcegroup -y
        - name: Force deletion when the cluster is disconnected.
          text: >
            az iot ops delete -n myinstance -g myresourcegroup --force
        - name: Discover resources via cluster name instead of instance name.
          text: >
            az iot ops delete --cluster mycluster -g myresourcegroup
        - name: Delete instance and dependency extensions.
          text: >
            az iot ops delete -n myinstance -g myresourcegroup --include-deps
        - name: Full cleanup via cluster name with dependency removal. Recommended for CI teardown.
          text: >
            az iot ops delete --cluster mycluster -g myresourcegroup --include-deps --force -y
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
        long-summary: Currently instance tags, description and features can be updated.

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
        short-summary: Upgrade an IoT Operations instance.
        long-summary: |
                      By default, with no options, the command will evaluate versions of the
                      deployed cluster side services that make up IoT Operations and compare them
                      with the built-in deployment that would be executed with `az iot ops init`
                      and `az iot ops create`.
        examples:
        - name: Upgrade the instance with minimal inputs.
          text: >
            az iot ops upgrade --name myinstance -g myresourcegroup
        - name: Skip the confirmation prompt for instance upgrade. Useful for CI scenarios.
          text: >
            az iot ops upgrade --name myinstance -g myresourcegroup -y
        - name: Set extension config settings that apply should be during upgrade.
           To remove a setting provide the key with no value.
          text: >
            az iot ops upgrade --name myinstance -g myresourcegroup --ops-config key1=value1 deletekey
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
            This operation includes federation of the identity for the applicable purpose.

            When --usage 'schema' is present, by default, a role assignment of the identity against the
            instance schema registry will be made if the expected role does not already exist.

        examples:
        - name: Assign and federate a desired user-assigned managed identity for use with dataflows.
          text: >
            az iot ops identity assign --name myinstance -g myresourcegroup --mi-user-assigned $UA_MI_RESOURCE_ID
        - name: Assign and federate a desired user-assigned managed identity for use with schema registry.
          text: >
            az iot ops identity assign --name myinstance -g myresourcegroup --mi-user-assigned $UA_MI_RESOURCE_ID --usage schema
        - name: Assign and federate a desired user-assigned managed identity for use with schema registry with a
            custom role to be used for the identity role assignment.
          text: >
            az iot ops identity assign --name myinstance -g myresourcegroup --mi-user-assigned $UA_MI_RESOURCE_ID --usage schema
            --custom-sr-role-id $CUSTOM_ROLE_ID
        - name: Assign and federate a desired user-assigned managed identity for use with schema registry but
            skip the role assignment step of the operation.
          text: >
            az iot ops identity assign --name myinstance -g myresourcegroup --mi-user-assigned $UA_MI_RESOURCE_ID --usage schema
            --skip-sr-ra
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
            The operation handles identity federation, creation of a default secret provider class
            and role assignments (Key Vault Reader, Key Vault Secrets User) of the managed identity
            against the target Key Vault.

            The flow starts with ensuring Key Vault role assignments, applying them if they don't exist.
            An error will be raised if the role assignments cannot be made. If necessary a custom role
            via --custom-role-id can be used in-place of the built-in roles. Or the --skip-ra flag can
            be used to skip role assignments.

        examples:
        - name: Enable the target instance for Key Vault secret sync.
          text: >
            az iot ops secretsync enable --instance myinstance -g myresourcegroup
            --mi-user-assigned $UA_MI_RESOURCE_ID --kv-resource-id $KEYVAULT_RESOURCE_ID
        - name: Enable secret sync and apply tags when creating the default secret provider class.
          text: >
            az iot ops secretsync enable --instance myinstance -g myresourcegroup
            --mi-user-assigned $UA_MI_RESOURCE_ID --kv-resource-id $KEYVAULT_RESOURCE_ID --tags a=b c=d
        - name: Enable secret sync with custom role Id against the Key Vault.
          text: >
            az iot ops secretsync enable --instance myinstance -g myresourcegroup
            --mi-user-assigned $UA_MI_RESOURCE_ID --kv-resource-id $KEYVAULT_RESOURCE_ID
            --custom-role-id $CUSTOM_ROLE_ID
        - name: Usage of flag to skip Key Vault role assignments.
          text: >
            az iot ops secretsync enable --instance myinstance -g myresourcegroup
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
            az iot ops secretsync list --instance myinstance -g myresourcegroup
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
            az iot ops secretsync disable --instance myinstance -g myresourcegroup
    """

    helps[
        "iot ops secretsync secret"
    ] = """
        type: group
        short-summary: Manage individual secrets within SecretSync resources.
    """

    helps[
        "iot ops secretsync secret set"
    ] = """
        type: command
        short-summary: Set AKV secret mappings on a SecretSync resource.
        long-summary: |
            Resolves the instance's default secret provider class (SPC), verifies each AKV secret exists, adds each secret to the SPC's objects list, and creates or merges entries into the named SecretSync resource.

            If the SecretSync already exists, new secret entries are merged into it. Existing entries with the same AKV secret name will have their target key updated.

            The --secret-sync-name value becomes the K8s secret name. Consumers reference it via `<secret-sync-name>/<target-key>` for device endpoints, or just `<secret-sync-name>` for dataflow endpoints.

        examples:
        - name: Create a SecretSync for device endpoint x509 cert auth.
          text: >
            az iot ops secretsync secret set --instance myInstance -g myRG
            --secret-sync-name my-certs
            --secret-map my-tls-cert=certificate --secret-map my-tls-key=privateKey
        - name: Add another secret to an existing SecretSync (idempotent merge).
          text: >
            az iot ops secretsync secret set --instance myInstance -g myRG
            --secret-sync-name my-certs
            --secret-map my-intermediate-cert=intermediateCerts
        - name: Create a SecretSync for SASL-based dataflow endpoint.
          text: >
            az iot ops secretsync secret set --instance myInstance -g myRG
            --secret-sync-name eventhub-sasl
            --secret-map my-eh-user=username --secret-map my-eh-pass=password
    """

    helps[
        "iot ops secretsync secret list"
    ] = """
        type: command
        short-summary: List secrets within a SecretSync resource.

        examples:
        - name: List secrets in a specific SecretSync resource.
          text: >
            az iot ops secretsync secret list --instance myInstance -g myRG
            --secret-sync-name my-certs
    """

    helps[
        "iot ops secretsync secret remove"
    ] = """
        type: command
        short-summary: Remove a specific secret from a SecretSync resource. If all secrets are removed, the SecretSync resource itself is automatically deleted.
        long-summary: |
            Removes the secret entry from the SecretSync's objectSecretMapping. If this is the last secret in the SecretSync, the entire SecretSync resource will be deleted since the ARM API does not allow a SecretSync with zero secret mappings.

            Before removing the secret from the shared SPC, a ref-count check is performed across all SecretSyncs in the custom location. The SPC entry is only removed if no other SecretSync still references the same AKV secret. This prevents breaking other consumers of the shared SPC.

            This command does NOT delete the secret from Azure Key Vault.

        examples:
        - name: Remove a secret from a SecretSync.
          text: >
            az iot ops secretsync secret remove --instance myInstance -g myRG
            --secret-sync-name my-certs --secret-name my-tls-cert
        - name: Remove a secret without confirmation prompt.
          text: >
            az iot ops secretsync secret remove --instance myInstance -g myRG
            --secret-sync-name my-certs --secret-name my-tls-cert -y
    """

    helps[
        "iot ops mgmt-actions"
    ] = """
        type: group
        short-summary: Instance management actions configuration.
    """

    helps[
        "iot ops mgmt-actions enable"
    ] = """
        type: command
        short-summary: Enable management actions for an IoT Operations instance.
        long-summary: |
            Bootstraps the infrastructure enabling cloud-based invocation of management
            actions on assets through Event Grid MQTT broker integration.

            The operation configures resources across three domains:
            - Event Grid Namespace: topic space, topic templates, and permission bindings.
            - Device Registry Namespace: managed identity enablement and management endpoint config.
            - IoT Operations Instance: EG dataflow endpoint, dataflow graph, and response dataflow.

            The command is idempotent. If a resource already exists, it is skipped. On partial failure,
            re-run the command to reach the desired state.

            By default, role assignments (Event Grid TopicSpaces Publisher and Subscriber) are created
            for both the ADR namespace MI and the AIO extension MI against the EG namespace.
            Use --skip-ra to skip role assignment creation, or --adr-role-ids / --ops-role-ids to
            provide custom role Ids.

        examples:
        - name: Enable management actions for an instance using system managed identity.
          text: >
            az iot ops mgmt-actions enable --instance myinstance -g myresourcegroup
            --eg-resource-id $EG_NAMESPACE_RESOURCE_ID
        - name: Enable management actions using a user-assigned managed identity for the EG dataflow endpoint.
          text: >
            az iot ops mgmt-actions enable --instance myinstance -g myresourcegroup
            --eg-resource-id $EG_NAMESPACE_RESOURCE_ID --mi-user-assigned $UA_MI_RESOURCE_ID
        - name: Enable management actions and skip role assignments.
          text: >
            az iot ops mgmt-actions enable --instance myinstance -g myresourcegroup
            --eg-resource-id $EG_NAMESPACE_RESOURCE_ID --skip-ra
    """

    helps[
        "iot ops mgmt-actions disable"
    ] = """
        type: command
        short-summary: Disable management actions for an IoT Operations instance.
        long-summary: |
            Removes management actions resources associated with the instance including
            the dataflow graph, response dataflow, EG dataflow endpoint, EG topic space,
            permission bindings, and the ADR namespace management endpoint entry.

            Role assignments are not removed as they may be shared with other resources.

            The Event Grid namespace is discovered from the ADR namespace management
            endpoint config. If the management endpoint entry has already been removed,
            Event Grid cleanup is skipped gracefully.

        examples:
        - name: Disable management actions for an instance.
          text: >
            az iot ops mgmt-actions disable --instance myinstance -g myresourcegroup
        - name: Disable management actions without confirmation prompt.
          text: >
            az iot ops mgmt-actions disable --instance myinstance -g myresourcegroup --yes
    """

    helps[
        "iot ops mgmt-actions show"
    ] = """
        type: command
        short-summary: Show management actions configuration for an IoT Operations instance.
        long-summary: |
            Checks the status of management actions resources across three areas:
            Device Registry (ADR) namespace, Event Grid resources, and AIO dataflow resources.

            Returns a structured summary with an overall enabled flag and per-domain detail
            sections. A domain that cannot be probed (e.g. missing ADR namespace ref) returns
            null for that section without blocking other domains from being checked.

        examples:
        - name: Show management actions configuration for an instance.
          text: >
            az iot ops mgmt-actions show --instance myinstance -g myresourcegroup
    """

    helps[
        "iot ops mgmt-actions execute"
    ] = """
        type: command
        short-summary: Execute a management action on a namespace asset.
        long-summary: |
            Invokes a management action defined on a namespace asset via the Device Registry
            executeAction operation. The management actions infrastructure must be enabled
            (`az iot ops mgmt-actions enable`) before actions can be executed.

            The command resolves the ADR namespace from the IoT Operations instance and
            submits the action as a long-running operation. The result includes the action
            status, any response from the asset, and error details if the action failed.

            When a payload is provided, the CLI validates it against the action's request
            schema (if available) before sending the request. Use --no-validate to skip
            this check. Use --show-schema to view the action's request schema without
            executing.

        examples:
        - name: Execute a management action with no payload.
          text: >
            az iot ops mgmt-actions execute
            --instance myinstance
            -g myresourcegroup
            --asset myasset
            --group mygroup
            --action reboot
        - name: Execute a management action with inline JSON payload.
          text: >
            az iot ops mgmt-actions execute
            --instance myinstance
            -g myresourcegroup
            --asset myasset
            --group mygroup
            --action configure
            -p '{"temperature": {"setpoint": 72}}'
        - name: Execute a management action with payload from file.
          text: >
            az iot ops mgmt-actions execute
            --instance myinstance
            -g myresourcegroup
            --asset myasset
            --group mygroup
            --action configure
            -p payload.json
        - name: Show the request schema for a management action.
          text: >
            az iot ops mgmt-actions execute
            --instance myinstance
            -g myresourcegroup
            --asset myasset
            --group mygroup
            --action configure
            --show-schema
        - name: Execute with payload, skipping schema validation.
          text: >
            az iot ops mgmt-actions execute
            --instance myinstance
            -g myresourcegroup
            --asset myasset
            --group mygroup
            --action configure
            -p '{"temperature": {"setpoint": 72}}'
            --no-validate
    """

    helps[
        "iot ops live-data"
    ] = """
        type: group
        short-summary: Live Data infrastructure configuration for an IoT Operations instance.
    """

    helps[
        "iot ops live-data enable"
    ] = """
        type: command
        short-summary: Enable Live Data for an IoT Operations instance.
        long-summary: |
            Provisions and configures the shared, instance-level infrastructure required for
            Live Data across three domains:
            - Event Grid Namespace: an observability topic space.
            - IoT Operations Instance: a dedicated dataflow profile and an EG MQTT dataflow endpoint.
            - Device Registry Namespace: the outbound identity and the per-instance observability
              endpoint entry (keyed by the instance's custom location).

            The command is idempotent. Re-running converges to the desired state without
            overwriting unrelated entries. Enablement for an instance is expressed by the presence
            of its observability endpoint entry.

            By default, role assignments (Event Grid TopicSpaces Publisher for the instance identity
            and Subscriber for the ADR namespace identity) are created at the Event Grid namespace
            scope. Use --ra-scope topic-space for least-privilege assignments scoped to the topic
            space, or --skip-ra to skip role assignment creation.

        examples:
        - name: Enable Live Data using a system-assigned managed identity and default roles.
          text: >
            az iot ops live-data enable --instance myinstance -g myresourcegroup
            --eg-resource-id $EG_NAMESPACE_RESOURCE_ID
        - name: Enable Live Data using a user-assigned managed identity for outbound auth.
          text: >
            az iot ops live-data enable --instance myinstance -g myresourcegroup
            --eg-resource-id $EG_NAMESPACE_RESOURCE_ID --mi-user-assigned $UA_MI_RESOURCE_ID
        - name: Enable Live Data with least-privilege, topic-space-scoped role assignments.
          text: >
            az iot ops live-data enable --instance myinstance -g myresourcegroup
            --eg-resource-id $EG_NAMESPACE_RESOURCE_ID --ra-scope topic-space
        - name: Enable Live Data and skip role assignments.
          text: >
            az iot ops live-data enable --instance myinstance -g myresourcegroup
            --eg-resource-id $EG_NAMESPACE_RESOURCE_ID --skip-ra
    """

    helps[
        "iot ops live-data disable"
    ] = """
        type: command
        short-summary: Disable Live Data for an IoT Operations instance.
        long-summary: |
            Tears down the dedicated dataflow profile, the EG dataflow endpoint, and the
            observability topic space, then removes this instance's observability endpoint
            entry from the Device Registry namespace last so an interrupted disable can be
            safely re-run.

            Namespace-scoped role assignments are preserved; topic-space-scoped role
            assignments are removed together with the topic space.

        examples:
        - name: Disable Live Data for an instance.
          text: >
            az iot ops live-data disable --instance myinstance -g myresourcegroup
        - name: Disable Live Data without a confirmation prompt.
          text: >
            az iot ops live-data disable --instance myinstance -g myresourcegroup --yes
    """

    helps[
        "iot ops live-data show"
    ] = """
        type: command
        short-summary: Show Live Data configuration for an IoT Operations instance.
        long-summary: |
            Reports the Live Data configuration and resource status across the Device Registry
            namespace, Event Grid, and IoT Operations dataflow resources. The top-level enabled
            flag is true only when this instance's observability endpoint entry and all supporting
            resources are present.

        examples:
        - name: Show Live Data configuration for an instance.
          text: >
            az iot ops live-data show --instance myinstance -g myresourcegroup
    """

    helps[
        "iot ops schema"
    ] = """
        type: group
        short-summary: Schema registry and schema management.
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
        - name: Create a schema called 'myschema' with additional customization. Schema version 14 will be created for this schema. The inline content is a bash syntax example. For more examples, see https://aka.ms/inline-json-examples
          text: >
            az iot ops schema create -n myschema -g myresourcegroup --registry myregistry
            --format delta --type message --desc "Schema for Assets" --display-name myassetschema
            --version-content '{"hello": "world"}' --ver 14 --vd "14th version"
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
        "iot ops connector template"
    ] = """
        type: group
        short-summary: Connector template management.
        long-summary: |
          Connector templates provide a standardized, metadata-driven approach to connector deployment.
          Templates are created from connector metadata references (MCR for 1st-party connectors,
          ACR for 3rd-party connectors), automatically populating connector-specific configuration
          while allowing user customization of deployment parameters.
    """

    helps[
        "iot ops connector template create"
    ] = """
        type: command
        short-summary: Create a new connector template.
        long-summary: |
          Creates a connector template from metadata stored in a container registry. The metadata
          automatically populates connector-specific settings, while deployment parameters like
          replicas, log levels, and secrets can be customized.
        examples:
        - name: Create a template for REST connector with default settings.
          text: >
            az iot ops connector template create --name my-rest-template
            --resource-group myResourceGroup --instance myAIOInstance
            --connector-metadata-ref mcr.microsoft.com/azureiotoperations/akri-connectors/rest-metadata:1.0.6
        - name: Create a template with custom configuration.
          text: >
            az iot ops connector template create --name my-rest-template
            --resource-group myResourceGroup --instance myAIOInstance
            --connector-metadata-ref mcr.microsoft.com/azureiotoperations/akri-connectors/rest-metadata:1.0.6
            --replicas 3 --log-level debug --image-pull-secrets acr-credentials
        - name: Create a template for 3rd-party connector from private ACR.
          text: >
            az iot ops connector template create --name custom-plc-template
            --resource-group myResourceGroup --instance myAIOInstance
            --connector-metadata-ref contoso.azurecr.io/connectors/plc-metadata:1.0.0
            --image-pull-secrets acr-pull-secret
    """

    helps[
        "iot ops connector template update"
    ] = """
        type: command
        short-summary: Update an existing connector template.
        long-summary: |
          Updates a connector template. Deployment parameters such as replicas, log levels, secrets,
          image pull settings, and trust settings can be modified. Connector metadata can be updated
          to patch or minor version upgrades only. Major version updates require creating a new template.
        examples:
        - name: Update replica count and log level.
          text: >
            az iot ops connector template update --name my-rest-template
            --resource-group myResourceGroup --instance myAIOInstance
            --replicas 5 --log-level debug
        - name: Update to a newer patch version of the connector.
          text: >
            az iot ops connector template update --name my-rest-template
            --resource-group myResourceGroup --instance myAIOInstance
            --connector-metadata-ref mcr.microsoft.com/azureiotoperations/akri-connectors/rest-metadata:1.0.7
    """

    helps[
        "iot ops connector template show"
    ] = """
        type: command
        short-summary: Display a connector template.
        long-summary: |
          Shows the complete template configuration including metadata, connector information,
          image configuration, deployment settings, storage configuration, and security settings.
        examples:
        - name: Show template details in JSON format.
          text: >
            az iot ops connector template show --name my-rest-template
            --resource-group myResourceGroup --instance myAIOInstance
        - name: Show template in table format.
          text: >
            az iot ops connector template show --name my-rest-template
            --resource-group myResourceGroup --instance myAIOInstance --output table
    """

    helps[
        "iot ops connector template delete"
    ] = """
        type: command
        short-summary: Delete a connector template.
        long-summary: |
          Deletes a connector template. Validates if template is currently in use by deployed
          connectors and prompts for confirmation unless --yes is provided.
        examples:
        - name: Delete template with confirmation prompt.
          text: >
            az iot ops connector template delete --name my-rest-template
            --resource-group myResourceGroup --instance myAIOInstance
        - name: Delete template without confirmation.
          text: >
            az iot ops connector template delete --name my-rest-template
            --resource-group myResourceGroup --instance myAIOInstance --yes
    """

    helps[
        "iot ops connector template list"
    ] = """
        type: command
        short-summary: List all connector templates.
        long-summary: |
          Lists all connector templates for a specific Azure IoT Operations instance with
          summary information including template name, connector type, version, replicas,
          and creation/modification dates.
        examples:
        - name: List all templates for an instance.
          text: >
            az iot ops connector template list --resource-group myResourceGroup
            --instance myAIOInstance
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
            'opc-ua-connector' and secretsync 'aio-opc-ua-broker-trust-list' will be created if not found.
        examples:
        - name: Add a trusted certificate to the OPC UA Broker's trusted certificate list.
          text: >
            az iot ops connector opcua trust add --instance instance --resource-group instanceresourcegroup
            --certificate-file "certificate.der"
        - name: Add a trusted certificate to the OPC UA Broker's trusted certificate list with custom secret name.
          text: >
            az iot ops connector opcua trust add --instance instance --resource-group instanceresourcegroup
            --certificate-file "certificate.crt" --secret-name custom-secret-name
        - name: Add a trusted certificate to the trusted certificate list and skip the overwrite confirmation prompt when the secret already exists.
          text: >
            az iot ops connector opcua trust add --instance instance --resource-group instanceresourcegroup
            --certificate-file "certificate.der" --overwrite-secret
        - name: Add a trusted certificate with a custom expiration date for the Key Vault secret.
          text: >
            az iot ops connector opcua trust add --instance instance --resource-group instanceresourcegroup
            --certificate-file "certificate.der" --expiration-date "2026-12-31T23:59:59Z"
    """

    helps[
        "iot ops connector opcua trust remove"
    ] = """
        type: command
        short-summary: Remove trusted certificate(s) from the OPC UA Broker's trusted certificate list.
        long-summary: |
            Note: Removing all trusted certificates from the OPC UA Broker's trusted certificate list
            will trigger deletion of the secretsync resource 'aio-opc-ua-broker-trust-list'.
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
          - name: Remove trusted certificates from trusted certificate list and skip confirmation prompt for removal.
            text: >
              az iot ops connector opcua trust remove --instance instance --resource-group instanceresourcegroup
              --certificate-names testcert1.der testcert2.crt --yes
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
            --certificate-file "certificate.der" --secret-name custom-secret-name
        - name: Add an issuer certificate to the issuer certificate list and skip the overwrite confirmation prompt when the secret already exists.
          text: >
            az iot ops connector opcua issuer add --instance instance --resource-group instanceresourcegroup
            --certificate-file "certificate.der" --overwrite-secret
    """

    helps[
        "iot ops connector opcua issuer remove"
    ] = """
        type: command
        short-summary: Remove trusted certificate(s) from the OPC UA Broker's issuer certificate list.
        long-summary: |
            Note: Removing all issuer certificates from the OPC UA Broker's issuer certificate list
            will trigger deletion of the secretsync resource 'aio-opc-ua-broker-issuer-list'.
            Please make sure to remove corresponding .crl if exist when removing .der/.crt certificate
            to avoid orphaned secret.
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
          - name: Remove issuer certificates from issuer certificate list and skip confirmation prompt for removal.
            text: >
              az iot ops connector opcua issuer remove --instance instance --resource-group instanceresourcegroup
              --certificate-names testcert.der --yes
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
            if not found. The newly added certificate will replace the existing
            certificate if there is any.
            Note: The subject name and application URI will be auto derived from the provided
            certificate. Optional parameters may be used to validate the respective values
            meet expectations before the operation proceeds.
        examples:
        - name: Add a client certificate.
          text: >
            az iot ops connector opcua client add --instance instance --resource-group instanceresourcegroup
            --public-key-file "newopc.der" --private-key-file "newopc.pem"
        - name: Add a client certificate and skip the overwrite confirmation prompt when the secret already exists.
          text: >
            az iot ops connector opcua client add --instance instance --resource-group instanceresourcegroup
            --public-key-file "newopc.der" --private-key-file "newopc.pem" --overwrite-secret
        - name: Add a client certificate with custom public and private key secret name.
          text: >
            az iot ops connector opcua client add
            --instance instance
            --resource-group instanceresourcegroup
            --public-key-file "newopc.der"
            --private-key-file "newopc.pem"
            --public-key-secret-name public-secret-name
            --private-key-secret-name private-secret-name
        - name: Add a client certificate with subject name and application URI specified. Values will be used to validate the existing certificate values.
          text: >
            az iot ops connector opcua client add
            --instance instance
            --resource-group instanceresourcegroup
            --public-key-file "newopc.der"
            --private-key-file "newopc.pem"
            --public-key-secret-name public-secret-name
            --private-key-secret-name private-secret-name
            --subject-name "aio-opc-opcuabroker"
            --application-uri "urn:microsoft.com:aio:opc:opcuabroker"
      """

    helps[
        "iot ops connector opcua client remove"
    ] = """
        type: command
        short-summary: Remove client application instance certificate from the OPC UA Broker.
        long-summary: |
            Note: Removing all certificates from the OPC UA Broker's client certificate store
            will trigger deletion of the secretsync resource 'aio-opc-ua-broker-client-certificate'.
            And this operation will trigger the fallback to default (cert-manager based) certificate.
            This fallback requires an aio extension update.
            Please make sure to remove both public(.der) and private(.pem) key certificate pair to
            avoid orphaned secret.
        examples:
          - name: Remove client certificates from the OPC UA Broker's client certificate store.
            text: >
              az iot ops connector opcua client remove --instance instance --resource-group instanceresourcegroup
              --certificate-names testcert.der testcert.pem
          - name: Remove client certificates from client certificate store, including remove related keyvault secret.
            text: >
              az iot ops connector opcua client remove --instance instance --resource-group instanceresourcegroup
              --certificate-names testcert.der testcert.pem --include-secrets
          - name: Force remove certificates operation regardless of warnings. May lead to errors.
            text: >
              az iot ops connector opcua client remove --instance instance --resource-group instanceresourcegroup
              --certificate-names testcert.der testcert.pem --force
          - name: Remove client certificates from client certificate store and skip confirmation prompt for removal.
            text: >
              az iot ops connector opcua client remove --instance instance --resource-group instanceresourcegroup
              --certificate-names testcert.der testcert.pem --yes

    """

    helps[
        "iot ops connector opcua client show"
    ] = """
        type: command
        short-summary: Show details of secretsync resource 'aio-opc-ua-broker-client-certificate'.
        examples:
        - name: Show details of 'aio-opc-ua-broker-client-certificate' secretsync resource.
          text: >
            az iot ops connector opcua client show --instance instance --resource-group instanceresourcegroup
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
            az iot ops schema version show --version 1 --schema myschema --registry myregistry -g myresourcegroup
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
            az iot ops schema version remove --version 1 -g myresourcegroup --registry myregistry --schema myschema
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
            az iot ops schema version add --version 1 -g myresourcegroup --registry myregistry --schema myschema --content '{\\\"hello\\\": \\\"world\\\"}'
        - name: Add a schema version 1 to a schema called 'myschema' within the registry 'myregistry' with
                minimum inputs. The content is inline json (cmd syntax example).
          text: >
            az iot ops schema version add --version 1 -g myresourcegroup --registry myregistry --schema myschema --content "{\\\"hello\\\": \\\"world\\\"}"
        - name: Add a schema version 1 to a schema called 'myschema' within the registry 'myregistry' with
                minimum inputs. The content is inline json (bash syntax example).
          text: >
            az iot ops schema version add --version 1 -g myresourcegroup --registry myregistry --schema myschema --content '{"hello": "world"}'
        - name: Add a schema version 2 to a schema called 'myschema' within the registry 'myregistry' with
                a description. The file should contain the schema content.
          text: >
            az iot ops schema version add --version 2 -g myresourcegroup --registry myregistry --schema myschema --content myschemav2.json --desc "New schema"
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

    helps[
        "iot ops clone"
    ] = f"""
        type: command
        short-summary: Clone an instance.
        long-summary: |
          Clone analyzes an instance then reproduces it in an infrastructure-as-code
          manner via ARM templates.

          The output of clone may be applied directly to another connected
          cluster (referred to as replication), and/or saved locally to use at another time
          with potential modification.

          The clone definition being a generic ARM template, can be deployed via existing tools.
          See https://aka.ms/aio-clone for details.

          Clone is compatible with the following instance version range: `{CLONE_INSTANCE_VERS_MIN}>=,<{CLONE_INSTANCE_VERS_MAX}`

        examples:
        - name: Clone an instance to a desired connected cluster.
          text: >
            az iot ops clone -n myinstance -g myresourcegroup --to-cluster-id $CLUSTER_RESOURCE_ID
        - name: Clone an instance to a desired connected cluster, with customized replication.
          text: >
            az iot ops clone -n myinstance -g myresourcegroup --to-cluster-id $CLUSTER_RESOURCE_ID --param location=eastus
        - name: Clone an instance to a desired connected cluster, but splitting and serially applying asset related sub-deployments.
          text: >
            az iot ops clone -n myinstance -g myresourcegroup --to-cluster-id $CLUSTER_RESOURCE_ID --mode linked
        - name: Clone an instance to a local directory.
          text: >
            az iot ops clone -n myinstance -g myresourcegroup --to-dir .
        - name: Clone an instance to a local directory, but splitting and linking to asset related sub-deployments.
          text: >
            az iot ops clone -n myinstance -g myresourcegroup --to-dir /my/content --mode linked
        - name: Hide progress displays and skip prompts.
          text: >
            az iot ops clone -n myinstance -g myresourcegroup --to-dir . --no-progress -y
    """

    helps[
        "iot ops enable-rsync"
    ] = """
        type: command
        short-summary: Enable edge to cloud hydration.
        long-summary: |
          This operation will lookup the K8 Bridge service principal then assign
          it to the scope of the IoT Operations instance custom location with the built-in
          role of Azure Kubernetes Service Arc Contributor by default.

        examples:
        - name: Enable resource sync for the instance.
          text: >
            az iot ops enable-rsync -n myinstance -g myresourcegroup
        - name: Enable resource sync for the instance and explictly provide the K8 Bridge principal OID.
          text: >
            az iot ops enable-rsync -n myinstance -g myresourcegroup --k8-bridge-sp-oid $TENANT_K8_BRIDGE_SP_OID
    """

    helps[
        "iot ops get-versions"
    ] = f"""
        type: command
        short-summary: Opens the version guide located at {GET_VERSIONS_URL} in the default browser.

        examples:
        - name: Route to the version guide in a new browser window.
          text: >
            az iot ops get-versions
    """

    helps[
        "iot ops migrate-assets"
    ] = f"""
        type: command
        short-summary: Migrate root assets to a namespace.
        long-summary: |
          Requires an instance version >= {MIN_INSTANCE_VERSION_V2}.

          The target set of root assets will be converted to an equivalent namespace representation
          replacing the original root assets.

          During the migration, namespace devices will be created in-place of the endpoint profiles
          referenced by the assets. If multiple assets reference the same endpoint profile, a
          single namespace device will be referenced by the migrated assets.

          Post migration use the `az iot ops ns asset` and `az iot ops ns device` command groups to
          manage namespace assets and devices.

          It is highly recommended to take a snapshot of the target instance via `az iot ops clone`
          before migration is executed. You can use the clone to restore the instance if needed.

          For glob-style pattern matching via --name-pattern, '*' or '?' or '[...]' can be used.

          By default the command will check if the Device Registry service principal has the
          `Azure Kubernetes Service Arc Contributor` built-in role against the custom location
          associated with the instance, applying the role if needed. This can be skipped with
          the `--skip-ra` flag.

        examples:
        - name: Migrate all root assets associated with the instance.
          text: >
            az iot ops migrate-assets -n myinstance --resource-group myresourcegroup
        - name: Migrate specific assets associated with the instance.
          text: >
            az iot ops migrate-assets -n myinstance --resource-group myresourcegroup
            --pattern asset1 asset2 asset3
        - name: Migrate assets associated with the instance that match glob-style patterns.
          text: >
            az iot ops migrate-assets -n myinstance --resource-group myresourcegroup
            --pattern asset-p1-* asset-eng?-01
    """
