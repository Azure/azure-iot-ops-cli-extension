# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple, Union

from knack.log import get_logger
from kubernetes.client.exceptions import ApiException
from kubernetes.client.models import V1Pod, V1PodList
from rich.console import Console, NewLine, Pretty
from rich.json import JSON
from rich.padding import Padding

from azext_edge.e4k.common import (
    BRIDGE_RESOURCE,
    BROKER_RESOURCE,
    CONSOLE_WIDTH,
    CheckTaskStatus,
    IotEdgeBrokerResource,
    ResourceState,
)

from .base import (
    DEFAULT_NAMESPACE,
    client,
    get_namespaced_object,
    get_namespaced_pods_by_prefix,
)

logger = get_logger(__name__)

console = Console(width=CONSOLE_WIDTH, highlight=False)


def run_checks(
    pre_deployment: bool = True, post_deployment: bool = True, as_list: bool = False
):
    from functools import partial

    desired_checks = {}
    result = {}

    if pre_deployment:
        result["preDeployment"] = []
        desired_checks.update(
            {"checkK8sVersion": partial(check_k8s_version, as_list=as_list)}
        )

        # with console.status("[bold green]Working on tasks...") as status:
        for c in desired_checks:
            output = desired_checks[c]()
            result["preDeployment"].append(output)

    if not as_list:
        return result

    process_as_list(result)


def process_as_list(result: Dict[str, dict]):
    pre_checks: List[dict] = result.get("preDeployment")
    if pre_checks:
        console.rule("Pre deployment checks", align="left")
        console.print(NewLine(1))

        for c in pre_checks:
            prefix_emoji = get_emoji_from_status(c["status"])
            console.print(Padding(f"{prefix_emoji} {c['description']}", (0, 0, 0, 4)))
            evaluations = c.get("evaluations", [])
            for e in evaluations:
                displays = e.get("displays", [])
                for d in displays:
                    console.print(d)
            console.print(NewLine(1))
        console.print(NewLine(1))


def get_emoji_from_status(status: str) -> str:
    if status == CheckTaskStatus.success.value:
        return "[green]:heavy_check_mark:[/green]"
    if status == CheckTaskStatus.warning.value:
        return "[yellow]:warning:[/yellow]"
    if status == CheckTaskStatus.skipped:
        return ":hammer:"
    if status == CheckTaskStatus.error:
        return "[red]:stop_sign:[/red]"


def check_k8s_version(as_list: bool = False):
    from kubernetes.client.models import VersionInfo
    from packaging import version
    from ..common import MIN_K8S_VERSION

    version_client = client.VersionApi()
    result = {}
    result["name"] = "minK8sVers"
    result["description"] = "Minimum Kubernetes server version"
    result["evaluations"] = []
    evaluation = {"expected": f">={MIN_K8S_VERSION}"}
    try:
        version_details: VersionInfo = version_client.get_code()
    except ApiException as ae:
        logger.debug(str(ae))
        result["status"] = CheckTaskStatus.warning.value
        evaluation["actual"] = "Unable to determine."
    else:
        major_version = version_details.major
        minor_version = version_details.minor
        semver = f"{major_version}.{minor_version}"
        evaluation["actual"] = semver
        if version.parse(semver) >= version.parse(MIN_K8S_VERSION):
            evaluation["status"] = CheckTaskStatus.success.value
        else:
            evaluation["status"] = CheckTaskStatus.error.value
        result["status"] = evaluation["status"]

    if as_list:
        evaluation["displays"] = [
            Padding(
                f"- Expected {{[blue]{evaluation['expected']}[/blue]}} actual {{[blue]{semver}[/blue]}}.",
                (0, 0, 0, 8),
            )
        ]
    result["evaluations"].append(evaluation)
    return result


def check_helm_version():
    from shutil import which
    from subprocess import run

    from packaging import version

    from azext_edge.e4k.constants import HELM_VERSION_MIN

    display_key = "Minimum helm version {expected>=3.8.0}"
    nested_displays = []
    nested_displays.append(
        Padding(
            "[yellow]:warning:[/yellow] Unable to fetch helm version. helm could not be located.",
            (0, 0, 0, 4),
        )
    )
    # status = CheckTaskStatus.warning.value

    helm_path = which("helm")
    if helm_path:
        result = run(
            [helm_path, "version", '--template="{{.Version}}"'],
            capture_output=True,
            check=True,
        )
        if result.returncode == 0:
            helm_semver = result.stdout.decode("utf-8").replace('"', "")
            if version.parse(helm_semver) > version.parse(HELM_VERSION_MIN):
                nested_displays[0] = Padding(
                    f":zap: System helm version is {helm_semver}", (0, 0, 0, 4)
                )
            else:
                nested_displays[0] = Padding(
                    f"[red]:stop_sign:[/red] System helm version is [{HELM_VERSION_MIN}]. Please upgrade.",
                    (0, 0, 0, 4),
                )
                # status = CheckTaskStatus.error.value

    display_key, status = _prefix_display_key(display_key, nested_displays)
    return {"display": {display_key: nested_displays}, "status": status}


def check_total_available_memory():
    from kubernetes.client.models import V1Node, V1NodeList
    from rich.padding import Padding

    core_client = client.CoreV1Api()
    nodes: V1NodeList = core_client.list_node()
    node_items: List[V1Node] = nodes.items

    status = CheckTaskStatus.error.value
    if not node_items:
        return {
            "display": "[red]:stop_sign:[/red] At least one node must be configured.",
            "status": status,
        }
    node_displays = []
    has_limited_node = False
    for node in node_items:
        memory: str = node.status.allocatable["memory"]
        # if memory.endswith("Ki"):
        memory = memory.replace("Ki", "")
        memory: int = int(int(memory) / 1024)
        name = node.metadata.name
        node_display = f"{name} [{memory}]"
        if memory < 140:
            node_display = f"{name} {{[yellow]{memory}MiB[/yellow]}}"
            has_limited_node = True
        else:
            node_display = f"{name} {{[green]{memory}MiB[/green]}}"
        node_displays.append(Padding(f"{node_display}", (0, 0, 0, 4)))

    display_key = "Total memory available per node"
    if has_limited_node:
        display_key = f"[yellow]:warning:[/yellow] {display_key}"
        status = CheckTaskStatus.warning.value
    else:
        display_key = f"[green]:heavy_check_mark:[/green] {display_key}"
        status = CheckTaskStatus.success.value

    return {"display": {display_key: node_displays}, "status": status}


pre_deployment_checks = {
    "checkK8sVersion": check_k8s_version,
    "checkHelmVersion": check_helm_version,
    "checkTotalAvailableMemory": check_total_available_memory,
}


def check_e4k_broker_config(namespace: Optional[str] = None):
    namespaced_object = get_namespaced_object(BROKER_RESOURCE, namespace)
    display_key = "E4K broker configuration"
    nested_displays = []

    if not namespaced_object:
        return {
            "display": "unable to detect namespaced object",
            "success": CheckTaskStatus.warning.value,
        }

    namespaced_items = namespaced_object.get("items")
    if not namespaced_items or len(namespaced_items) > 1:
        return {
            "display": f"expected number of brokers in {{{namespace}}} namespace is {{1}} found {{{len(namespaced_items)}}}",
            "success": CheckTaskStatus.error.value,
        }

    broker_object = namespaced_items[0]
    broker_metadata = broker_object.get("metadata")
    if not broker_metadata:
        return {
            "display": f"broker in namespace {{{namespace}}} has no field 'metadata'",
            "success": CheckTaskStatus.error.value,
        }

    broker_meta_name = broker_metadata.get("name")
    if not broker_meta_name:
        return {
            "display": f"broker in namespace {{{namespace}}} has no field 'metadata.name'",
            "success": CheckTaskStatus.error.value,
        }

    broker_spec = broker_object.get("spec")
    if not broker_spec:
        return {
            "display": f"broker in namespace {{{namespace}}} has no field 'spec'",
            "success": CheckTaskStatus.error.value,
        }

    broker_mode = broker_spec["mode"]

    if broker_mode == "distributed":
        cardinality = broker_spec.get("cardinality")
        if not cardinality:
            return {
                "display": f"broker in namespace {{{namespace}}} has no field 'spec.cardinality'",
                "success": CheckTaskStatus.error.value,
            }
        frontend = cardinality.get("frontend")
        if not frontend:
            return {
                "display": f"broker in namespace {{{namespace}}} has no field 'spec.cardinality.frontend'",
                "success": CheckTaskStatus.error.value,
            }
        frontend_replicas = frontend.get("replicas")
        result_prefix = (
            ":zap:" if frontend_replicas and frontend_replicas >= 1 else ":warning:"
        )
        nested_displays.append(
            Padding(
                f"{result_prefix} {{{broker_meta_name}}} resource minimum specs",
                (0, 0, 0, 4),
            )
        )
        nested_displays.append(
            Padding(
                f"Frontend replicas {{expected>=1, actual:{frontend_replicas}}}",
                (0, 0, 0, 10),
            )
        )
        backendChain = cardinality.get("backendChain")
        if not backendChain:
            return {
                "display": f"broker in namespace [{namespace}] has no field 'spec.cardinality.backendChain'",
                "success": CheckTaskStatus.error.value,
            }
        backend_replicas = backendChain.get("replicas")
        backend_chain_count = backendChain.get("chainCount")
        result_prefix = (
            ":zap:" if backend_replicas and backend_replicas >= 1 else ":warning:"
        )
        nested_displays.append(
            Padding(
                f"Backend replicas {{expected>=1, actual:{backend_replicas}}}",
                (0, 0, 0, 10),
            )
        )
        result_prefix = (
            ":zap:" if backend_chain_count and backend_chain_count >= 1 else ":warning:"
        )
        nested_displays.append(
            Padding(
                f"Backend chain count {{expected>=1, actual:{backend_replicas}}}",
                (0, 0, 0, 10),
            )
        )

        display_key, status = _prefix_display_key(display_key, nested_displays)
        return {"display": {display_key: nested_displays}, "status": status}


def check_e4k_broker_health(namespace: Optional[str] = None):
    namespaced_object = get_namespaced_object(BROKER_RESOURCE, namespace)

    display_key = "E4K broker health"
    nested_displays = []

    broker_name = namespaced_object["items"][0]["metadata"]["name"]
    broker_status_obj = namespaced_object["items"][0].get("status")
    if not broker_status_obj:
        return {
            "display": f"{{{broker_name}}} current state unknown",
            "success": CheckTaskStatus.error.value,
        }

    broker_status = broker_status_obj["status"]
    broker_status_desc = broker_status_obj.get("statusDescription")

    if broker_status == ResourceState.starting.value:
        result_prefix = ":warning:"
        nested_displays.append(
            Padding(
                f"{result_prefix} {{{broker_name}}} current state {{[light_sea_green]{broker_status}[/light_sea_green]}} - {broker_status_desc}. This is a healthy state, please retry.",
                (0, 0, 0, 4),
            )
        )
    elif (
        broker_status == ResourceState.running.value
        or broker_status == ResourceState.recovering.value
    ):
        result_prefix = ":zap:"
        nested_displays.append(
            Padding(
                f"{result_prefix} {{{broker_name}}} current state {{[light_sea_green]Ready[/light_sea_green]}} - {broker_status_desc}.",
                (0, 0, 0, 4),
            )
        )
    else:
        result_prefix = ":stop_sign:"
        nested_displays.append(
            Padding(
                f"{result_prefix} {{{broker_name}}} current state {{[light_sea_green]{broker_status}[/light_sea_green]}} - {broker_status_desc}.",
                (0, 0, 0, 4),
            )
        )

    display_key, status = _prefix_display_key(display_key, nested_displays)
    return {"display": {display_key: nested_displays}, "status": status}


def check_mqtt_bridge_health(namespace: Optional[str] = None):
    namespaced_object = get_namespaced_object(BRIDGE_RESOURCE, namespace)

    display_key = "E4K MQTT bridge health"
    nested_displays = []

    if not namespaced_object.get("items"):
        nested_displays.append(
            Padding(
                ":hammer: No E4K bridge installed.",
                (0, 0, 0, 4),
            )
        )
    else:
        valid_bridges = {}
        for bridge in namespaced_object["items"]:
            bridge_metadata: dict = bridge["metadata"]
            bridge_name = bridge_metadata.get("name")
            if not bridge_name:
                nested_displays.append(
                    Padding(
                        f":stop_sign: MQTT bridge in namespace '{namespace}' has no field 'name'.",
                        (0, 0, 0, 4),
                    )
                )
            else:
                valid_bridges[bridge_name] = bridge
        if valid_bridges:
            for bridge_name in valid_bridges:
                bridge_status = valid_bridges[bridge_name].get("status")
                bridge_config_status_level = None
                if bridge_status:
                    bridge_config_status_level = bridge_status.get("configStatusLevel")
                # @digimaun - delta, no configStatusLevel == unknown vs error
                if not any([bridge_status, bridge_config_status_level]):
                    nested_displays.append(
                        Padding(
                            f"[yellow]:warning:[/yellow] {{{bridge_name}}} current state unknown.",
                            (0, 0, 0, 4),
                        )
                    )
                else:
                    prefix = None
                    if bridge_config_status_level.lower() == "warn":
                        prefix = "[yellow]:warning:[/yellow]"
                    elif bridge_config_status_level.lower() == "error":
                        prefix = "[red]:stop_sign:[/red]"
                    else:
                        prefix = ":zap:"

                    nested_displays.append(
                        Padding(
                            f"{prefix} {{{bridge_name}}} current state {{[light_sea_green]{bridge_config_status_level}[/light_sea_green]}}.",
                            (0, 0, 0, 4),
                        )
                    )

    display_key, status = _prefix_display_key(display_key, nested_displays)
    return {"display": {display_key: nested_displays}, "status": status}


def check_frontend_service(namespace: Optional[str] = None):
    from kubernetes.client.models import V1LoadBalancerIngress, V1Service

    from azext_edge.e4k.common import AZEDGE_FRONTEND_POD_PREFIX

    display_key = "E4K frontend service has at least one external IP"
    nested_displays = []

    if not namespace:
        namespace = DEFAULT_NAMESPACE

    v1 = client.CoreV1Api()
    frontend_service: V1Service = v1.read_namespaced_service(
        name=AZEDGE_FRONTEND_POD_PREFIX, namespace=namespace
    )
    frontend_service_ingress: List[
        V1LoadBalancerIngress
    ] = frontend_service.status.load_balancer.ingress

    host_or_ips = []
    for i in frontend_service_ingress:
        host_or_ip = i.ip or i.hostname
        if host_or_ip:
            host_or_ips.append(host_or_ip)

    nested_displays.append(
        Padding(f":zap: Service {{{AZEDGE_FRONTEND_POD_PREFIX}}} ingress", (0, 0, 0, 4))
    )
    if frontend_service_ingress:
        for i in range(len(frontend_service_ingress)):
            nested_displays.append(
                Padding(
                    f"{i}: [deep_sky_blue4]{frontend_service_ingress[i].ip}[/deep_sky_blue4]",
                    (0, 0, 0, 8),
                )
            )
    else:
        pass

    display_key, status = _prefix_display_key(display_key, nested_displays)
    return {"display": {display_key: nested_displays}, "status": status}


def check_cloud_connector_health(namespace: Optional[str] = None):
    import tomli
    from kubernetes.client.models import V1ConfigMap, V1Pod, V1PodList

    from azext_edge.e4k.common import AZEDGE_KAFKA_CONFIG_PREFIX

    display_key = "E4K Cloud Connector health"
    nested_displays = []

    if not namespace:
        namespace = DEFAULT_NAMESPACE

    v1 = client.CoreV1Api()

    target_pods: List[V1Pod] = []
    pods_list: V1PodList = v1.list_namespaced_pod(
        namespace=namespace, label_selector="app=azedge-connector"
    )
    if not pods_list.items:
        nested_displays.append(
            Padding(
                f":hammer: No connector pods discovered in namespace {namespace}.",
                (0, 0, 0, 4),
            )
        )
    else:
        target_pods.extend(pods_list.items)
        for pod in target_pods:
            connector_prefix = ":zap:"
            pod_name: str = pod.metadata.name
            pod_name_parts = pod_name.split("-")
            pod_config_key = (
                f"{AZEDGE_KAFKA_CONFIG_PREFIX}-{'-'.join(pod_name_parts[2:-2])}"
            )
            connector_config: V1ConfigMap = v1.read_namespaced_config_map(
                name=pod_config_key, namespace=namespace
            )
            config_data = connector_config.data.get("config.toml")
            if not config_data:
                pass
            else:
                parsed_toml = tomli.loads(config_data)
                config_routes = parsed_toml.get("route", [])
                routes_prefix = ""
                if not config_routes:
                    connector_prefix = routes_prefix = "[yellow]:warning:[/yellow]"

                nested_displays.append(
                    Padding(
                        f"{connector_prefix} Connector {{{pod_name}}} pod", (0, 0, 0, 4)
                    )
                )
                nested_displays.append(
                    Padding(
                        f"Status: {{{_decorate_pod_phase(pod.status.phase)}}}",
                        (0, 0, 0, 10),
                    )
                )
                nested_displays.append(
                    Padding(
                        f"StartTime: {{{pod.status.start_time.strftime('%a %d %b %Y, %I:%M%p %Z')}}}",
                        (0, 0, 0, 10),
                    )
                )
                nested_displays.append(Padding(f"{routes_prefix}Routes", (0, 0, 0, 10)))
                for i in range(len(config_routes)):
                    # i keys: kafka, mqtt, sink_to
                    nested_displays.append(
                        Padding(f"{i}: {config_routes[i]}", (0, 0, 0, 12))
                    )

    display_key, status = _prefix_display_key(display_key, nested_displays)
    return {"display": {display_key: nested_displays}, "status": status}


def check_e4k_diagnostics_health(namespace: Optional[str] = None):
    from kubernetes.client.models import V1ConfigMap, V1Pod, V1PodList, V1Service

    from azext_edge.e4k.common import (
        AZEDGE_DIAGNOSTICS_POD_PREFIX,
        AZEDGE_DIAGNOSTICS_PROBE_POD_NAME_PREFIX,
        AZEDGE_DIAGNOSTICS_SERVICE,
    )

    display_key = "E4K diagnostics health"
    nested_displays = []

    if not namespace:
        namespace = DEFAULT_NAMESPACE

    v1 = client.CoreV1Api()

    diagnostics_service: V1Service = v1.read_namespaced_service(
        name=AZEDGE_DIAGNOSTICS_SERVICE, namespace=namespace
    )
    nested_displays.append(
        Padding(
            f":zap: Service {{{diagnostics_service.metadata.name}}} available.",
            (0, 0, 0, 4),
        )
    )
    # TODO not found.
    # return []string{"The [" + constants.DIAGNOSTICS_SERVICE_NAME + "] service or one of its components is not deployed"}, false

    target_pods, exception = get_namespaced_pods_by_prefix(
        prefix=AZEDGE_DIAGNOSTICS_POD_PREFIX, namespace=namespace
    )
    if exception:
        nested_displays.append(
            Padding(
                "[yellow]:warning:[/yellow] Diagnostics pod not found.", (0, 0, 0, 4)
            )
        )
    else:
        diagnostic_pod = target_pods[0]
        diagnostic_pod_name: str = diagnostic_pod.metadata.name

        nested_displays.append(
            Padding(f":zap: Diagnostics {{{diagnostic_pod_name}}} pod", (0, 0, 0, 4))
        )
        nested_displays.append(
            Padding(
                f"Status: {{{_decorate_pod_phase(diagnostic_pod.status.phase)}}}",
                (0, 0, 0, 10),
            )
        )
        # TODO: Show running pod?

    target_pods, exception = get_namespaced_pods_by_prefix(
        prefix=AZEDGE_DIAGNOSTICS_PROBE_POD_NAME_PREFIX, namespace=namespace
    )
    if exception:
        nested_displays.append(
            Padding(
                "[yellow]:warning:[/yellow]  Diagnostics Probe pod not found.",
                (0, 0, 0, 4),
            )
        )
    else:
        diagnostic_probe_pod = target_pods[0]
        diagnostic_probe_pod_name: str = diagnostic_probe_pod.metadata.name

        nested_displays.append(
            Padding(
                f":zap: Diagnostics Probe {{{diagnostic_probe_pod_name}}} pod",
                (0, 0, 0, 4),
            )
        )
        nested_displays.append(
            Padding(
                f"Status: {{{_decorate_pod_phase(diagnostic_probe_pod.status.phase)}}}",
                (0, 0, 0, 10),
            )
        )

    display_key, status = _prefix_display_key(display_key, nested_displays)
    return {"display": {display_key: nested_displays}, "status": status}


post_deployment_checks = {
    "checkE4KBrokerConfig": check_e4k_broker_config,
    "checkE4KBrokerHealth": check_e4k_broker_health,
    "checkE4KFrontEndService": check_frontend_service,
    "checkE4KMqttBridgeHealth": check_mqtt_bridge_health,
    "checkE4KCloudConnectorHealth": check_cloud_connector_health,
    "checkE4KDiagnosticsHealth": check_e4k_diagnostics_health,
}


def _prefix_display_key(
    key: str, displays: List[Union[str, Padding]]
) -> Tuple[str, str]:
    is_warning = False
    is_error = False
    is_skipped = False
    for d in displays:
        if isinstance(d, NewLine):
            continue
        if isinstance(d, Padding):
            d = d.renderable
            if isinstance(d, (Pretty, JSON)):
                continue
        if ":warning:" in d:
            is_warning = True
        if ":stop_sign:" in d:
            is_error = True
        if ":hammer:" in d:
            is_skipped = True

    if is_error:
        return f"[red]:stop_sign:[/red] {key}", CheckTaskStatus.error.value
    if is_warning:
        return f"[yellow]:warning:[/yellow] {key}", CheckTaskStatus.warning.value
    if is_skipped:
        return f":hammer: {key}", CheckTaskStatus.skipped.value

    return (
        f"[green]:heavy_check_mark:[/green] {key} - [green]OK[/green]",
        CheckTaskStatus.success.value,
    )


def _decorate_pod_phase(phase: str) -> str:
    from ..common import PodState

    if phase == PodState.failed.value:
        return f"[red]{phase}[/red]"
    if phase in [PodState.unknown.value, PodState.pending.value]:
        return f"[yellow]{phase}[/yellow]"
    return f"[green]{phase}[/green]"
