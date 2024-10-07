# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
from typing import Dict, List, Optional, Union
from os.path import isfile

import pytest
from knack.log import get_logger

from azext_edge.edge.util.common import assemble_nargs_to_dict

from ....generators import generate_random_string
from ....helpers import run

logger = get_logger(__name__)


@pytest.fixture(scope="function")
def init_test_setup(settings, tracked_resources):
    from ....settings import EnvironmentVariables

    settings.add_to_config(EnvironmentVariables.rg.value)
    settings.add_to_config(EnvironmentVariables.cluster.value)
    settings.add_to_config(EnvironmentVariables.instance.value)
    settings.add_to_config(EnvironmentVariables.init_args.value)
    settings.add_to_config(EnvironmentVariables.create_args.value)
    settings.add_to_config(EnvironmentVariables.aio_cleanup.value)
    settings.add_to_config(EnvironmentVariables.init_continue_on_error.value)
    settings.add_to_config(EnvironmentVariables.init_redeployment.value)

    instance_name = settings.env.azext_edge_instance
    if not instance_name:
        instance_name = f"testcli{generate_random_string(force_lower=True, size=6)}"
    # set up registry
    storage_account_name = f"initstore{generate_random_string(force_lower=True, size=6)}"
    registry_name = f"init-registry-{generate_random_string(force_lower=True, size=6)}"
    registry_namespace = f"init-namespace-{generate_random_string(force_lower=True, size=6)}"
    storage_account = run(
        f"az storage account create -n {storage_account_name} -g {settings.env.azext_edge_rg} "
        "--enable-hierarchical-namespace --public-network-access Disabled "
        "--allow-shared-key-access false --allow-blob-public-access false --default-action Deny"
    )
    tracked_resources.append(storage_account['id'])
    registry = run(
        f"az iot ops schema registry create -n {registry_name} -g {settings.env.azext_edge_rg} "
        f"--rn {registry_namespace} --sa-resource-id {storage_account['id']} "
    )
    tracked_resources.append(registry["id"])

    if not all([settings.env.azext_edge_cluster, settings.env.azext_edge_rg]):
        raise AssertionError(
            "Cannot run init tests without a connected cluster and resource group. "
            f"Current settings:\n {settings}"
        )

    yield {
        "clusterName": settings.env.azext_edge_cluster,
        "resourceGroup": settings.env.azext_edge_rg,
        "schemaRegistryId": registry["id"],
        "instanceName": instance_name,
        "additionalCreateArgs": _strip_quotes(settings.env.azext_edge_create_args),
        "additionalInitArgs": _strip_quotes(settings.env.azext_edge_init_args),
        "continueOnError": settings.env.azext_edge_init_continue_on_error or False,
        "redeployment": settings.env.azext_edge_init_redeployment or False
    }
    if settings.env.azext_edge_aio_cleanup:
        run(
            f"az iot ops delete --cluster {settings.env.azext_edge_cluster} -g {settings.env.azext_edge_rg} "
            "-y --no-progress --force --include-deps"
        )
    else:
        # if the init + create worked - make sure that schema reg + storage account aren't deleted
        tracked_resources.remove(storage_account['id'])
        tracked_resources.remove(registry['id'])


@pytest.mark.init_scenario_test
def test_init_scenario(
    init_test_setup, tracked_files
):
    additional_init_args = init_test_setup["additionalInitArgs"] or ""
    init_arg_dict = _process_additional_args(additional_init_args)
    additional_create_args = init_test_setup["additionalCreateArgs"] or ""
    create_arg_dict = _process_additional_args(additional_create_args)
    _process_broker_config_file_arg(create_arg_dict, tracked_files)

    cluster_name = init_test_setup["clusterName"]
    resource_group = init_test_setup["resourceGroup"]
    registry_id = init_test_setup["schemaRegistryId"]
    instance_name = init_test_setup["instanceName"]
    command = f"az iot ops init -g {resource_group} --cluster {cluster_name} "\
        f"--sr-resource-id {registry_id} --no-progress {additional_init_args} "

    # TODO: assert return once there is a return for init
    run(command)

    assert_aio_init(cluster_name=cluster_name, resource_group=resource_group, **init_arg_dict)

    # create command
    create_command = f"az iot ops create -g {resource_group} --cluster {cluster_name} "\
        f"-n {instance_name} --no-progress {additional_create_args} "
    # TODO: assert create when return be returning
    run(create_command)

    if init_test_setup["redeployment"]:
        run(
            f"az iot ops delete --name {instance_name} -g {resource_group} "
            "-y --no-progress --force"
        )
        run(create_command)

    # Missing:
    # init
    # --kubernetes-distro + runtime-socket
    # --enable-fault-tolerance
    # --trust-source (one param)
    # create
    # --cluster-namespace

    try:
        for assertion in [
            assert_aio_instance,
            assert_broker_args,
            assert_dataflow_profile_args,
        ]:
            assertion(
                instance_name=instance_name,
                cluster_name=cluster_name,
                resource_group=resource_group,
                schema_registry_id=registry_id,
                **create_arg_dict
            )
    except Exception as e:  # pylint: disable=broad-except
        # Note we have this since there are multiple Exceptions that can occur:
        # AssertionError: normal assert error (assuming the expression can get evaluated)
        # CLIInternalError: a run to check existance fails
        # KeyError: one of the expected keys in the result is not present
        # TypeError: one of the values changes expected types and cannot be evaluated correctly (ex: len(None))
        # and more
        if init_test_setup["continueOnError"]:
            pytest.skip(f"Deployment succeeded but init assertions failed. \n{e}")
        raise e


def assert_aio_init(
    cluster_name: str,
    resource_group: str,
    ops_config: Optional[str] = None,
    **_,
):
    # check extensions installed
    cluster_id = run(
        f"az resource show -n {cluster_name} -g {resource_group} "
        "--resource-type Microsoft.Kubernetes/connectedClusters"
    )["id"]
    extension_result = run(
        f"az rest --method GET --url {cluster_id}/providers/"
        "Microsoft.KubernetesConfiguration/extensions?api-version=2023-05-01"
    )
    extensions = extension_result["value"]
    while extension_result.get("nextLink"):
        extension_result = run(f"az rest --method GET --url {extension_result['nextLink']}")
        extensions.extend(extension_result["value"])
    iot_ops_ext = None,
    iot_ops_platform_ext = None
    for ext in extensions:
        if ext["properties"]["extensionType"] == "microsoft.iotoperations":
            iot_ops_ext = ext
        elif ext["properties"]["extensionType"] == "microsoft.iotoperations.platform":
            iot_ops_platform_ext = ext

    if ops_config:
        ops_config = assemble_nargs_to_dict(ops_config.split())
        configs = iot_ops_ext["properties"]["configurationSettings"]
        for key, value in ops_config.items():
            assert configs[key] == value

    if not all([iot_ops_platform_ext, iot_ops_ext]):
        raise AssertionError(
            "Extensions for AIO are missing. These are the extensions "
            f"on the cluster: {[ext['name'] for ext in extensions]}."
        )


def assert_aio_instance(
    instance_name: str,
    resource_group: str,
    schema_registry_id: str,
    custom_location: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    enable_rsync: bool = False,
    tags: Optional[str] = None,
    **_
):
    instance_show = run(f"az iot ops show -n {instance_name} -g {resource_group}")
    tags = assemble_nargs_to_dict(tags)
    assert instance_show.get("tags", {}) == tags
    if location:
        assert instance_show["location"] == location
    expected_custom_location = instance_show["extendedLocation"]["name"].split("/")[-1]
    if custom_location:
        assert custom_location == expected_custom_location

    instance_props = instance_show["properties"]
    assert instance_props.get("description") == description
    assert instance_props["schemaRegistryRef"] == {"resource_id": schema_registry_id}

    expected_components = {"adr", "akri", "connectors", "dataflows", "schemaRegistry"}
    disabled_components = []
    unexpected_components = []
    for component, state in instance_props["components"].items():
        if state["state"].lower() != "enabled":
            disabled_components.append(component)
        if component in expected_components:
            expected_components.remove(component)
        else:
            unexpected_components.append(component)

    error_msg = []
    if disabled_components:
        error_msg.append(f"The following components are disabled: {disabled_components}.")
    if unexpected_components:
        error_msg.append(f"The following components are unexpected: {unexpected_components}.")
    if expected_components:
        error_msg.append(f"The following components are missing: {expected_components}.")
    if error_msg:
        raise AssertionError("\n".join(error_msg))

    tree = run(f"az iot ops show -n {instance_name} -g {resource_group} --tree")
    # no resource sync rules if disable rsync rules
    assert ("adr-sync" in tree) is enable_rsync
    assert expected_custom_location in tree
    assert "azure-iot-operations-platform" in tree


def assert_broker_args(
    instance_name: str,
    resource_group: str,
    add_insecure_listener: Optional[bool] = None,
    broker_backend_part: Optional[str] = None,
    broker_backend_rf: Optional[str] = None,
    broker_backend_workers: Optional[str] = None,
    broker_config_file: Optional[str] = None,
    broker_frontend_replicas: Optional[str] = None,
    broker_frontend_workers: Optional[str] = None,
    broker_listener_type: Optional[str] = None,
    broker_mem_profile: Optional[str] = None,
    bp: Optional[str] = None,
    br: Optional[str] = None,
    bw: Optional[str] = None,
    fr: Optional[str] = None,
    fw: Optional[str] = None,
    lt: Optional[str] = None,
    mp: Optional[str] = None,
    **_
):
    if bp:
        broker_backend_part = bp
    if br:
        broker_backend_rf = br
    if bw:
        broker_backend_workers = bw
    if fr:
        broker_frontend_replicas = fr
    if fw:
        broker_frontend_workers = fw
    if lt:
        broker_listener_type = lt
    if mp:
        broker_mem_profile = mp

    broker = run(f"az iot ops broker list -g {resource_group} -i {instance_name}")
    assert len(broker) == 1
    broker = broker[0]
    broker_name = broker["name"]
    assert broker_name == "default"

    if broker_config_file:
        with open(broker_config_file, "r", encoding="utf-8") as bcf:
            broker_config = json.loads(bcf)
            broker_mem_profile = broker_config.get("memoryProfile", "").lower()

            broker_backend = broker_config.get("cardinality", {}).get("backendChain", {})
            broker_backend_part = broker_backend.get("partitions")
            broker_backend_rf = broker_backend.get("redundancyFactor")
            broker_backend_workers = broker_backend.get("workers")

            broker_frontend = broker_config.get("cardinality", {}).get("frontend", {})
            broker_frontend_replicas = broker_frontend.get("replicas")
            broker_frontend_workers = broker_frontend.get("workers")

    broker_props = broker["properties"]
    assert broker_props["memoryProfile"].lower() == (broker_mem_profile or "medium")

    cardinality = broker_props["cardinality"]
    assert cardinality["backendChain"]["partitions"] == (broker_backend_part or 2)
    assert cardinality["backendChain"]["redundancyFactor"] == (broker_backend_rf or 2)
    assert cardinality["backendChain"]["workers"] == (broker_backend_workers or 2)
    assert cardinality["frontend"]["replicas"] == (broker_frontend_replicas or 2)
    assert cardinality["frontend"]["workers"] == (broker_frontend_workers or 2)
    # there is diagnostics + generateResourceLimits but nothing from init yet

    # nothing interesting in the authn
    authns = run(f"az iot ops broker authn list -g {resource_group} -i {instance_name} -b {broker_name}")
    assert len(authns) == 1

    # listener
    listeners = run(f"az iot ops broker listener list -g {resource_group} -i {instance_name} -b {broker_name}")
    assert len(listeners) == (2 if add_insecure_listener else 1)

    if add_insecure_listener:
        insecure = [listener for listener in listeners if listener["name"] == "default-insecure"][0]
        ports = insecure["properties"]["ports"]
        assert 1883 in [p['port'] for p in ports]

    secure_listener = [listener for listener in listeners if listener["name"] == "default"]
    listener_props = secure_listener[0]["properties"]
    assert listener_props["serviceType"].lower() == (broker_listener_type or "ClusterIp").lower()


def assert_dataflow_profile_args(
    instance_name: str,
    resource_group: str,
    dataflow_profile_instances: Optional[int] = None,
    **_
):
    profile = run(f"az iot ops dataflow profile list -g {resource_group} -i {instance_name}")
    profile_props = profile[0]["properties"]
    assert profile_props["instanceCount"] == (dataflow_profile_instances or 1)


def _process_additional_args(additional_args: str) -> Dict[str, Union[str, bool]]:
    arg_dict = {}
    for arg in additional_args.split("--")[1:]:
        arg = arg.strip().split(" ", maxsplit=1)
        # --simulate-plc vs --desc "potato cluster"
        arg[0] = arg[0].replace("-", "_")
        if len(arg) == 1 or arg[1].lower() == "true":
            arg_dict[arg[0]] = True
        elif arg[1].lower() == "false":
            arg_dict[arg[0]] = False
        else:
            arg_dict[arg[0]] = arg[1]
    return arg_dict


def _process_broker_config_file_arg(create_arg_dict: dict, tracked_files: List[str]):
    if "broker_config_file" in create_arg_dict:
        broker_config_path = create_arg_dict["broker_config_file"]
        if not isfile(broker_config_path):
            tracked_files.append(broker_config_path)
            with open(broker_config_path, "w", encoding="utf-8") as bcf:
                json.dump(DEFAULT_BROKER_CONFIG, bcf)


def _strip_quotes(argument: Optional[str]) -> Optional[str]:
    if not argument:
        return argument
    if argument[0] == argument[-1] and argument[0] in ("'", '"'):
        argument = argument[1:-1]
    return argument


DEFAULT_BROKER_CONFIG = {
    "advanced": {
        "encryptInternalTraffic": "Enabled"
    },
    "cardinality": {
        "backendChain": {
            "partitions": 2,
            "redundancyFactor": 2,
            "workers": 2
        },
        "frontend": {
            "replicas": 2,
            "workers": 2
        }
    },
    "diagnostics": {
        "logs": {
            "level": "info"
        },
        "metrics": {
            "prometheusPort": 9600
        },
        "selfCheck": {
            "intervalSeconds": 30,
            "mode": "Enabled",
            "timeoutSeconds": 15
        },
        "traces": {
            "cacheSizeMegabytes": 16,
            "mode": "Enabled",
            "selfTracing": {
                "intervalSeconds": 30,
                "mode": "Enabled"
            },
            "spanChannelCapacity": 1000
        }
    },
    "generateResourceLimits": {
        "cpu": "Disabled"
    },
    "memoryProfile": "Medium",
}
