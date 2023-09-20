# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from functools import partial
from typing import Any, Dict, List, Optional, Tuple, Union
from enum import Enum

from knack.log import get_logger
from kubernetes.client.exceptions import ApiException
from kubernetes.client.models import (
    V1APIResource,
    V1APIResourceList,
)
from rich.console import Console, NewLine
from rich.padding import Padding

from ..common import (
    AZEDGE_DIAGNOSTICS_SERVICE,
    AZEDGE_DIAGNOSTICS_PROBE_PREFIX,
    AZEDGE_FRONTEND_PREFIX,
    AZEDGE_BACKEND_PREFIX,
    AZEDGE_AUTH_PREFIX,
    BLUEFIN_NATS_PREFIX,
    BLUEFIN_OPERATOR_CONTROLLER_MANAGER,
    BLUEFIN_READER_WORKER_PREFIX,
    BLUEFIN_REFDATA_STORE_PREFIX,
    BLUEFIN_RUNNER_WORKER_PREFIX,
    CheckTaskStatus,
    ProvisioningState,
    ResourceState,
)

from ..providers.edge_api import E4K_ACTIVE_API, E4kResourceKinds
from ..providers.edge_api import BLUEFIN_API_V1, BluefinResourceKinds
from .support.e4k import E4K_LABEL

from .base import (
    client,
    get_cluster_custom_api,
    get_namespaced_pods_by_prefix,
    get_namespaced_service,
)

logger = get_logger(__name__)

console = Console(width=100, highlight=False)


def run_checks(
    edge_service: str = "e4k",
    extended: Optional[bool] = False,
    namespace: Optional[str] = None,
    pre_deployment: bool = True,
    post_deployment: bool = True,
    as_list: bool = False,
):
    result = {}

    # with console.status("Analyzing cluster..."):
    from time import sleep

    sleep(0.25)

    result["title"] = f"Evaluation for {{[bright_blue]{edge_service}[/bright_blue]}} edge service deployment"

    if pre_deployment:
        result["preDeployment"] = []
        desired_checks = {}
        desired_checks.update(
            {
                "checkK8sVersion": partial(check_k8s_version, as_list=as_list),
                "checkHelmVersion": partial(check_helm_version, as_list=as_list),
                "checkNodes": partial(check_nodes, as_list=as_list),
            }
        )

        for c in desired_checks:
            output = desired_checks[c]()
            result["preDeployment"].append(output)

    if post_deployment:
        if not namespace:
            from .base import DEFAULT_NAMESPACE

            namespace = DEFAULT_NAMESPACE
        result["postDeployment"] = []
        
        # check post deployment according to edge_service type
        if edge_service == "e4k":
            check_e4k_post_deployment(extended=extended, namespace=namespace, result=result, as_list=as_list)
        elif edge_service == "bluefin":
            check_bluefin_post_deployment(extended=extended, namespace=namespace, result=result, as_list=as_list)


        if not as_list:
            return result

        process_as_list(result=result, namespace=namespace)


def check_e4k_post_deployment(
    namespace: str,
    result: dict,
    as_list: bool = False,
    extended: Optional[bool] = False,
):

    resource_enumeration, api_resources = enumerate_edge_service_resources(
        api_group=E4K_ACTIVE_API.group,
        api_version=E4K_ACTIVE_API.version,
        check_name="enumerateE4kApi",
        check_desc="Enumerate E4K API resource",
        target_api=E4K_ACTIVE_API.as_str(),
        as_list=as_list)
    result["postDeployment"].append(resource_enumeration)
    if api_resources:
        if "Broker" in api_resources:
            result["postDeployment"].append(evaluate_brokers(namespace=namespace, as_list=as_list))
        if "BrokerListener" in api_resources:
            result["postDeployment"].append(evaluate_broker_listeners(namespace=namespace, as_list=as_list))
        if "DiagnosticService" in api_resources:
            result["postDeployment"].append(evaluate_diagnostics_service(namespace=namespace, as_list=as_list))
        if "MqttBridgeConnector" in api_resources:
            # result["postDeployment"].append(evaluate_bridge_connectors(namespace=namespace, as_list=as_list))
            pass


def check_bluefin_post_deployment(
    namespace: str,
    result: dict,
    as_list: bool = False,
    extended: Optional[bool] = False,
):

    resource_enumeration, api_resources = enumerate_edge_service_resources(
        api_group=BLUEFIN_API_V1.group,
        api_version=BLUEFIN_API_V1.version,
        check_name="enumerateBluefinApi",
        check_desc="Enumerate Bluefin API resource",
        target_api=BLUEFIN_API_V1.as_str(),
        as_list=as_list)
    result["postDeployment"].append(resource_enumeration)
    if api_resources:
        if "Instance" in api_resources:
            result["postDeployment"].append(evaluate_instances(namespace=namespace, as_list=as_list))
        if "Pipeline" in api_resources:
            result["postDeployment"].append(evaluate_pipelines(extended=extended, namespace=namespace, as_list=as_list))
        if "Dataset" in api_resources:
            result["postDeployment"].append(evaluate_datasets(extended=extended, namespace=namespace, as_list=as_list))


def process_as_list(result: Dict[str, dict], namespace: str):
    success_count: int = 0
    warning_count: int = 0
    error_count: int = 0
    skipped_count: int = 0

    def _increment_summary(status: str):
        nonlocal success_count, warning_count, error_count, skipped_count
        if not status:
            return
        if status == CheckTaskStatus.success.value:
            success_count = success_count + 1
        elif status == CheckTaskStatus.warning.value:
            warning_count = warning_count + 1
        elif status == CheckTaskStatus.error.value:
            error_count = error_count + 1
        elif status == CheckTaskStatus.skipped.value:
            skipped_count = skipped_count + 1

    def _print_summary():
        from rich.panel import Panel

        success_content = f"[green]{success_count} check(s) succeeded.[/green]"
        warning_content = f"{warning_count} check(s) raised warnings."
        warning_content = (
            f"[green]{warning_content}[/green]" if not warning_count else f"[yellow]{warning_content}[/yellow]"
        )
        error_content = f"{error_count} check(s) raised errors."
        error_content = f"[green]{error_content}[/green]" if not error_count else f"[red]{error_content}[/red]"
        skipped_content = f"[bright_white]{skipped_count} check(s) were skipped[/bright_white]."
        content = f"{success_content}\n{warning_content}\n{error_content}\n{skipped_content}"
        console.print(Panel(content, title="Check Summary", expand=False))

    def _enumerate_displays(checks: List[Dict[str, dict]]):
        for c in checks:
            status = c.get("status")
            prefix_emoji = get_emoji_from_status(status)
            console.print(Padding(f"{prefix_emoji} {c['description']}", (0, 0, 0, 4)))

            targets = c.get("targets", {})
            for t in targets:
                displays = targets[t].get("displays", [])
                for d in displays:
                    console.print(d)
                target_status = targets[t].get("status")
                evaluations = targets[t].get("evaluations", [])
                if not evaluations:
                    _increment_summary(target_status)
                for e in evaluations:
                    eval_status = e.get("status")
                    _increment_summary(eval_status)
            console.print(NewLine(1))
        console.print(NewLine(1))

    title: dict = result.get("title")
    if title:
        console.print(NewLine(1))
        console.rule(title, align="center", style="blue bold")
        console.print(NewLine(1))

    pre_checks: List[dict] = result.get("preDeployment")
    if pre_checks:
        console.rule("Pre deployment checks", align="left")
        console.print(NewLine(1))
        _enumerate_displays(pre_checks)

    post_checks: List[dict] = result.get("postDeployment")
    if post_checks:
        console.rule("Post deployment checks", align="left")
        console.print(NewLine(1))
        _enumerate_displays(post_checks)

    _print_summary()


def get_emoji_from_status(status: str) -> str:
    if not status:
        return ""
    if status == CheckTaskStatus.success.value:
        return "[green]:heavy_check_mark:[/green]"
    if status == CheckTaskStatus.warning.value:
        return "[yellow]:warning:[/yellow]"
    if status == CheckTaskStatus.skipped.value:
        return ":hammer:"
    if status == CheckTaskStatus.error.value:
        return "[red]:stop_sign:[/red]"


def evaluate_diagnostics_service(
    namespace: str,
    as_list: bool = False,
):
    check_manager = CheckManager(
        check_name="evalBrokerDiag",
        check_desc="Evaluate E4K Diagnostics Service",
        namespace=namespace,
    )
    diagnostics_service_list: dict = E4K_ACTIVE_API.get_resources(kind=E4kResourceKinds.DIAGNOSTIC_SERVICE, namespace=namespace)
    diagnostics_service_resources = diagnostics_service_list.get("items", [])
    target_diagnostic_service = "diagnosticservices.az-edge.com"

    check_manager.add_target(target_name=target_diagnostic_service, conditions=[
        "len(diagnosticservices)==1",
        "spec"
    ])

    diagnostics_count_text = "- Expecting [bright_blue]1[/bright_blue] diagnostics service resource per namespace. {}."
    diagnostic_service_count = len(diagnostics_service_resources)

    service_count_status = CheckTaskStatus.success.value
    service_status_color = "green"

    # warn if we have <0, >1 diagnostic service resources
    if diagnostic_service_count != 1:
        service_count_status = CheckTaskStatus.warning.value
        service_status_color = "yellow"

    diagnostics_count_text = diagnostics_count_text.format(f"[{service_status_color}]Detected {diagnostic_service_count}[/{service_status_color}]")

    check_manager.add_target_eval(target_name=target_diagnostic_service, status=service_count_status, value=diagnostic_service_count)
    check_manager.add_display(target_name=target_diagnostic_service, display=Padding(diagnostics_count_text, (0, 0, 0, 8)))

    if not diagnostics_service_resources:
        return check_manager.as_dict(as_list)

    for diag_service_resource in diagnostics_service_resources:
        diag_service_resource_name = diag_service_resource["metadata"]["name"]
        diag_service_resource_spec: dict = diag_service_resource["spec"]

        check_manager.add_display(
            target_name=target_diagnostic_service,
            display=Padding(
                f"\n- Diagnostic service resource {{[bright_blue]{diag_service_resource_name}[/bright_blue]}}.",
                (0, 0, 0, 8),
            ),
        )

        diag_service_spec_data_export_freq = diag_service_resource_spec.get("dataExportFrequencySeconds")
        diag_service_spec_log_format = diag_service_resource_spec.get("logFormat")
        diag_service_spec_log_level = diag_service_resource_spec.get("logLevel")
        diag_service_spec_max_data_storage_size = diag_service_resource_spec.get("maxDataStorageSize")
        diag_service_spec_metrics_port = diag_service_resource_spec.get("metricsPort")
        diag_service_spec_stale_data_timeout = diag_service_resource_spec.get("staleDataTimeoutSeconds")

        check_manager.add_display(
            target_name=target_diagnostic_service,
            display=Padding(
                f"Data Export Frequency: [bright_blue]{diag_service_spec_data_export_freq}[/bright_blue] seconds",
                (0, 0, 0, 12),
            ),
        )
        check_manager.add_display(
            target_name=target_diagnostic_service,
            display=Padding(
                f"Log Format: [bright_blue]{diag_service_spec_log_format}[/bright_blue]",
                (0, 0, 0, 12),
            ),
        )
        check_manager.add_display(
            target_name=target_diagnostic_service,
            display=Padding(
                f"Log Level: [bright_blue]{diag_service_spec_log_level}[/bright_blue]",
                (0, 0, 0, 12),
            ),
        )
        check_manager.add_display(
            target_name=target_diagnostic_service,
            display=Padding(
                f"Max Data Storage Size: [bright_blue]{diag_service_spec_max_data_storage_size}[/bright_blue]",
                (0, 0, 0, 12),
            ),
        )
        check_manager.add_display(
            target_name=target_diagnostic_service,
            display=Padding(
                f"Metrics Port: [bright_blue]{diag_service_spec_metrics_port}[/bright_blue]",
                (0, 0, 0, 12),
            ),
        )
        check_manager.add_display(
            target_name=target_diagnostic_service,
            display=Padding(
                f"Stale Data Timeout: [bright_blue]{diag_service_spec_stale_data_timeout}[/bright_blue] seconds",
                (0, 0, 0, 12),
            ),
        )

        check_manager.add_target_eval(
            target_name=target_diagnostic_service,
            status=CheckTaskStatus.success.value,
            value={"spec": diag_service_resource_spec},
        )

    target_service_deployed = f"service/{AZEDGE_DIAGNOSTICS_SERVICE}"
    check_manager.add_target(
        target_name=target_service_deployed, conditions=["spec.clusterIP", "spec.ports"]
    )
    check_manager.add_display(
        target_name=target_service_deployed,
        display=Padding(
            "\nService Status",
            (0, 0, 0, 8),
        ),
    )

    diagnostics_service = get_namespaced_service(
        name=AZEDGE_DIAGNOSTICS_SERVICE, namespace=namespace, as_dict=True
    )
    if not diagnostics_service:
        check_manager.add_target_eval(
            target_name=target_service_deployed, status=CheckTaskStatus.error.value, value=None
        )
        diag_service_desc_suffix = "[red]not detected[/red]."
        diag_service_desc = f"Service {{[bright_blue]{AZEDGE_DIAGNOSTICS_SERVICE}[/bright_blue]}} {diag_service_desc_suffix}"
        check_manager.add_display(
            target_name=target_service_deployed,
            display=Padding(
                diag_service_desc,
                (0, 0, 0, 12),
            ),
        )
    else:
        clusterIP = diagnostics_service.get("spec", {}).get("clusterIP")
        ports: List[dict] = diagnostics_service.get("spec", {}).get("ports", [])

        check_manager.add_target_eval(
            target_name=target_service_deployed,
            status=CheckTaskStatus.success.value,
            value={"spec": {"clusterIP": clusterIP, "ports": ports}},
            resource_name=diagnostics_service["metadata"]["name"],
        )
        diag_service_desc_suffix = "[green]detected[/green]."
        diag_service_desc = f"Service {{[bright_blue]{AZEDGE_DIAGNOSTICS_SERVICE}[/bright_blue]}} {diag_service_desc_suffix}"
        check_manager.add_display(
            target_name=target_service_deployed,
            display=Padding(
                diag_service_desc,
                (0, 0, 0, 12),
            ),
        )
        if ports:
            for port in ports:
                check_manager.add_display(
                    target_name=target_service_deployed,
                    display=Padding(
                        f"[cyan]{port.get('name')}[/cyan] "
                        f"port [bright_blue]{port.get('port')}[/bright_blue] "
                        f"protocol [cyan]{port.get('protocol')}[/cyan]",
                        (0, 0, 0, 16),
                    ),
                )
            check_manager.add_display(target_name=target_service_deployed, display=NewLine())

        evaluate_pod_health(
            check_manager=check_manager,
            namespace=namespace,
            pod=AZEDGE_DIAGNOSTICS_SERVICE,
            display_padding=12,
            service_label=E4K_LABEL
        )

    return check_manager.as_dict(as_list)


def evaluate_broker_listeners(
    namespace: str,
    as_list: bool = False,
):
    check_manager = CheckManager(
        check_name="evalBrokerListeners", check_desc="Evaluate E4K broker listeners", namespace=namespace
    )

    target_listeners = "brokerlisteners.az-edge.com"
    listener_conditions = ["len(brokerlisteners)>=1", "spec", "valid(spec.brokerRef)", "spec.serviceName", "status"]
    check_manager.add_target(target_name=target_listeners, conditions=listener_conditions)

    valid_broker_refs = _get_valid_references(kind=E4kResourceKinds.BROKER, namespace=namespace)
    listener_list: dict = E4K_ACTIVE_API.get_resources(E4kResourceKinds.BROKER_LISTENER, namespace=namespace)

    if not listener_list:
        fetch_listeners_error_text = (
            f"Unable to fetch {E4kResourceKinds.BROKER_LISTENER.value}s."
        )
        check_manager.add_target_eval(
            target_name=target_listeners, status=CheckTaskStatus.error.value, value=fetch_listeners_error_text
        )
        check_manager.add_display(
            target_name=target_listeners, display=Padding(fetch_listeners_error_text, (0, 0, 0, 8))
        )
        return check_manager.as_dict(as_list)

    listeners: List[dict] = listener_list.get("items", [])
    listeners_count = len(listeners)
    listener_count_desc = "- Expecting [bright_blue]>=1[/bright_blue] broker listeners per namespace. {}"
    listeners_eval_status = CheckTaskStatus.success.value

    if listeners_count >= 1:
        listener_count_desc = listener_count_desc.format(f"[green]Detected {listeners_count}[/green].")
    else:
        listener_count_desc = listener_count_desc.format(f"[yellow]Detected {listeners_count}[/yellow].")
        check_manager.set_target_status(target_name=target_listeners, status=CheckTaskStatus.warning.value)
        # TODO listeners_eval_status = CheckTaskStatus.warning.value
    check_manager.add_display(target_name=target_listeners, display=Padding(listener_count_desc, (0, 0, 0, 8)))

    processed_services = {}
    for listener in listeners:
        listener_name: str = listener["metadata"]["name"]
        listener_spec_service_name: str = listener["spec"]["serviceName"]
        listener_spec_service_type: str = listener["spec"]["serviceType"]
        listener_broker_ref: str = listener["spec"]["brokerRef"]

        listener_eval_value = {}
        listener_eval_value["spec"] = listener["spec"]

        if listener_broker_ref not in valid_broker_refs:
            ref_display = f"[red]Invalid[/red] broker reference {{[red]{listener_broker_ref}[/red]}}."
            listeners_eval_status = CheckTaskStatus.error.value
            listener_eval_value["valid(spec.brokerRef)"] = False
        else:
            ref_display = f"[green]Valid[/green] broker reference {{[green]{listener_broker_ref}[/green]}}."
            listener_eval_value["valid(spec.brokerRef)"] = True

        listener_desc = f"\n- Broker Listener {{[bright_blue]{listener_name}[/bright_blue]}}. {ref_display}"
        check_manager.add_display(target_name=target_listeners, display=Padding(listener_desc, (0, 0, 0, 8)))
        check_manager.add_display(
            target_name=target_listeners,
            display=Padding(
                f"Port: [bright_blue]{listener['spec']['port']}[/bright_blue]",
                (0, 0, 0, 12),
            ),
        )
        check_manager.add_display(
            target_name=target_listeners,
            display=Padding(
                f"AuthN enabled: [bright_blue]{listener['spec']['authenticationEnabled']}[/bright_blue]",
                (0, 0, 0, 12),
            ),
        )
        check_manager.add_display(
            target_name=target_listeners,
            display=Padding(
                f"AuthZ enabled: [bright_blue]{listener['spec']['authenticationEnabled']}[/bright_blue]",
                (0, 0, 0, 12),
            ),
        )
        node_port = listener["spec"].get("nodePort")
        if node_port:
            check_manager.add_display(
                target_name=target_listeners,
                display=Padding(
                    f"Node Port: [bright_blue]{node_port}[/bright_blue]",
                    (0, 0, 0, 12),
                ),
            )

        if listener_spec_service_name not in processed_services:
            target_listener_service = f"service/{listener_spec_service_name}"
            listener_service_eval_status = CheckTaskStatus.success.value
            check_manager.add_target(target_name=target_listener_service)

            associated_service: dict = get_namespaced_service(
                name=listener_spec_service_name, namespace=namespace, as_dict=True
            )
            processed_services[listener_spec_service_name] = True
            if not associated_service:
                listener_service_eval_status = CheckTaskStatus.warning.value
                check_manager.add_display(
                    target_name=target_listeners,
                    display=Padding(
                        f"\n[red]Unable[/red] to fetch service {{[red]{listener_spec_service_name}[/red]}}.",
                        (0, 0, 0, 12),
                    ),
                )
                check_manager.add_target_eval(
                    target_name=target_listener_service,
                    status=listener_service_eval_status,
                    value="Unable to fetch service.",
                )
            else:
                check_manager.add_display(
                    target_name=target_listener_service,
                    display=Padding(
                        f"\nService {{[bright_blue]{listener_spec_service_name}[/bright_blue]}} of type [bright_blue]{listener_spec_service_type}[/bright_blue]",
                        (0, 0, 0, 8),
                    ),
                )

                if listener_spec_service_type.lower() == "loadbalancer":
                    check_manager.set_target_conditions(
                        target_name=target_listener_service,
                        conditions=["status", "len(status.loadBalancer.ingress[*].ip)>=1"],
                    )
                    ingress_rules_desc = "- Expecting [bright_blue]>=1[/bright_blue] ingress rule. {}"

                    service_status = associated_service.get("status", {})
                    load_balancer = service_status.get("loadBalancer", {})
                    ingress_rules: List[dict] = load_balancer.get("ingress", [])

                    if not ingress_rules:
                        listener_service_eval_status = CheckTaskStatus.warning.value
                        ingress_count_colored = "[red]Detected 0[/red]."
                    else:
                        ingress_count_colored = f"[green]Detected {len(ingress_rules)}[/green]."

                    check_manager.add_display(
                        target_name=target_listener_service,
                        display=Padding(ingress_rules_desc.format(ingress_count_colored), (0, 0, 0, 12)),
                    )

                    if ingress_rules:
                        check_manager.add_display(
                            target_name=target_listener_service,
                            display=Padding("\nIngress", (0, 0, 0, 12)),
                        )

                    for ingress in ingress_rules:
                        ip = ingress.get("ip")
                        if ip:
                            rule_desc = f"- ip: [green]{ip}[/green]"
                            check_manager.add_display(
                                target_name=target_listener_service,
                                display=Padding(rule_desc, (0, 0, 0, 16)),
                            )
                        else:
                            listener_service_eval_status = CheckTaskStatus.warning.value

                    check_manager.add_target_eval(
                        target_name=target_listener_service, status=listener_service_eval_status, value=service_status
                    )

                if listener_spec_service_type.lower() == "clusterip":
                    check_manager.set_target_conditions(
                        target_name=target_listener_service, conditions=["spec.clusterIP"]
                    )
                    cluster_ip = associated_service.get("spec", {}).get("clusterIP")

                    cluster_ip_desc = "Cluster IP: {}"
                    if not cluster_ip:
                        listener_service_eval_status = CheckTaskStatus.warning.value
                        cluster_ip_desc = cluster_ip_desc.format("[yellow]Undetermined[/yellow]")
                    else:
                        cluster_ip_desc = cluster_ip_desc.format(f"[cyan]{cluster_ip}[/cyan]")

                    check_manager.add_display(
                        target_name=target_listener_service,
                        display=Padding(cluster_ip_desc, (0, 0, 0, 12)),
                    )
                    check_manager.add_target_eval(
                        target_name=target_listener_service,
                        status=listener_service_eval_status,
                        value={"spec.clusterIP": cluster_ip},
                    )

                if listener_spec_service_type.lower() == "nodeport":
                    pass

        check_manager.add_target_eval(
            target_name=target_listeners,
            status=listeners_eval_status,
            value=listener_eval_value,
            resource_name=listener_name,
        )

    return check_manager.as_dict(as_list)


def evaluate_brokers(
    namespace: str,
    as_list: bool = False,
):
    check_manager = CheckManager(check_name="evalBrokers", check_desc="Evaluate E4K broker", namespace=namespace)

    target_brokers = "brokers.az-edge.com"
    broker_conditions = ["len(brokers)==1", "status", "spec.mode"]
    check_manager.add_target(target_name=target_brokers, conditions=broker_conditions)

    broker_list: dict = E4K_ACTIVE_API.get_resources(E4kResourceKinds.BROKER, namespace=namespace)
    if not broker_list:
        fetch_brokers_error_text = f"Unable to fetch namespace {E4kResourceKinds.BROKER.value}s."
        check_manager.add_target_eval(
            target_name=target_brokers, status=CheckTaskStatus.error.value, value=fetch_brokers_error_text
        )
        check_manager.add_display(target_name=target_brokers, display=Padding(fetch_brokers_error_text, (0, 0, 0, 8)))
        return check_manager.as_dict(as_list)

    brokers: List[dict] = broker_list.get("items", [])
    brokers_count = len(brokers)
    brokers_count_text = "- Expecting [bright_blue]1[/bright_blue] broker resource per namespace. {}."
    broker_eval_status = CheckTaskStatus.success.value

    if brokers_count == 1:
        brokers_count_text = brokers_count_text.format(f"[green]Detected {brokers_count}[/green]")
    else:
        brokers_count_text = brokers_count_text.format(f"[red]Detected {brokers_count}[/red]")
        check_manager.set_target_status(target_name=target_brokers, status=CheckTaskStatus.error.value)
    check_manager.add_display(target_name=target_brokers, display=Padding(brokers_count_text, (0, 0, 0, 8)))

    added_distributed_conditions = False
    for b in brokers:
        broker_name = b["metadata"]["name"]
        broker_spec: dict = b["spec"]
        broker_diagnostics = broker_spec["diagnostics"]
        broker_mode = broker_spec.get("mode")
        broker_status_state = b.get("status", {})
        broker_status = broker_status_state.get("status", "N/A")
        broker_status_desc = broker_status_state.get("statusDescription")

        status_display_text = f"Status {{{_decorate_resource_status(broker_status)}}}."

        if broker_status_state:
            status_display_text = f"{status_display_text} {broker_status_desc}."

        target_broker_text = (
            f"\n- Broker {{[bright_blue]{broker_name}[/bright_blue]}} mode [bright_blue]{broker_mode}[/bright_blue]."
        )
        check_manager.add_display(target_name=target_brokers, display=Padding(target_broker_text, (0, 0, 0, 8)))

        broker_eval_value = {"status": {"status": broker_status, "statusDescription": broker_status_desc}}
        broker_eval_status = CheckTaskStatus.success.value

        if broker_status in [ResourceState.error.value, ResourceState.failed.value]:
            broker_eval_status = CheckTaskStatus.error.value
        elif broker_status in [
            ResourceState.recovering.value,
            ResourceState.warn.value,
            ResourceState.starting.value,
            "N/A",
        ]:
            broker_eval_status = CheckTaskStatus.warning.value
        check_manager.add_display(target_name=target_brokers, display=Padding(status_display_text, (0, 0, 0, 12)))

        if broker_mode == "distributed":
            if not added_distributed_conditions:
                # TODO - conditional evaluations
                broker_conditions.append("spec.cardinality")
                broker_conditions.append("spec.cardinality.backendChain.partitions>=1")
                broker_conditions.append("spec.cardinality.backendChain.replicas>=1")
                broker_conditions.append("spec.cardinality.frontend.replicas>=1")
                added_distributed_conditions = True

            check_manager.set_target_conditions(target_name=target_brokers, conditions=broker_conditions)
            check_manager.add_display(target_name=target_brokers, display=Padding("\nCardinality", (0, 0, 0, 12)))
            broker_cardinality: dict = broker_spec.get("cardinality")
            broker_eval_value["spec.cardinality"] = broker_cardinality
            broker_eval_value["spec.mode"] = broker_mode
            if not broker_cardinality:
                broker_eval_status = CheckTaskStatus.error.value
                check_manager.add_display(
                    target_name=target_brokers,
                    display=Padding("[magenta]spec.cardinality is undefined![/magenta]", (0, 0, 0, 16)),
                )
            else:
                backend_cardinality_desc = "- Expecting backend partitions [bright_blue]>=1[/bright_blue]. {}"
                backend_replicas_desc = "- Expecting backend replicas [bright_blue]>=1[/bright_blue]. {}"
                backend_workers_desc = "- Expecting backend workers [bright_blue]>=1[/bright_blue]. {}"

                backend_chain = broker_cardinality.get("backendChain", {})
                backend_partition_count: Optional[int] = backend_chain.get("partitions")
                backend_replicas: Optional[int] = backend_chain.get("replicas")
                backend_workers: Optional[int] = backend_chain.get("workers")

                if backend_partition_count and backend_partition_count >= 1:
                    backend_chain_count_colored = f"[green]Actual {backend_partition_count}[/green]."
                else:
                    backend_chain_count_colored = f"[red]Actual {backend_partition_count}[/red]."
                    broker_eval_status = CheckTaskStatus.error.value

                if backend_replicas and backend_replicas >= 1:
                    backend_replicas_colored = f"[green]Actual {backend_replicas}[/green]."
                else:
                    backend_replicas_colored = f"[red]Actual {backend_replicas}[/red]."
                    broker_eval_status = CheckTaskStatus.error.value

                if backend_workers and backend_workers >= 1:
                    backend_workers_colored = f"[green]Actual {backend_workers}[/green]."
                else:
                    backend_workers_colored = f"[red]Actual {backend_workers}[/red]."
                    broker_eval_status = CheckTaskStatus.error.value

                check_manager.add_display(
                    target_name=target_brokers,
                    display=Padding(
                        backend_cardinality_desc.format(backend_chain_count_colored),
                        (0, 0, 0, 16),
                    ),
                )
                check_manager.add_display(
                    target_name=target_brokers,
                    display=Padding(
                        backend_replicas_desc.format(backend_replicas_colored),
                        (0, 0, 0, 16),
                    ),
                )
                check_manager.add_display(
                    target_name=target_brokers,
                    display=Padding(
                        backend_workers_desc.format(backend_workers_colored),
                        (0, 0, 0, 16),
                    ),
                )

                frontend_cardinality_desc = "- Expecting frontend replicas [bright_blue]>=1[/bright_blue]. {}"
                frontend_replicas: Optional[int] = broker_cardinality.get("frontend", {}).get("replicas")

                if frontend_replicas and frontend_replicas >= 1:
                    frontend_replicas_colored = f"[green]Actual {frontend_replicas}[/green]."
                else:
                    frontend_replicas_colored = f"[red]Actual {frontend_replicas}[/red]."

                check_manager.add_display(
                    target_name=target_brokers,
                    display=Padding(frontend_cardinality_desc.format(frontend_replicas_colored), (0, 0, 0, 16)),
                )

        if broker_diagnostics:
            diagnostic_detail_padding = (0, 0, 0, 16)
            check_manager.add_display(
                target_name=target_brokers,
                display=Padding("\nBroker Diagnostics", (0, 0, 0, 12))
            )
            diag_endpoint = broker_diagnostics.get("diagnosticServiceEndpoint")
            diag_enable_metrics = broker_diagnostics.get("enableMetrics")
            diag_enable_selfcheck = broker_diagnostics.get("enableSelfCheck")
            diag_enable_tracing = broker_diagnostics.get("enableTracing")
            diag_loglevel = broker_diagnostics.get("logLevel")

            check_manager.add_display(
                target_name=target_brokers,
                display=Padding(
                    f"Diagnostic Service Endpoint: [cyan]{diag_endpoint}[/cyan]",
                    diagnostic_detail_padding,
                ),
            )
            check_manager.add_display(
                target_name=target_brokers,
                display=Padding(f"Enable Metrics: [bright_blue]{diag_enable_metrics}[/bright_blue]", diagnostic_detail_padding),
            )
            check_manager.add_display(
                target_name=target_brokers,
                display=Padding(
                    f"Enable Self-Check: [bright_blue]{diag_enable_selfcheck}[/bright_blue]", diagnostic_detail_padding
                ),
            )
            check_manager.add_display(
                target_name=target_brokers,
                display=Padding(f"Enable Tracing: [bright_blue]{diag_enable_tracing}[/bright_blue]", diagnostic_detail_padding),
            )
            check_manager.add_display(
                target_name=target_brokers,
                display=Padding(f"Log Level: [cyan]{diag_loglevel}[/cyan]", diagnostic_detail_padding),
            )
        else:
            check_manager.add_target_eval(
                target_name=target_brokers,
                status=CheckTaskStatus.warning.value,
                value=None,
            )
            check_manager.add_display(
                target_name=target_brokers,
                display=Padding(
                    "[yellow]Unable to fetch broker diagnostics.[/yellow]",
                    diagnostic_detail_padding,
                ),
            )

        check_manager.add_target_eval(
            target_name=target_brokers, status=broker_eval_status, value=broker_eval_value, resource_name=broker_name
        )

    if brokers_count > 0:
        check_manager.add_display(
            target_name=target_brokers,
            display=Padding(
                "\nRuntime Health",
                (0, 0, 0, 8),
            ),
        )

        evaluate_pod_health(
            check_manager=check_manager, namespace=namespace, pod=AZEDGE_DIAGNOSTICS_PROBE_PREFIX, display_padding=12, service_label=E4K_LABEL
        )
        evaluate_pod_health(
            check_manager=check_manager, namespace=namespace, pod=AZEDGE_FRONTEND_PREFIX, display_padding=12, service_label=E4K_LABEL
        )
        evaluate_pod_health(
            check_manager=check_manager, namespace=namespace, pod=AZEDGE_BACKEND_PREFIX, display_padding=12, service_label=E4K_LABEL
        )
        evaluate_pod_health(
            check_manager=check_manager, namespace=namespace, pod=AZEDGE_AUTH_PREFIX, display_padding=12, service_label=E4K_LABEL
        )

    return check_manager.as_dict(as_list)


def evaluate_instances(
    namespace: str,
    as_list: bool = False,
):
    check_manager = CheckManager(check_name="evalInstances", check_desc="Evaluate Bluefin instance", namespace=namespace)

    target_instances = "instances.bluefin.az-bluefin.com"
    instance_conditions = ["len(instances)==1", "provisioningState"]
    check_manager.add_target(target_name=target_instances, conditions=instance_conditions)

    instance_list: dict = BLUEFIN_API_V1.get_resources(BluefinResourceKinds.INSTANCE, namespace=namespace)
    if not instance_list:
        fetch_instances_error_text = f"Unable to fetch namespace {BluefinResourceKinds.INSTANCE.value}s."
        check_manager.add_target_eval(
            target_name=target_instances, status=CheckTaskStatus.error.value, value=fetch_instances_error_text
        )
        check_manager.add_display(target_name=target_instances, display=Padding(fetch_instances_error_text, (0, 0, 0, 8)))
        return check_manager.as_dict(as_list)

    instances: List[dict] = instance_list.get("items", [])
    instances_count = len(instances)
    instances_count_text = "- Expecting [bright_blue]1[/bright_blue] instance resource per namespace. {}."
    instance_eval_status = CheckTaskStatus.success.value

    if instances_count == 1:
        instances_count_text = instances_count_text.format(f"[green]Detected {instances_count}[/green]")
    else:
        instances_count_text = instances_count_text.format(f"[red]Detected {instances_count}[/red]")
        check_manager.set_target_status(target_name=target_instances, status=CheckTaskStatus.error.value)
    check_manager.add_display(target_name=target_instances, display=Padding(instances_count_text, (0, 0, 0, 8)))

    for i in instances:
        instance_name = i["metadata"]["name"]
        instance_status = i["status"]["provisioningStatus"]["status"]

        target_instance_text = (
            f"\n- Instance {{[bright_blue]{instance_name}[/bright_blue]}} provisioning status {{{_decorate_resource_status(instance_status)}}}."
        )
        check_manager.add_display(target_name=target_instances, display=Padding(target_instance_text, (0, 0, 0, 8)))

        instance_eval_value = {"provisioningState": instance_status}
        instance_eval_status = CheckTaskStatus.success.value

        if instance_status in [ProvisioningState.canceled.value, ProvisioningState.failed.value]:
            instance_eval_status = CheckTaskStatus.error.value
            error_message = i["status"]["provisioningStatus"]["error"]["message"]
            error_display_text = f"[red]Error: {error_message}[/red]"
            check_manager.add_display(target_name=target_instances, display=Padding(error_display_text, (0, 0, 0, 10)))
        elif instance_status in [
                ProvisioningState.updating.value,
                ProvisioningState.provisioning.value,
                ProvisioningState.deleting.value,
                ProvisioningState.accepted.value
            ]:
            instance_eval_status = CheckTaskStatus.warning.value

        check_manager.add_target_eval(
            target_name=target_instances, status=instance_eval_status, value=instance_eval_value, resource_name=instance_name
        )

    if instances_count > 0:
        check_manager.add_display(
            target_name=target_instances,
            display=Padding(
                "\nRuntime Health",
                (0, 0, 0, 8),
            ),
        )

        from .support.bluefin import BLUEFIN_APP_LABEL

        evaluate_pod_health(
            check_manager=check_manager, namespace=namespace, pod=BLUEFIN_READER_WORKER_PREFIX, display_padding=12, service_label=BLUEFIN_APP_LABEL
        )
        evaluate_pod_health(
            check_manager=check_manager, namespace=namespace, pod=BLUEFIN_RUNNER_WORKER_PREFIX, display_padding=12, service_label=BLUEFIN_APP_LABEL
        )
        evaluate_pod_health(
            check_manager=check_manager, namespace=namespace, pod=BLUEFIN_REFDATA_STORE_PREFIX, display_padding=12, service_label=BLUEFIN_APP_LABEL
        )
        evaluate_pod_health(
            check_manager=check_manager, namespace=namespace, pod=BLUEFIN_NATS_PREFIX, display_padding=12, service_label=BLUEFIN_APP_LABEL
        )
        evaluate_pod_health(
            check_manager=check_manager, namespace=namespace, pod=BLUEFIN_OPERATOR_CONTROLLER_MANAGER, display_padding=12, service_label=BLUEFIN_APP_LABEL
        )

    return check_manager.as_dict(as_list)


def evaluate_pipelines(
    namespace: str,
    as_list: bool = False,
    extended: Optional[bool] = False,
):
    check_manager = CheckManager(check_name="evalPipelines", check_desc="Evaluate Bluefin pipeline", namespace=namespace)

    target_pipelines = "pipelines.bluefin.az-bluefin.com"
    pipeline_conditions = ["len(pipelines)>=1",
                           "mode.enabled",
                           "provisioningStatus",
                           "sourceNodeCount == 1",
                           "spec.input.broker",
                           "len(spec.input.topics)>=1",
                           "spec.input.format.type"
                           "spec.input.partitionCount>=1",
                           "intermediateStagesCount>=1",
                           "destinationNodeCount==1"]
    check_manager.add_target(target_name=target_pipelines, conditions=pipeline_conditions)

    pipeline_list: dict = BLUEFIN_API_V1.get_resources(BluefinResourceKinds.PIPELINE, namespace=namespace)
    if not pipeline_list:
        fetch_pipelines_error_text = f"Unable to fetch namespace {BluefinResourceKinds.PIPELINE.value}s."
        check_manager.add_target_eval(
            target_name=target_pipelines, status=CheckTaskStatus.error.value, value=fetch_pipelines_error_text
        )
        check_manager.add_display(target_name=target_pipelines, display=Padding(fetch_pipelines_error_text, (0, 0, 0, 8)))
        return check_manager.as_dict(as_list)

    pipelines: List[dict] = pipeline_list.get("items", [])
    pipelines_count = len(pipelines)
    pipelines_count_text = "- Expecting [bright_blue]>=1[/bright_blue] pipeline resource per namespace. {}."
    pipeline_eval_status = CheckTaskStatus.success.value

    if pipelines_count >= 1:
        pipelines_count_text = pipelines_count_text.format(f"[green]Detected {pipelines_count}[/green]")
    else:
        pipelines_count_text = pipelines_count_text.format(f"[red]Detected {pipelines_count}[/red]")
        check_manager.set_target_status(target_name=target_pipelines, status=CheckTaskStatus.error.value)
    check_manager.add_display(target_name=target_pipelines, display=Padding(pipelines_count_text, (0, 0, 0, 8)))

    for p in pipelines:
        pipeline_name = p["metadata"]["name"]
        pipeline_running_status = "running" if p["spec"]["enabled"] else "not running"

        pipeline_enabled_text = f"\n- Pipeline {{[bright_blue]{pipeline_name}[/bright_blue]}} is {{[bright_blue]{pipeline_running_status}[/bright_blue]}}."
        pipeline_eval_value = {"mode.enabled": pipeline_running_status}
        pipeline_eval_status = CheckTaskStatus.success.value

        if pipeline_running_status == "not running":
            check_manager.add_target_eval(target_name=target_pipelines, status=CheckTaskStatus.skipped.value, resource_name=pipeline_name)
            pipieline_not_enabled_text = (
                f"\n- Pipeline {{[bright_blue]{pipeline_name}[/bright_blue]}} is {{[yellow]not running[/yellow]}}."
                "\n  [bright_white]Skipping pipeline evaluation[/bright_white]."
            )
            check_manager.add_display(target_name=target_pipelines, display=Padding(pipieline_not_enabled_text, (0, 0, 0, 8)))
            continue
        check_manager.add_display(target_name=target_pipelines, display=Padding(pipeline_enabled_text, (0, 0, 0, 8)))

        check_manager.add_target_eval(
            target_name=target_pipelines, status=pipeline_eval_status, value=pipeline_eval_value, resource_name=pipeline_name
        )

        # check provisioning status
        pipeline_status = p["status"]["provisioningStatus"]["status"]
        status_display_text = f"- Provisioning status {{{_decorate_resource_status(pipeline_status)}}}."
        check_manager.add_display(target_name=target_pipelines, display=Padding(status_display_text, (0, 0, 0, 12)))

        pipeline_eval_value = {"provisioningStatus": pipeline_status}
        pipeline_eval_status = CheckTaskStatus.success.value

        if pipeline_status in [ProvisioningState.canceled.value, ProvisioningState.failed.value]:
            pipeline_eval_status = CheckTaskStatus.error.value
            error_message = p["status"]["provisioningStatus"]["error"]["message"]
            error_display_text = f"[red]Error: {error_message}[/red]"
            check_manager.add_display(target_name=target_pipelines, display=Padding(error_display_text, (0, 0, 0, 14)))
        elif pipeline_status in [
                ProvisioningState.updating.value,
                ProvisioningState.provisioning.value,
                ProvisioningState.deleting.value,
                ProvisioningState.accepted.value
            ]:
            pipeline_eval_status = CheckTaskStatus.warning.value

        check_manager.add_target_eval(
            target_name=target_pipelines, status=pipeline_eval_status, value=pipeline_eval_value, resource_name=pipeline_name
        )

        # check data source node count
        pipeline_source_node = p["spec"]["input"]
        pipeline_source_node_count = 1 if pipeline_source_node else 0
        source_count_display_text = f"- Expecting [bright_blue]1[/bright_blue] MQTT data source node. [green]Detected {pipeline_source_node_count}[/green]."

        pipeline_source_count_eval_value = {"sourceNodeCount": pipeline_source_node_count}
        pipeline_source_count_eval_status = CheckTaskStatus.success.value

        if pipeline_source_node_count != 1:
            pipeline_source_count_eval_status = CheckTaskStatus.error.value
            source_count_display_text = f"- Expecting [bright_blue]1[/bright_blue] MQTT data source node. {{[red]Detected {pipeline_source_node_count}[/red]}}."
        check_manager.add_display(target_name=target_pipelines, display=Padding(source_count_display_text, (0, 0, 0, 12)))

        check_manager.add_target_eval(
            target_name=target_pipelines, status=pipeline_source_count_eval_status, value=pipeline_source_count_eval_value, resource_name=pipeline_name
        )

        # check data source broker URL
        pipeline_source_node_broker = pipeline_source_node["broker"]
        source_broker_display_text = f"- Broker URL: {pipeline_source_node_broker}"

        pipeline_source_broker_eval_value = {"spec.input.broker": pipeline_source_node_broker}
        pipeline_source_broker_eval_status = CheckTaskStatus.success.value

        if not pipeline_source_node_broker:
            pipeline_source_broker_eval_status = CheckTaskStatus.error.value
        check_manager.add_display(target_name=target_pipelines, display=Padding(source_broker_display_text, (0, 0, 0, 16)))

        check_manager.add_target_eval(
            target_name=target_pipelines, status=pipeline_source_broker_eval_status, value=pipeline_source_broker_eval_value, resource_name=pipeline_name
        )

        # check data source topics
        pipeline_source_node_topics = pipeline_source_node["topics"]
        pipeline_source_node_topics_count = len(pipeline_source_node_topics)
        source_topics_display_text = f"- Expecting [bright_blue]>=1[/bright_blue] and [bright_blue]<=50[/bright_blue] topics. [green]Detected {pipeline_source_node_topics_count}[/green]."

        pipeline_source_topics_eval_value = {"spec.input.topics": pipeline_source_node["topics"]}
        pipeline_source_topics_eval_status = CheckTaskStatus.success.value

        if pipeline_source_node_topics_count < 1 or pipeline_source_node_topics_count > 50:
            pipeline_source_topics_eval_status = CheckTaskStatus.error.value
        check_manager.add_display(target_name=target_pipelines, display=Padding(source_topics_display_text, (0, 0, 0, 16)))

        if extended:
            for topic in pipeline_source_node_topics:
                topic_display_text = f"Topic {{[bright_blue]{topic}[/bright_blue]}} detected."
                check_manager.add_display(target_name=target_pipelines, display=Padding(topic_display_text, (0, 0, 0, 18)))

        check_manager.add_target_eval(
            target_name=target_pipelines, status=pipeline_source_topics_eval_status, value=pipeline_source_topics_eval_value, resource_name=pipeline_name
        )

        # data source message format type
        pipeline_source_node_format_type = pipeline_source_node["format"]["type"]
        source_format_type_display_text = f"- Source message type: [bright_blue]{pipeline_source_node_format_type}[/bright_blue]"

        check_manager.add_display(target_name=target_pipelines, display=Padding(source_format_type_display_text, (0, 0, 0, 16)))

        check_manager.add_target_eval(
            target_name=target_pipelines, status=pipeline_source_topics_eval_status, value=pipeline_source_topics_eval_value, resource_name=pipeline_name
        )

        # check data source partition
        pipeline_source_node_partition_count = pipeline_source_node["partitionCount"]
        pipeline_source_node_partition_strategy = pipeline_source_node["partitionStrategy"]["type"]
        source_partition_count_display_text = f"- Expecting the number of partition [bright_blue]>=1[/bright_blue] and [bright_blue]<=100[/bright_blue]. [green]Detected {pipeline_source_node_partition_count}[/green]."
        source_partition_strategy_display_text = f"The type of partitioning strategy is {{[bright_blue]{pipeline_source_node_partition_strategy}[/bright_blue]}}."

        pipeline_source_partition_eval_value = {"spec.input.partitionCount": pipeline_source_node_partition_count}
        pipeline_source_partition_eval_status = CheckTaskStatus.success.value

        if pipeline_source_node_partition_count < 1 or pipeline_source_node_partition_count > 100:
            pipeline_source_partition_eval_status = CheckTaskStatus.error.value
        check_manager.add_display(target_name=target_pipelines, display=Padding(source_partition_count_display_text, (0, 0, 0, 16)))
        check_manager.add_display(target_name=target_pipelines, display=Padding(source_partition_strategy_display_text, (0, 0, 0, 18)))

        check_manager.add_target_eval(
            target_name=target_pipelines, status=pipeline_source_partition_eval_status, value=pipeline_source_partition_eval_value, resource_name=pipeline_name
        )

        if extended:
            # data source qos
            pipeline_source_node_qos = pipeline_source_node["qos"]
            source_qos_display_text = f"- QoS: [bright_blue]{pipeline_source_node_qos}[/bright_blue]"
            check_manager.add_display(target_name=target_pipelines, display=Padding(source_qos_display_text, (0, 0, 0, 16)))

            # data source authentication
            pipeline_source_node_authentication = pipeline_source_node["authentication"]["type"]
            source_authentication_display_text = f"- Authentication type: [bright_blue]{pipeline_source_node_authentication}[/bright_blue]"
            check_manager.add_display(target_name=target_pipelines, display=Padding(source_authentication_display_text, (0, 0, 0, 16)))

        # check pipeline intermediate node
        pipeline_stages_node = p["spec"]["stages"]
        output_node: Tuple = ()
        for s in pipeline_stages_node:
            if "output" in pipeline_stages_node[s]["type"]:
                output_node = (s, pipeline_stages_node[s])
                break
        # number of intermediate stages should be total len(stages) - len(output stage)
        # pipeline_intermediate_stages_node is pipeline_stages_node removing output stage node
        pipeline_intermediate_stages_node = pipeline_stages_node.copy()
        pipeline_intermediate_stages_node_count = len(pipeline_stages_node)
        if output_node:
            pipeline_intermediate_stages_node.pop(output_node[0])
            pipeline_intermediate_stages_node_count -= 1
        stage_count_display_text = f"- Expecting [bright_blue]>=1[/bright_blue] intermediate stages. [green]Detected {pipeline_intermediate_stages_node_count}[/green]."

        pipeline_stage_eval_value = {"intermediateStagesCount": pipeline_intermediate_stages_node_count}
        pipeline_stage_eval_status = CheckTaskStatus.success.value

        if pipeline_intermediate_stages_node_count < 1:
            pipeline_stage_eval_status = CheckTaskStatus.error.value
        check_manager.add_display(target_name=target_pipelines, display=Padding(stage_count_display_text, (0, 0, 0, 12)))

        check_manager.add_target_eval(
            target_name=target_pipelines, status=pipeline_stage_eval_status, value=pipeline_stage_eval_value, resource_name=pipeline_name
        )

        if extended:
            for s in pipeline_intermediate_stages_node:
                stage_name = s
                stage_type = pipeline_intermediate_stages_node[s]["type"]
                stage_display_text = f"- Stage resource {{[bright_blue]{stage_name}[/bright_blue]}} of type {{[bright_blue]{stage_type}[/bright_blue]}}"
                check_manager.add_display(target_name=target_pipelines, display=Padding(stage_display_text, (0, 0, 0, 16)))

                for key, value in pipeline_intermediate_stages_node[s].items():
                    property_display_text = f"Property [bright_blue]{key}[/bright_blue] : [bright_blue]{value}[/bright_blue]"
                    check_manager.add_display(target_name=target_pipelines, display=Padding(property_display_text, (0, 0, 0, 20)))

        # check pipeline destination node
        pipeline_destination_node_count = 0
        if output_node:
            pipeline_destination_node_count = 1
        destination_count_display_text = f"- Expecting [bright_blue]1[/bright_blue] data destination node. [green]Detected {pipeline_destination_node_count}[/green]."

        pipeline_destination_eval_value = {"destinationNodeCount": pipeline_destination_node_count}
        pipeline_destination_eval_status = CheckTaskStatus.success.value

        if pipeline_destination_node_count != 1:
            pipeline_destination_eval_status = CheckTaskStatus.error.value
        check_manager.add_display(target_name=target_pipelines, display=Padding(destination_count_display_text, (0, 0, 0, 12)))

        check_manager.add_target_eval(
            target_name=target_pipelines, status=pipeline_destination_eval_status, value=pipeline_destination_eval_value, resource_name=pipeline_name
        )

        if output_node:
            if extended:
                for key, value in output_node[1].items():
                    property_display_text = f"Property [bright_blue]{key}[/bright_blue] : [bright_blue]{value}[/bright_blue]"
                    check_manager.add_display(target_name=target_pipelines, display=Padding(property_display_text, (0, 0, 0, 16)))
            else:
                # check pipeline destination type
                pipeline_destination_type = output_node[1]["type"]
                destination_type_display_text = f"- Message destination type {{[bright_blue]{pipeline_destination_type}[/bright_blue]}} detected"
                check_manager.add_display(target_name=target_pipelines, display=Padding(destination_type_display_text, (0, 0, 0, 16)))

                # check pipeline destination target endpoint
                pipeline_destination_target = _get_destination_target_endpoint(output_node)
                destination_target_display_text = f"- Target endpoint: [bright_blue]{pipeline_destination_target}[/bright_blue]"
                check_manager.add_display(target_name=target_pipelines, display=Padding(destination_target_display_text, (0, 0, 0, 16)))

    return check_manager.as_dict(as_list)


def evaluate_datasets(
    namespace: str,
    as_list: bool = False,
    extended: Optional[bool] = False,
):
    check_manager = CheckManager(check_name="evalDatasets", check_desc="Evaluate Bluefin dataset", namespace=namespace)

    target_datasets = "datasets.bluefin.az-bluefin.com"
    dataset_conditions = ["provisioningState"]
    check_manager.add_target(target_name=target_datasets, conditions=dataset_conditions)

    dataset_list: dict = BLUEFIN_API_V1.get_resources(BluefinResourceKinds.DATASET, namespace=namespace)
    datasets: List[dict] = dataset_list.get("items", [])
    datasets_count = len(datasets)

    datasets_count_text = "- Checking dataset resource in namespace. {}."
    dataset_eval_status = CheckTaskStatus.success.value

    if datasets_count > 0:
        datasets_count_text = datasets_count_text.format(f"[green]Detected {datasets_count}[/green]")
    else:
        check_manager.add_target_eval(target_name=target_datasets, status=CheckTaskStatus.skipped.value)
        no_dataset_text = (
            "Datasets [yellow]not[/yellow] detected."
            "\n[bright_white]Skipping dataset evaluation[/bright_white]."
        )
        check_manager.add_display(target_name=target_datasets, display=Padding(no_dataset_text, (0, 0, 0, 8)))
        return check_manager.as_dict(as_list)
    check_manager.add_display(target_name=target_datasets, display=Padding(datasets_count_text, (0, 0, 0, 8)))

    for d in datasets:
        dataset_name = d["metadata"]["name"]
        dataset_status = d["status"]["provisioningStatus"]["status"]

        status_display_text = f"Provisiong Status: {{{_decorate_resource_status(dataset_status)}}}"

        target_dataset_text = (
            f"\n- Dataset resource {{[bright_blue]{dataset_name}[/bright_blue]}}"
        )
        check_manager.add_display(target_name=target_datasets, display=Padding(target_dataset_text, (0, 0, 0, 8)))
        check_manager.add_display(target_name=target_datasets, display=Padding(status_display_text, (0, 0, 0, 12)))

        dataset_eval_value = {"provisioningState": dataset_status}
        dataset_eval_status = CheckTaskStatus.success.value

        if dataset_status in [ProvisioningState.canceled.value, ProvisioningState.failed.value]:
            dataset_eval_status = CheckTaskStatus.error.value
            error_message = d["status"]["provisioningStatus"]["error"]["message"]
            error_display_text = f"[red]Error: {error_message}[/red]"
            check_manager.add_display(target_name=target_datasets, display=Padding(error_display_text, (0, 0, 0, 14)))
        elif dataset_status in [
                ProvisioningState.updating.value,
                ProvisioningState.provisioning.value,
                ProvisioningState.deleting.value,
                ProvisioningState.accepted.value
            ]:
            dataset_eval_status = CheckTaskStatus.warning.value

        check_manager.add_target_eval(
            target_name=target_datasets, status=dataset_eval_status, value=dataset_eval_value, resource_name=dataset_name
        )

        if extended:
            dataset_spec: dict = d["spec"]
            import pdb; pdb.set_trace()
            dataset_payload = dataset_spec.get("payload", "")
            if dataset_payload:
                check_manager.add_display(
                    target_name=target_datasets,
                    display=Padding(
                        f"Payload path: [cyan]{dataset_payload}[/cyan]",
                        (0, 0, 0, 12),
                    ),
                )

            dataset_timestamp = dataset_spec.get("timestamp", "")
            if dataset_timestamp:
                check_manager.add_display(
                    target_name=target_datasets,
                    display=Padding(
                        f"Timestamp: [cyan]{dataset_timestamp}[/cyan]",
                        (0, 0, 0, 12),
                    ),
                )

            dataset_ttl = dataset_spec.get("ttl", "")
            if dataset_ttl:
                check_manager.add_display(
                    target_name=target_datasets,
                    display=Padding(
                        f"Expiration time: [cyan]{dataset_ttl}[/cyan]",
                        (0, 0, 0, 12),
                    ),
                )

            dataset_keys = dataset_spec.get("keys", {})
            if dataset_keys:
                check_manager.add_display(
                    target_name=target_datasets,
                    display=Padding(
                        "Configuration keys:",
                        (0, 0, 0, 12),
                    ),
                )

                for key in dataset_keys:
                    check_manager.add_display(
                        target_name=target_datasets,
                        display=Padding(
                            f"Key {{[cyan]{key}[/cyan]}} detected",
                            (0, 0, 0, 16),
                        ),
                    )

            
    return check_manager.as_dict(as_list)


# def enumerate_e4k_resources(
#     as_list: bool = False,
# ) -> Tuple[dict, dict]:
#     resource_kind_map = {}
#     target_api = E4K_ACTIVE_API.as_str()
#     check_manager = CheckManager(check_name="enumerateE4kApi", check_desc="Enumerate E4K API resources")
#     check_manager.add_target(target_name=target_api)

#     api_resources: V1APIResourceList = get_cluster_custom_api(group=E4K_ACTIVE_API.group, version=E4K_ACTIVE_API.version)

#     if not api_resources:
#         check_manager.add_target_eval(target_name=target_api, status=CheckTaskStatus.skipped.value)
#         missing_api_text = (
#             f"[bright_blue]{target_api}[/bright_blue] API resources [red]not[/red] detected."
#             "\n\n[bright_white]Skipping deployment evaluation[/bright_white]."
#         )
#         check_manager.add_display(target_name=target_api, display=Padding(missing_api_text, (0, 0, 0, 8)))
#         return check_manager.as_dict(as_list), resource_kind_map

#     api_header_display = Padding(f"[bright_blue]{target_api}[/bright_blue] API resources", (0, 0, 0, 8))
#     check_manager.add_display(target_name=target_api, display=api_header_display)
#     for resource in api_resources.resources:
#         r: V1APIResource = resource
#         if r.kind not in resource_kind_map:
#             resource_kind_map[r.kind] = True
#             check_manager.add_display(target_name=target_api, display=Padding(f"[cyan]{r.kind}[/cyan]", (0, 0, 0, 12)))

#     check_manager.add_target_eval(
#         target_name=target_api, status=CheckTaskStatus.success.value, value=list(resource_kind_map.keys())
#     )
#     return check_manager.as_dict(as_list), resource_kind_map


def enumerate_edge_service_resources(
    api_group: str,
    api_version: str,
    check_name: str,
    check_desc: str,
    target_api: str,
    as_list: bool = False,
) -> Tuple[dict, dict]:
    resource_kind_map = {}
    check_manager = CheckManager(check_name, check_desc)
    check_manager.add_target(target_name=target_api)

    api_resources: V1APIResourceList = get_cluster_custom_api(group=api_group, version=api_version)

    if not api_resources:
        check_manager.add_target_eval(target_name=target_api, status=CheckTaskStatus.skipped.value)
        missing_api_text = (
            f"[bright_blue]{target_api}[/bright_blue] API resources [red]not[/red] detected."
            "\n\n[bright_white]Skipping deployment evaluation[/bright_white]."
        )
        check_manager.add_display(target_name=target_api, display=Padding(missing_api_text, (0, 0, 0, 8)))
        return check_manager.as_dict(as_list), resource_kind_map

    api_header_display = Padding(f"[bright_blue]{target_api}[/bright_blue] API resources", (0, 0, 0, 8))
    check_manager.add_display(target_name=target_api, display=api_header_display)
    for resource in api_resources.resources:
        r: V1APIResource = resource
        if r.kind not in resource_kind_map:
            resource_kind_map[r.kind] = True
            check_manager.add_display(target_name=target_api, display=Padding(f"[cyan]{r.kind}[/cyan]", (0, 0, 0, 12)))

    check_manager.add_target_eval(
        target_name=target_api, status=CheckTaskStatus.success.value, value=list(resource_kind_map.keys())
    )
    return check_manager.as_dict(as_list), resource_kind_map


def check_k8s_version(as_list: bool = False):
    from kubernetes.client.models import VersionInfo
    from packaging import version

    from ..common import MIN_K8S_VERSION

    version_client = client.VersionApi()

    target_k8s_version = "k8s"
    check_manager = CheckManager(check_name="evalK8sVers", check_desc="Evaluate Kubernetes server")
    check_manager.add_target(
        target_name=target_k8s_version,
        conditions=[f"(k8s version)>={MIN_K8S_VERSION}"],
    )

    try:
        version_details: VersionInfo = version_client.get_code()
    except ApiException as ae:
        logger.debug(str(ae))
        api_error_text = "Unable to determine. Is there connectivity to the cluster?"
        check_manager.add_target_eval(
            target_name=target_k8s_version, status=CheckTaskStatus.error.value, value=api_error_text
        )
        check_manager.add_display(target_name=target_k8s_version, display=Padding(api_error_text, (0, 0, 0, 8)))
    else:
        major_version = version_details.major
        minor_version = version_details.minor
        semver = f"{major_version}.{minor_version}"

        if version.parse(semver) >= version.parse(MIN_K8S_VERSION):
            semver_status = CheckTaskStatus.success.value
            semver_colored = f"[green]v{semver}[/green]"
        else:
            semver_status = CheckTaskStatus.error.value
            semver_colored = f"[red]v{semver}[/red]"

        k8s_semver_text = (
            f"Require [bright_blue]k8s[/bright_blue] >=[cyan]{MIN_K8S_VERSION}[/cyan] detected {semver_colored}."
        )
        check_manager.add_target_eval(target_name=target_k8s_version, status=semver_status, value=semver)
        check_manager.add_display(target_name=target_k8s_version, display=Padding(k8s_semver_text, (0, 0, 0, 8)))

    return check_manager.as_dict(as_list)


def check_helm_version(as_list: bool = False):
    from shutil import which
    from subprocess import CalledProcessError, run
    from packaging import version

    from ..common import MIN_HELM_VERSION

    check_manager = CheckManager(check_name="evalHelmVers", check_desc="Evaluate helm")
    target_helm_version = "helm"
    check_manager.add_target(
        target_name=target_helm_version,
        conditions=[f"(helm version)>={MIN_HELM_VERSION}"],
    )

    helm_path = which("helm")
    if not helm_path:
        not_found_helm_text = "Unable to determine. Is helm installed and on system path?"
        check_manager.add_target_eval(
            target_name=target_helm_version, status=CheckTaskStatus.error.value, value=not_found_helm_text
        )
        check_manager.add_display(target_name=target_helm_version, display=Padding(not_found_helm_text, (0, 0, 0, 8)))
        return check_manager.as_dict(as_list)

    try:
        completed_process = run(
            [helm_path, "version", '--template="{{.Version}}"'],
            capture_output=True,
            check=True,
        )
    except CalledProcessError:
        process_error_text = "Unable to determine. Error running helm version command."
        check_manager.add_target_eval(
            target_name=target_helm_version, status=CheckTaskStatus.error.value, value=process_error_text
        )
        check_manager.add_display(target_name=target_helm_version, display=Padding(process_error_text, (0, 0, 0, 8)))
        return CheckManager.as_dict(as_list)

    helm_semver = completed_process.stdout.decode("utf-8").replace('"', "")
    if version.parse(helm_semver) >= version.parse(MIN_HELM_VERSION):
        helm_semver_status = CheckTaskStatus.success.value
        helm_semver_colored = f"[green]{helm_semver}[/green]"
    else:
        helm_semver_status = CheckTaskStatus.error.value
        helm_semver_colored = f"[red]{helm_semver}[/red]"
    helm_semver_text = (
        f"Require [bright_blue]helm[/bright_blue] >=[cyan]{MIN_HELM_VERSION}[/cyan] detected {helm_semver_colored}."
    )

    check_manager.add_target_eval(target_name=target_helm_version, status=helm_semver_status, value=helm_semver)
    check_manager.add_display(target_name=target_helm_version, display=Padding(helm_semver_text, (0, 0, 0, 8)))

    return check_manager.as_dict(as_list)


def check_nodes(as_list: bool = False):
    from kubernetes.client.models import V1Node, V1NodeList

    check_manager = CheckManager(check_name="evalClusterNodes", check_desc="Evaluate cluster nodes")
    target_minimum_nodes = "cluster/nodes"
    check_manager.add_target(
        target_name=target_minimum_nodes,
        conditions=["len(cluster/nodes)>=1", "(cluster/nodes).each(node.status.allocatable[memory]>=140MiB)"],
    )

    try:
        core_client = client.CoreV1Api()
        nodes: V1NodeList = core_client.list_node()
    except ApiException as ae:
        logger.debug(str(ae))
        api_error_text = "Unable to fetch nodes. Is there connectivity to the cluster?"
        check_manager.add_target_eval(
            target_name=target_minimum_nodes, status=CheckTaskStatus.error.value, value=api_error_text
        )
        check_manager.add_display(target_name=target_minimum_nodes, display=Padding(api_error_text, (0, 0, 0, 8)))
    else:
        node_items: List[V1Node] = nodes.items
        node_count = len(node_items)
        target_display = "At least 1 node is required. {}"
        if node_count < 1:
            target_display = Padding(target_display.format(f"[red]Detected {node_count}[/red]."), (0, 0, 0, 8))
            check_manager.add_target_eval(target_name=target_minimum_nodes, status=CheckTaskStatus.error.value)
            check_manager.add_display(target_name=target_minimum_nodes, display=target_display)
            return check_manager.as_dict()

        target_display = Padding(target_display.format(f"[green]Detected {node_count}[/green]."), (0, 0, 0, 8))
        check_manager.add_display(target_name=target_minimum_nodes, display=target_display)
        check_manager.add_display(target_name=target_minimum_nodes, display=NewLine())

        for node in node_items:
            node_memory_value = {}
            memory_status = CheckTaskStatus.success.value
            memory: str = node.status.allocatable["memory"]
            memory = memory.replace("Ki", "")
            memory: int = int(int(memory) / 1024)
            mem_colored = f"[green]{memory}[/green]"
            node_name = node.metadata.name
            node_memory_value[node_name] = f"{memory}MiB"

            if memory < 140:
                memory_status = CheckTaskStatus.warning.value
                mem_colored = f"[yellow]{memory}[/yellow]"

            node_memory_display = Padding(f"[bright_blue]{node_name}[/bright_blue] {mem_colored} MiB", (0, 0, 0, 8))
            check_manager.add_target_eval(
                target_name=target_minimum_nodes, status=memory_status, value=node_memory_value
            )
            check_manager.add_display(target_name=target_minimum_nodes, display=node_memory_display)

    return check_manager.as_dict(as_list)


def _decorate_pod_phase(phase: str) -> Tuple[str, str]:
    from ..common import PodState

    if phase == PodState.failed.value:
        return f"[red]{phase}[/red]", CheckTaskStatus.error.value
    if not phase or phase in [PodState.unknown.value, PodState.pending.value]:
        return f"[yellow]{phase}[/yellow]", CheckTaskStatus.warning.value
    return f"[green]{phase}[/green]", CheckTaskStatus.success.value


def _decorate_resource_status(status: str) -> str:
    from ..common import ResourceState

    if status in [ResourceState.failed.value, ResourceState.error.value]:
        return f"[red]{status}[/red]"
    if status in [ResourceState.recovering.value, ResourceState.warn.value, ResourceState.starting.value, "N/A"]:
        return f"[yellow]{status}[/yellow]"
    return f"[green]{status}[/green]"


def _get_valid_references(kind: Union[Enum, str], namespace: str):
    result = {}
    custom_objects = E4K_ACTIVE_API.get_resources(kind=kind, namespace=namespace)
    if custom_objects:
        objects: List[dict] = custom_objects.get("items", [])
        for object in objects:
            o: dict = object
            metadata: dict = o.get("metadata", {})
            name = metadata.get("name")
            if name:
                result[name] = True

    return result


def _get_destination_target_endpoint(output_node: Tuple) -> str:
    target_endpoint = ""

    if "dataexplorer" in output_node[1]["type"]:
        target_endpoint = output_node[1]["clusterUrl"]
    elif "fabric" in output_node[1]["type"] or "http" in output_node[1]["type"]:
        target_endpoint = output_node[1]["url"]
    elif "file" in output_node[1]["type"]:
        target_endpoint = output_node[1]["filePath"]
    elif "grpc" in output_node[1]["type"]:
        target_endpoint = output_node[1]["serverAddress"]
    elif "mqtt" in output_node[1]["type"]:
        target_endpoint = output_node[1]["broker"]
    elif "refdata" in output_node[1]["type"]:
        target_endpoint = output_node[1]["dataset"]

    return target_endpoint
 


class CheckManager:
    """
    {
        "name":"evaluateBrokerListeners",
        "description": "Evaluate E4K broker listeners",
        "namespace": "default,
        "targets": {
            "len(listeners)": {
                "displays": [],
                "conditions": ["==1"],
                "evaluations": [
                    {
                        "name"?: "listeners",
                        "kind"?: "brokerListener
                        "value"?: 2,
                        "status": "warning"
                    }
                ],
                "status": "warning"
            }
        },
        "status": "warning",
    }
    """

    def __init__(self, check_name: str, check_desc: str, namespace: Optional[str] = None):
        self.check_name = check_name
        self.check_desc = check_desc
        self.namespace = namespace
        self.targets = {}
        self.target_displays = {}
        self.worst_status = CheckTaskStatus.success.value

    def add_target(self, target_name: str, conditions: List[str] = None, description: str = None):
        if target_name not in self.targets:
            self.targets[target_name] = {}
        self.targets[target_name]["conditions"] = conditions
        self.targets[target_name]["evaluations"]: List[dict] = []
        self.targets[target_name]["status"] = CheckTaskStatus.success.value
        if description:
            self.targets[target_name]["description"] = description

    def set_target_conditions(self, target_name: str, conditions: List[str]):
        self.targets[target_name]["conditions"] = conditions

    def set_target_status(self, target_name: str, status: str):
        self._process_status(target_name=target_name, status=status)

    def add_target_eval(
        self,
        target_name: str,
        status: str,
        value: Optional[Any] = None,
        resource_name: Optional[str] = None,
        resource_kind: Optional[str] = None,
    ):
        eval_dict = {"status": status}
        if resource_name:
            eval_dict["name"] = resource_name
        if value:
            eval_dict["value"] = value
        if resource_kind:
            eval_dict["kind"] = resource_kind
        self.targets[target_name]["evaluations"].append(eval_dict)
        self._process_status(target_name, status)

    def _process_status(self, target_name: str, status: str):
        existing_status = self.targets[target_name].get("status", CheckTaskStatus.success.value)
        if existing_status != status:
            if existing_status == CheckTaskStatus.success.value and status in [
                CheckTaskStatus.warning.value,
                CheckTaskStatus.error.value,
                CheckTaskStatus.skipped.value,
            ]:
                self.targets[target_name]["status"] = status
                self.worst_status = status
            elif (
                existing_status == CheckTaskStatus.warning.value or existing_status == CheckTaskStatus.skipped.value
            ) and status in [CheckTaskStatus.error.value]:
                self.targets[target_name]["status"] = status
                self.worst_status = status

    def add_display(self, target_name: str, display: Any):
        if target_name not in self.target_displays:
            self.target_displays[target_name] = []
        self.target_displays[target_name].append(display)

    def as_dict(self, as_list: bool = False):
        import copy

        result = {
            "name": self.check_name,
            "namespace": self.namespace,
            "description": self.check_desc,
            "targets": {},
            "status": self.worst_status,
        }
        result["targets"] = copy.deepcopy(self.targets)
        if as_list:
            for t in self.target_displays:
                result["targets"][t]["displays"] = copy.deepcopy(self.target_displays[t])

            if self.namespace:
                result["description"] = f"{result['description']} in namespace {{[cyan]{self.namespace}[/cyan]}}"

        return result


def evaluate_pod_health(check_manager: CheckManager, namespace: str, pod: str, display_padding: int, service_label: str):
    target_service_pod = f"pod/{pod}"
    check_manager.add_target(target_name=target_service_pod, conditions=["status.phase"])
    diagnostics_pods = get_namespaced_pods_by_prefix(prefix=pod, namespace=namespace, label_selector=service_label)
    if not diagnostics_pods:
        check_manager.add_target_eval(target_name=target_service_pod, status=CheckTaskStatus.warning.value, value=None)
        check_manager.add_display(
            target_name=target_service_pod,
            display=Padding(f"{target_service_pod}* [yellow]not detected[/yellow].", (0, 0, 0, display_padding)),
        )
    else:
        for pod in diagnostics_pods:
            pod_dict = pod.to_dict()
            pod_name = pod_dict["metadata"]["name"]
            pod_phase = pod_dict.get("status", {}).get("phase")
            pod_phase_deco, status = _decorate_pod_phase(pod_phase)

            check_manager.add_target_eval(
                target_name=target_service_pod, status=status, value={"name": pod_name, "status.phase": pod_phase}
            )
            check_manager.add_display(
                target_name=target_service_pod,
                display=Padding(
                    f"Pod {{[bright_blue]{pod_name}[/bright_blue]}} in phase {{{pod_phase_deco}}}.",
                    (0, 0, 0, display_padding),
                ),
            )
