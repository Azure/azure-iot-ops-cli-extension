# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from functools import partial
from time import sleep
from typing import Any, Dict, List, Optional, Tuple, Union

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
    BROKER_RESOURCE,
    CheckTaskStatus,
    IotEdgeBrokerResource,
    ResourceState,
)

from .base import (
    DEFAULT_NAMESPACE,
    client,
    get_cluster_custom_resources,
    get_namespaced_custom_objects,
    get_namespaced_pods_by_prefix,
    get_namespaced_service,
)

logger = get_logger(__name__)

console = Console(width=100, highlight=False)


def run_checks(
    namespace: Optional[str] = None,
    pre_deployment: bool = True,
    post_deployment: bool = True,
    as_list: bool = False,
):
    result = {}

    # with console.status("Analyzing cluster...") as status:
    #    sleep(0.25)

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
            namespace = DEFAULT_NAMESPACE
        result["postDeployment"] = []

        resource_enumeration, api_resources = enumerate_e4k_resources(as_list=as_list)
        result["postDeployment"].append(resource_enumeration)
        if api_resources:
            if "Broker" in api_resources:
                result["postDeployment"].append(evaluate_brokers(namespace=namespace, as_list=as_list))
            if "BrokerListener" in api_resources:
                result["postDeployment"].append(evaluate_broker_listeners(namespace=namespace, as_list=as_list))
            if "DiagnosticService":
                result["postDeployment"].append(evaluate_broker_diagnostics(namespace=namespace, as_list=as_list))
            if "MqttBridgeConnector" in api_resources:
                pass

    if not as_list:
        return result

    process_as_list(result=result, namespace=namespace)


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

        success_content = f"[green]{success_count} succeeded.[/green]"
        warning_content = f"{warning_count} raised warnings."
        warning_content = (
            f"[green]{warning_content}[/green]" if not warning_count else f"[yellow]{warning_content}[/yellow]"
        )
        error_content = f"{error_count} raised errors."
        error_content = f"[green]{error_content}[/green]" if not error_count else f"[red]{error_content}[/red]"
        skipped_content = f"[bright_white]{skipped_count} were skipped[/bright_white]."
        content = f"{success_content}\n{warning_content}\n{error_content}\n{skipped_content}"
        console.print(Panel(content, title="Summary", expand=False))

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


def evaluate_broker_diagnostics(
    namespace: str,
    as_list: bool = False,
):
    check_manager = CheckManager(
        check_name="evalBrokerDiag",
        check_desc="Evaluate E4K broker diagnostics",
        namespace=namespace,
    )
    target_diag = "brokerdiagnostics.az-edge.com"
    target_diag_status = CheckTaskStatus.success.value
    check_manager.add_target(
        target_name=target_diag, conditions=["len(brokerdiagnostics)<=1", "spec", "valid(spec.brokerRef)"]
    )
    valid_broker_refs = _get_valid_references(namespace=namespace, plural="brokers")

    diagnostics_list: dict = get_namespaced_custom_objects(
        resource=BROKER_RESOURCE, namespace=namespace, plural="brokerdiagnostics"
    )
    if not diagnostics_list:
        check_manager.add_target_eval(
            target_name=target_diag,
            status=CheckTaskStatus.skipped.value,
            value=None,
        )
        check_manager.add_display(
            target_name=target_diag,
            display=Padding(
                "Unable to fetch broker diagnostics.",
                (0, 0, 0, 8),
            ),
        )
        return check_manager.as_dict(as_list)

    diagnostics: List[dict] = diagnostics_list.get("items", [])
    diagnostics_count = len(diagnostics)
    diag_count_display = "- Expecting up to [bright_blue]1[/bright_blue] broker diagnostic resource. {}"
    if not diagnostics_count:
        check_manager.set_target_status(target_name=target_diag, status=CheckTaskStatus.skipped.value)
        diag_display_value = f"[bright_white]Detected {diagnostics_count}[/bright_white]."
    elif diagnostics_count > 1:
        check_manager.set_target_status(target_name=target_diag, status=CheckTaskStatus.error.value)
        diag_display_value = f"[red]Detected {diagnostics_count}[/red]."
    else:
        diag_display_value = f"[green]Detected {diagnostics_count}[/green]."

    check_manager.add_display(
        target_name=target_diag,
        display=Padding(diag_count_display.format(diag_display_value), (0, 0, 0, 8)),
    )

    evaluated_diagnostic_services = False
    for diag in diagnostics:
        diag_name: str = diag["metadata"]["name"]
        diag_spec: dict = diag["spec"]
        diag_broker_ref: str = diag_spec["brokerRef"]

        diagnostic_header_display = f"- Broker diagnostic {{[bright_blue]{diag_name}[/bright_blue]}}."
        valid_broker_ref = True
        if diag_broker_ref not in valid_broker_refs:
            valid_broker_ref = False
            broker_ref_display = f"[red]Invalid[/red] reference {{[red]{diag_broker_ref}[/red]}}."
        else:
            broker_ref_display = f"[green]Valid[/green] reference {{[green]{diag_broker_ref}[/green]}}."
        check_manager.add_display(
            target_name=target_diag,
            display=Padding(f"\n{diagnostic_header_display} {broker_ref_display}", (0, 0, 0, 8)),
        )

        diag_spec_endpoint = diag_spec.get("diagnosticServiceEndpoint")
        diag_spec_enable_metrics = diag_spec.get("enableMetrics")
        diag_spec_enable_selfcheck = diag_spec.get("enableSelfCheck")
        diag_spec_enable_tracing = diag_spec.get("enableTracing")
        diag_spec_loglevel = diag_spec.get("logLevel")

        check_manager.add_display(
            target_name=target_diag,
            display=Padding(
                f"Diagnostic Service Endpoint: [cyan]{diag_spec_endpoint}[/cyan]",
                (0, 0, 0, 12),
            ),
        )
        check_manager.add_display(
            target_name=target_diag,
            display=Padding(f"Enable Metrics: [bright_blue]{diag_spec_enable_metrics}[/bright_blue]", (0, 0, 0, 12)),
        )
        check_manager.add_display(
            target_name=target_diag,
            display=Padding(
                f"Enable Self-Check: [bright_blue]{diag_spec_enable_selfcheck}[/bright_blue]", (0, 0, 0, 12)
            ),
        )
        check_manager.add_display(
            target_name=target_diag,
            display=Padding(f"Enable Tracing: [bright_blue]{diag_spec_enable_tracing}[/bright_blue]", (0, 0, 0, 12)),
        )
        check_manager.add_display(
            target_name=target_diag,
            display=Padding(f"Log Level: [cyan]{diag_spec_loglevel}[/cyan]", (0, 0, 0, 12)),
        )
        check_manager.add_target_eval(
            target_name=target_diag,
            status=target_diag_status,
            value={
                "spec": diag_spec,
                "valid(spec.brokerRef)": valid_broker_ref,
            },
            resource_name=diag_name,
        )

    if not evaluated_diagnostic_services:
        diagnostics_service_list: dict = get_namespaced_custom_objects(
            resource=BROKER_RESOURCE, namespace=namespace, plural="diagnosticservices"
        )
        evaluated_diagnostic_services = True
        diagnostics_service_resources = diagnostics_service_list.get("items", [])
        target_diagnostic_service = "diagnosticservices.az-edge.com"
        check_manager.add_target(target_name=target_diagnostic_service, conditions=["spec"])
        if not diagnostics_service_resources:
            no_diag_service_desc = "No diagnostics service resource detected."
            check_manager.add_target_eval(
                target_name=target_diagnostic_service, status=CheckTaskStatus.warning.value, value=no_diag_service_desc
            )
            check_manager.add_display(
                target_name=target_diagnostic_service,
                display=Padding(f"\n[yellow]{no_diag_service_desc}[/yellow]", (0, 0, 0, 8)),
            )
        else:
            for diag_service_resource in diagnostics_service_resources:
                diag_service_resource_name = diag_service_resource["metadata"]["name"]
                diag_service_resource_spec: dict = diag_service_resource["spec"]

                target_diagnostic_service_status = CheckTaskStatus.success.value
                target_diagnostic_service_value = {}
                target_diagnostic_service_value["spec"] = diag_service_resource_spec

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
                    status=target_diagnostic_service_status,
                    value=target_diagnostic_service_value,
                )

                target_service_deployed = f"service/{AZEDGE_DIAGNOSTICS_SERVICE}"
                check_manager.add_target(
                    target_name=target_service_deployed, conditions=["spec.clusterIP", "spec.ports"]
                )
                check_manager.add_display(
                    target_name=target_service_deployed,
                    display=Padding(
                        "\nStatus",
                        (0, 0, 0, 12),
                    ),
                )

                diagnostics_service = get_namespaced_service(
                    name=AZEDGE_DIAGNOSTICS_SERVICE, namespace=namespace, as_dict=True
                )
                if not diagnostics_service:
                    check_manager.add_target_eval(
                        target_name=target_service_deployed, status=CheckTaskStatus.warning.value, value=None
                    )
                    diag_service_desc_suffix = f"[yellow]not detected[/yellow]."
                    diag_service_desc = f"Service {{[bright_blue]{AZEDGE_DIAGNOSTICS_SERVICE}[/bright_blue]}} {diag_service_desc_suffix}"
                    check_manager.add_display(
                        target_name=target_service_deployed,
                        display=Padding(
                            diag_service_desc,
                            (0, 0, 0, 16),
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
                    diag_service_desc_suffix = f"[green]detected[/green]."
                    diag_service_desc = f"Service {{[bright_blue]{AZEDGE_DIAGNOSTICS_SERVICE}[/bright_blue]}} {diag_service_desc_suffix}"
                    check_manager.add_display(
                        target_name=target_service_deployed,
                        display=Padding(
                            diag_service_desc,
                            (0, 0, 0, 16),
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
                                    (0, 0, 0, 20),
                                ),
                            )
                        check_manager.add_display(target_name=target_service_deployed, display=NewLine())

                evaluate_pod_health(
                    check_manager=check_manager,
                    namespace=namespace,
                    pod=AZEDGE_DIAGNOSTICS_SERVICE,
                    display_padding=16,
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

    valid_broker_refs = _get_valid_references(namespace=namespace, plural="brokers")
    listener_list: dict = get_namespaced_custom_objects(
        resource=BROKER_RESOURCE, namespace=namespace, plural="brokerlisteners"
    )

    if not listener_list:
        fetch_listeners_error_text = "Unable to fetch namespace brokerlisteners."
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
    for l in listeners:
        listener_name: str = l["metadata"]["name"]
        listener_spec_service_name: str = l["spec"]["serviceName"]
        listener_spec_service_type: str = l["spec"]["serviceType"]
        listener_broker_ref: str = l["spec"]["brokerRef"]

        listener_eval_value = {}
        listener_eval_value["spec"] = l["spec"]

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
                f"Port: [bright_blue]{l['spec']['port']}[/bright_blue]",
                (0, 0, 0, 12),
            ),
        )
        check_manager.add_display(
            target_name=target_listeners,
            display=Padding(
                f"AuthN enabled: [bright_blue]{l['spec']['authenticationEnabled']}[/bright_blue]",
                (0, 0, 0, 12),
            ),
        )
        check_manager.add_display(
            target_name=target_listeners,
            display=Padding(
                f"AuthZ enabled: [bright_blue]{l['spec']['authenticationEnabled']}[/bright_blue]",
                (0, 0, 0, 12),
            ),
        )
        node_port = l["spec"].get("nodePort")
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
                        ingress_count_colored = f"[red]Detected 0[/red]."
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

    broker_list: dict = get_namespaced_custom_objects(resource=BROKER_RESOURCE, plural="brokers", namespace=namespace)
    if not broker_list:
        fetch_brokers_error_text = "Unable to fetch namespace brokers."
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
                broker_conditions.append("spec.cardinality.backendChain.chainCount>=1")
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
                backend_cardinality_desc = "- Expecting backend chainCount [bright_blue]>=1[/bright_blue]. {}"
                backend_replicas_desc = "- Expecting backend replicas [bright_blue]>=1[/bright_blue]. {}"

                backend_chain = broker_cardinality.get("backendChain", {})
                backend_chain_count: Optional[int] = backend_chain.get("chainCount")
                backend_replicas: Optional[int] = backend_chain.get("replicas")

                if backend_chain_count and backend_chain_count >= 1:
                    backend_chain_count_colored = f"[green]Actual {backend_chain_count}[/green]."
                else:
                    backend_chain_count_colored = f"[red]Actual {backend_chain_count}[/red]."
                    broker_eval_status = CheckTaskStatus.error.value

                if backend_replicas and backend_replicas >= 1:
                    backend_replicas_colored = f"[green]Actual {backend_replicas}[/green]."
                else:
                    backend_replicas_colored = f"[red]Actual {backend_replicas}[/red]."
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
            check_manager=check_manager, namespace=namespace, pod=AZEDGE_DIAGNOSTICS_PROBE_PREFIX, display_padding=12
        )
        evaluate_pod_health(
            check_manager=check_manager, namespace=namespace, pod=AZEDGE_FRONTEND_PREFIX, display_padding=12
        )
        evaluate_pod_health(
            check_manager=check_manager, namespace=namespace, pod=AZEDGE_BACKEND_PREFIX, display_padding=12
        )
        evaluate_pod_health(
            check_manager=check_manager, namespace=namespace, pod=AZEDGE_AUTH_PREFIX, display_padding=12
        )

    return check_manager.as_dict(as_list)


def enumerate_e4k_resources(
    as_list: bool = False,
) -> Tuple[dict, dict]:
    resource_kind_map = {}
    target_api = f"{BROKER_RESOURCE.group}/{BROKER_RESOURCE.version}"
    check_manager = CheckManager(check_name="enumerateE4kApi", check_desc="Enumerate E4K API resources")
    check_manager.add_target(target_name=target_api)

    api_resources: V1APIResourceList = get_cluster_custom_resources(BROKER_RESOURCE)

    if not api_resources:
        check_manager.add_target_eval(target_name=target_api, status=CheckTaskStatus.skipped.value)
        missing_api_text = f"[bright_blue]{target_api}[/bright_blue] API resources [red]not[/red] detected.\n\nSkipping deployment evaluation."
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
        target_display = "At least 1 node is required. Detected {}."
        if node_count < 1:
            target_display = Padding(target_display.format(f"[red]{node_count}[/red]"), (0, 0, 0, 8))
            check_manager.add_target_eval(target_name=target_minimum_nodes, status=CheckTaskStatus.error.value)
            check_manager.add_display(target_name=target_minimum_nodes, display=target_display)
            return check_manager.as_dict()

        target_display = Padding(target_display.format(f"[green]{node_count}[/green]"), (0, 0, 0, 8))
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


# def check_mqtt_bridge_health(namespace: Optional[str] = None):
#     namespaced_object = get_namespaced_object(BRIDGE_RESOURCE, namespace)

#     display_key = "E4K MQTT bridge health"
#     nested_displays = []

#     if not namespaced_object.get("items"):
#         nested_displays.append(
#             Padding(
#                 ":hammer: No E4K bridge installed.",
#                 (0, 0, 0, 4),
#             )
#         )
#     else:
#         valid_bridges = {}
#         for bridge in namespaced_object["items"]:
#             bridge_metadata: dict = bridge["metadata"]
#             bridge_name = bridge_metadata.get("name")
#             if not bridge_name:
#                 nested_displays.append(
#                     Padding(
#                         f":stop_sign: MQTT bridge in namespace '{namespace}' has no field 'name'.",
#                         (0, 0, 0, 4),
#                     )
#                 )
#             else:
#                 valid_bridges[bridge_name] = bridge
#         if valid_bridges:
#             for bridge_name in valid_bridges:
#                 bridge_status = valid_bridges[bridge_name].get("status")
#                 bridge_config_status_level = None
#                 if bridge_status:
#                     bridge_config_status_level = bridge_status.get("configStatusLevel")
#                 # @digimaun - delta, no configStatusLevel == unknown vs error
#                 if not any([bridge_status, bridge_config_status_level]):
#                     nested_displays.append(
#                         Padding(
#                             f"[yellow]:warning:[/yellow] {{{bridge_name}}} current state unknown.",
#                             (0, 0, 0, 4),
#                         )
#                     )
#                 else:
#                     prefix = None
#                     if bridge_config_status_level.lower() == "warn":
#                         prefix = "[yellow]:warning:[/yellow]"
#                     elif bridge_config_status_level.lower() == "error":
#                         prefix = "[red]:stop_sign:[/red]"
#                     else:
#                         prefix = ":zap:"

#                     nested_displays.append(
#                         Padding(
#                             f"{prefix} {{{bridge_name}}} current state {{[light_sea_green]{bridge_config_status_level}[/light_sea_green]}}.",
#                             (0, 0, 0, 4),
#                         )
#                     )

#     display_key, status = _prefix_display_key(display_key, nested_displays)
#     return {"display": {display_key: nested_displays}, "status": status}


# def check_cloud_connector_health(namespace: Optional[str] = None):
#     import tomli
#     from kubernetes.client.models import V1ConfigMap, V1Pod, V1PodList

#     from azext_edge.e4k.common import AZEDGE_KAFKA_CONFIG_PREFIX

#     display_key = "E4K Cloud Connector health"
#     nested_displays = []

#     if not namespace:
#         namespace = DEFAULT_NAMESPACE

#     v1 = client.CoreV1Api()

#     target_pods: List[V1Pod] = []
#     pods_list: V1PodList = v1.list_namespaced_pod(namespace=namespace, label_selector="app=azedge-connector")
#     if not pods_list.items:
#         nested_displays.append(
#             Padding(
#                 f":hammer: No connector pods discovered in namespace {namespace}.",
#                 (0, 0, 0, 4),
#             )
#         )
#     else:
#         target_pods.extend(pods_list.items)
#         for pod in target_pods:
#             connector_prefix = ":zap:"
#             pod_name: str = pod.metadata.name
#             pod_name_parts = pod_name.split("-")
#             pod_config_key = f"{AZEDGE_KAFKA_CONFIG_PREFIX}-{'-'.join(pod_name_parts[2:-2])}"
#             connector_config: V1ConfigMap = v1.read_namespaced_config_map(name=pod_config_key, namespace=namespace)
#             config_data = connector_config.data.get("config.toml")
#             if not config_data:
#                 pass
#             else:
#                 parsed_toml = tomli.loads(config_data)
#                 config_routes = parsed_toml.get("route", [])
#                 routes_prefix = ""
#                 if not config_routes:
#                     connector_prefix = routes_prefix = "[yellow]:warning:[/yellow]"

#                 nested_displays.append(Padding(f"{connector_prefix} Connector {{{pod_name}}} pod", (0, 0, 0, 4)))
#                 nested_displays.append(
#                     Padding(
#                         f"Status: {{{_decorate_pod_phase(pod.status.phase)}}}",
#                         (0, 0, 0, 10),
#                     )
#                 )
#                 nested_displays.append(
#                     Padding(
#                         f"StartTime: {{{pod.status.start_time.strftime('%a %d %b %Y, %I:%M%p %Z')}}}",
#                         (0, 0, 0, 10),
#                     )
#                 )
#                 nested_displays.append(Padding(f"{routes_prefix}Routes", (0, 0, 0, 10)))
#                 for i in range(len(config_routes)):
#                     # i keys: kafka, mqtt, sink_to
#                     nested_displays.append(Padding(f"{i}: {config_routes[i]}", (0, 0, 0, 12)))

#     display_key, status = _prefix_display_key(display_key, nested_displays)
#     return {"display": {display_key: nested_displays}, "status": status}


# post_deployment_checks = {
#     "checkE4KMqttBridgeHealth": check_mqtt_bridge_health,
#     "checkE4KCloudConnectorHealth": check_cloud_connector_health,
# }


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


def _get_valid_references(namespace: str, plural: str):
    result = {}
    custom_objects: dict = get_namespaced_custom_objects(resource=BROKER_RESOURCE, namespace=namespace, plural=plural)
    if custom_objects:
        objects: List[dict] = custom_objects.get("items", [])
        for object in objects:
            o: dict = object
            metadata: dict = o.get("metadata", {})
            name = metadata.get("name")
            if name:
                result[name] = True

    return result


class CheckManager:
    """
    {
        "name":"evaluateBrokerListeners",
        "description": "Evaluate E4K broker listeners",
        "namespace": "default,
        "targets": {
            "len(listeners)": {
                "conditions": ["==1"],
                "evaluations": [
                    {
                        "name?": "listeners",
                        "kind"?: "brokerListener
                        "value"?: 2,
                        "status": "warning"
                    }
                ],
                "status": "warning"
            }
        },
        "status": "warning",
        "displays": []
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
        result = {
            "name": self.check_name,
            "namespace": self.namespace,
            "description": self.check_desc,
            "targets": self.targets,
            "status": self.worst_status,
        }
        if as_list:
            # TODO: hacky
            for t in self.target_displays:
                self.targets[t]["displays"] = self.target_displays[t]

            if self.namespace:
                result["description"] = f"{result['description']} in namespace {{[cyan]{self.namespace}[/cyan]}}"

        return result


def evaluate_pod_health(check_manager: CheckManager, namespace: str, pod: str, display_padding: int):
    from .support.e4k import E4K_LABEL

    target_service_pod = f"pod/{pod}"
    check_manager.add_target(target_name=target_service_pod, conditions=["status.phase"])
    diagnostics_pods, _ = get_namespaced_pods_by_prefix(prefix=pod, namespace=namespace, label_selector=E4K_LABEL)
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
