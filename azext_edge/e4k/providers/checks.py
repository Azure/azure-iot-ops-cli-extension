# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

from abc import ABC, abstractmethod
from functools import partial
from time import sleep
from typing import Any, Dict, List, Optional, Tuple, Union

from knack.log import get_logger
from kubernetes.client.exceptions import ApiException
from kubernetes.client.models import (
    V1APIResource,
    V1APIResourceList,
    V1Namespace,
    V1NamespaceList,
    V1Pod,
    V1PodList,
    V1Service,
    V1ServiceStatus,
)
from rich.console import Console, NewLine, Pretty
from rich.json import JSON
from rich.padding import Padding

from azext_edge.e4k.common import (
    AZEDGE_DIAGNOSTICS_SERVICE,
    AZEDGE_DIAGNOSTICS_PROBE,
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
    get_cluster_custom_resources,
    get_namespaced_custom_objects,
    get_namespaced_pods_by_prefix,
    get_namespaced_service,
)

logger = get_logger(__name__)

console = Console(width=CONSOLE_WIDTH, highlight=False)


def run_checks(
    namespace: Optional[str] = None,
    pre_deployment: bool = True,
    post_deployment: bool = True,
    as_list: bool = False,
):
    result = {}

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

        with console.status("Analyzing cluster...") as status:
            sleep(0.25)
            for c in desired_checks:
                output = desired_checks[c]()
                result["preDeployment"].append(output)

    if post_deployment:
        if not namespace:
            namespace = DEFAULT_NAMESPACE
        result["postDeployment"] = []
        # TODO: with console.status("Analyzing E4K environment...") as status:
        # sleep(0.25)
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

        success_content = f"[green]{success_count} check(s) succeeded.[/green]"
        warning_content = f"{warning_count} check(s) raised warnings."
        warning_content = (
            f"[green]{warning_content}[/green]" if not warning_count else f"[yellow]{warning_content}[/yellow]"
        )
        error_content = f"{error_count} check(s) raised errors."
        error_content = f"[green]{error_content}[/green]" if not error_count else f"[red]{error_content}[/red]"
        skipped_content = f"{skipped_count} check(s) were skipped."
        content = f"{success_content}\n{warning_content}\n{error_content}\n{skipped_content}"
        console.print(Panel(content, title="Summary", expand=False))

    def _enumerate_displays(_checks: List[Dict[str, dict]]):
        for c in _checks:
            status = c.get("status")
            prefix_emoji = get_emoji_from_status(status)
            _increment_summary(status)
            console.print(Padding(f"{prefix_emoji} {c['description']}", (0, 0, 0, 4)))
            # @digimaun - hacky
            targets = c.get("targets", {})
            if targets:
                for t in targets:
                    displays = targets[t].get("displays", [])
                    for d in displays:
                        console.print(d)
            # @digimaun - delete soon
            else:
                evaluations = c.get("evaluations", [])
                for e in evaluations:
                    displays = e.get("displays", [])
                    for d in displays:
                        console.print(d)

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
    target_diag_count = "brokerDiagnostics"
    check_manager.add_target(target_name=target_diag_count, conditions=["len(brokerDiagnostics)==1"])
    valid_broker_refs = _get_valid_references(namespace=namespace, plural="brokers")

    diagnostics_list: dict = get_namespaced_custom_objects(
        resource=BROKER_RESOURCE, namespace=namespace, plural="brokerdiagnostics"
    )
    if not diagnostics_list:
        check_manager.add_target_eval(
            target_name=target_diag_count,
            status=CheckTaskStatus.skipped.value,
            value=None,
        )
        check_manager.add_display(
            target_name=target_diag_count,
            display=Padding(
                "Unable to fetch broker diagnostics.",
                (0, 0, 0, 8),
            ),
        )
        # TODO:digimaun
        return check_manager.as_dict(as_list)

    diagnostics: List[dict] = diagnostics_list.get("items", [])
    diagnostics_count = len(diagnostics)
    add_diag_count_eval = partial(
        check_manager.add_target_eval,
        target_name=target_diag_count,
        value=diagnostics_count,
        resource_kind="BrokerDiagnostic",
    )
    diag_count_display = "- Expecting exactly [blue]1[/blue] broker diagnostic per namespace. Actual {}."
    if diagnostics_count != 1:
        add_diag_count_eval(status=CheckTaskStatus.warning.value)
        diag_display_value = f"[yellow]{diagnostics_count}[/yellow]"
    else:
        add_diag_count_eval(status=CheckTaskStatus.success.value)
        diag_display_value = f"[green]{diagnostics_count}[/green]"
    check_manager.add_display(
        target_name=target_diag_count,
        display=Padding(diag_count_display.format(diag_display_value), (0, 0, 0, 8)),
    )

    evaluated_diagnostic_services = False
    for diag in diagnostics:
        diag_name: str = diag["metadata"]["name"]
        diag_broker_ref: str = diag["spec"]["brokerRef"]

        target_broker_ref = f"resource/{diag_name}.spec.brokerRef"
        check_manager.add_target(target_name=target_broker_ref, conditions=["valid(spec.brokerRef)"])

        diagnostic_header_display = f"- Broker Diagnostic {{[blue]{diag_name}[/blue]}}."
        if diag_broker_ref not in valid_broker_refs:
            check_manager.add_target_eval(
                target_name=target_broker_ref,
                status=CheckTaskStatus.error.value,
                value=diag_broker_ref,
            )
            broker_ref_display = f"[red]Invalid[/red] reference {{[red]{diag_broker_ref}[/red]}}."
        else:
            check_manager.add_target_eval(
                target_name=target_broker_ref,
                status=CheckTaskStatus.success.value,
                value=diag_broker_ref,
            )
            broker_ref_display = f"[green]Valid[/green] reference {{[green]{diag_broker_ref}[/green]}}."
        check_manager.add_display(
            target_name=target_broker_ref,
            display=Padding(f"\n{diagnostic_header_display} {broker_ref_display}", (0, 0, 0, 8)),
        )

        target_diagnostic_spec = f"resource/{diag_name}.spec"
        check_manager.add_target(
            target_name=target_diagnostic_spec,
            conditions=[
                "spec.diagnosticServiceEndpoint",
                "spec.enableMetrics",
                "spec.enableSelfCheck",
                "spec.enableTracing",
                "spec.logLevel",
            ],
        )
        diag_spec_endpoint = diag["spec"].get("diagnosticServiceEndpoint")
        diag_spec_enable_metrics = diag["spec"].get("enableMetrics")
        diag_spec_enable_selfcheck = diag["spec"].get("enableSelfCheck")
        diag_spec_enable_tracing = diag["spec"].get("enableTracing")
        diag_spec_loglevel = diag["spec"].get("logLevel")

        check_manager.add_display(
            target_name=target_diagnostic_spec,
            display=Padding(
                f"Diagnostic Service Endpoint: [cyan]{diag_spec_endpoint}[/cyan]",
                (0, 0, 0, 12),
            ),
        )
        check_manager.add_display(
            target_name=target_diagnostic_spec,
            display=Padding(f"Enable Metrics: [blue]{diag_spec_enable_metrics}[/blue]", (0, 0, 0, 12)),
        )
        check_manager.add_display(
            target_name=target_diagnostic_spec,
            display=Padding(f"Enable Self-Check: [blue]{diag_spec_enable_selfcheck}[/blue]", (0, 0, 0, 12)),
        )
        check_manager.add_display(
            target_name=target_diagnostic_spec,
            display=Padding(f"Enable Tracing: [blue]{diag_spec_enable_tracing}[/blue]", (0, 0, 0, 12)),
        )
        check_manager.add_display(
            target_name=target_diagnostic_spec,
            display=Padding(f"Log Level: [cyan]{diag_spec_loglevel}[/cyan]", (0, 0, 0, 12)),
        )
        check_manager.add_target_eval(
            target_name=target_diagnostic_spec,
            status=CheckTaskStatus.success.value,
            value={
                "spec.diagnosticServiceEndpoint": diag_spec_endpoint,
                "spec.enableMetrics": diag_spec_enable_metrics,
                "spec.enableSelfCheck": diag_spec_enable_selfcheck,
                "spec.enableTracing": diag_spec_enable_tracing,
                "spec.logLevel": diag_spec_loglevel,
            },
            resource_name=diag_name,
        )

        check_manager.add_display(
            target_name=target_diagnostic_spec,
            display=Padding(
                "\nStatus",
                (0, 0, 0, 12),
            ),
        )
        evaluate_pod_health(
            check_manager=check_manager, namespace=namespace, pod=AZEDGE_DIAGNOSTICS_PROBE, display_padding=16
        )

        if not evaluated_diagnostic_services:
            diagnostics_service_list = dict = get_namespaced_custom_objects(
                resource=BROKER_RESOURCE, namespace=namespace, plural="diagnosticservices"
            )
            diagnostics_service_resources = diagnostics_service_list.get("items", [])
            if diagnostics_service_resources:
                for diag_service_resource in diagnostics_service_resources:
                    diag_service_resource_name = diag_service_resource["metadata"]["name"]
                    diag_service_resource_kind = diag_service_resource["kind"]
                    diag_service_resource_spec = diag_service_resource["spec"]

                    target_diagnostic_service_spec = f"resource/{diag_service_resource_name}.spec"
                    check_manager.add_target(
                        target_name=target_diagnostic_service_spec,
                        conditions=[
                            "spec.diagnosticServiceEndpoint",
                            "spec.enableMetrics",
                            "spec.enableSelfCheck",
                            "spec.enableTracing",
                            "spec.logLevel",
                        ],
                    )

                    check_manager.add_display(
                        target_name=target_diagnostic_service_spec,
                        display=Padding(
                            f"\nAssociated resource {{[blue]{diag_service_resource_name}[/blue]}} of kind {{[blue]{diag_service_resource_kind}[/blue]}}.",
                            (0, 0, 0, 12),
                        ),
                    )

                    diag_service_spec_data_export_freq = diag_service_resource_spec.get("dataExportFrequencySeconds")
                    diag_service_spec_log_format = diag_service_resource_spec.get("logFormat")
                    diag_service_spec_log_level = diag_service_resource_spec.get("logLevel")
                    diag_service_spec_max_data_storage_size = diag_service_resource_spec.get("maxDataStorageSize")
                    diag_service_spec_metrics_port = diag_service_resource_spec.get("metricsPort")
                    diag_service_spec_stale_data_timeout = diag_service_resource_spec.get("staleDataTimeoutSeconds")

                    check_manager.add_display(
                        target_name=target_diagnostic_service_spec,
                        display=Padding(
                            f"Data Export Frequency: [blue]{diag_service_spec_data_export_freq}[/blue] seconds",
                            (0, 0, 0, 16),
                        ),
                    )
                    check_manager.add_display(
                        target_name=target_diagnostic_service_spec,
                        display=Padding(
                            f"Log Format: [blue]{diag_service_spec_log_format}[/blue]",
                            (0, 0, 0, 16),
                        ),
                    )
                    check_manager.add_display(
                        target_name=target_diagnostic_service_spec,
                        display=Padding(
                            f"Log Level: [blue]{diag_service_spec_log_level}[/blue]",
                            (0, 0, 0, 16),
                        ),
                    )
                    check_manager.add_display(
                        target_name=target_diagnostic_service_spec,
                        display=Padding(
                            f"Max Data Storage Size: [blue]{diag_service_spec_max_data_storage_size}[/blue]",
                            (0, 0, 0, 16),
                        ),
                    )
                    check_manager.add_display(
                        target_name=target_diagnostic_service_spec,
                        display=Padding(
                            f"Metrics Port: [blue]{diag_service_spec_metrics_port}[/blue]",
                            (0, 0, 0, 16),
                        ),
                    )
                    check_manager.add_display(
                        target_name=target_diagnostic_service_spec,
                        display=Padding(
                            f"Stale Data Timeout: [blue]{diag_service_spec_stale_data_timeout}[/blue] seconds",
                            (0, 0, 0, 16),
                        ),
                    )

                    target_service_deployed = f"service/{AZEDGE_DIAGNOSTICS_SERVICE}"
                    check_manager.add_target(
                        target_name=target_service_deployed, conditions=[f"exists({target_service_deployed})"]
                    )
                    check_manager.add_display(
                        target_name=target_service_deployed,
                        display=Padding(
                            "\nStatus",
                            (0, 0, 0, 16),
                        ),
                    )
                    diagnostics_service = get_namespaced_service(name=AZEDGE_DIAGNOSTICS_SERVICE, namespace=namespace)
                    if diagnostics_service:
                        check_manager.add_target_eval(
                            target_name=target_service_deployed,
                            status=CheckTaskStatus.success.value,
                            value=True,
                            resource_name=diagnostics_service.metadata.name,
                        )
                        diag_service_display_suffix = f"[green]detected[/green]."
                    else:
                        check_manager.add_target_eval(
                            target_name=target_service_deployed, status=CheckTaskStatus.warning.value, value=None
                        )
                        diag_service_display_suffix = f"[yellow]not detected[/yellow]."

                    diag_service_display = (
                        f"Service {{[blue]{AZEDGE_DIAGNOSTICS_SERVICE}[/blue]}} {diag_service_display_suffix}"
                    )
                    check_manager.add_display(
                        target_name=target_service_deployed,
                        display=Padding(
                            diag_service_display,
                            (0, 0, 0, 20),
                        ),
                    )
                    evaluate_pod_health(
                        check_manager=check_manager,
                        namespace=namespace,
                        pod=AZEDGE_DIAGNOSTICS_SERVICE,
                        display_padding=20,
                    )

            evaluated_diagnostic_services = True

    return check_manager.as_dict(as_list)


def evaluate_broker_listeners(
    namespace: str,
    as_list: bool = False,
):
    from kubernetes.client.models import V1LoadBalancerIngress, V1LoadBalancerStatus

    result = {}
    result["name"] = "evaluateBrokerListeners"
    result["description"] = "Evaluate E4K broker listeners"
    result["evaluations"] = []
    displays = []

    evaluate_listener_count = {
        "expected": ">=1",
        "target": "brokerListenerCount",
    }
    evaluate_listener_reference = {
        "expected": "validRef",
        "target": "spec.brokerRef",
        "actual": [],
    }
    evaluate_loadbalancer_ip = {
        "expected": "[*].ip",
        "target": "status.loadbalancer.ingress",
        "actual": [],
    }

    valid_broker_refs = _get_valid_references(namespace=namespace, plural="brokers")
    listener_list: dict = get_namespaced_custom_objects(
        resource=BROKER_RESOURCE, namespace=namespace, plural="brokerlisteners"
    )
    if not listener_list:
        evaluate_listener_count["status"] = CheckTaskStatus.error.value
        displays.append(
            Padding(
                "Unable to fetch broker listeners.",
                (0, 0, 0, 8),
            )
        )
    else:
        listeners: List[dict] = listener_list.get("items", [])
        listener_count_desc = "- Expecting {{[blue]>=1[/blue]}} broker listeners per namespace. Actual {{{}}}."
        listener_count = len(listeners)
        evaluate_listener_count["actual"] = listener_count
        if listener_count < 1:
            evaluate_listener_count["status"] = CheckTaskStatus.error.value
            displays.append(
                Padding(
                    listener_count_desc.format(f"[red]{listener_count}[/red]"),
                    (0, 0, 0, 8),
                )
            )
        else:
            evaluate_listener_count["status"] = CheckTaskStatus.success.value
            displays.append(
                Padding(
                    listener_count_desc.format(f"[green]{listener_count}[/green]"),
                    (0, 0, 0, 8),
                )
            )

        for l in listeners:
            listener_name: str = l["metadata"]["name"]
            listener_namespace: str = l["metadata"]["namespace"]
            listener_spec_service_name: str = l["spec"]["serviceName"]
            listener_spec_service_type: str = l["spec"]["serviceType"]
            listener_broker_ref: str = l["spec"]["brokerRef"]
            eval_broker_ref = {
                "spec.brokerRef": listener_broker_ref,
                "name": listener_name,
                "namespace": listener_namespace,
            }
            if listener_broker_ref not in valid_broker_refs:
                eval_broker_ref["status"] = CheckTaskStatus.error.value
                ref_display = f"[red]Invalid[/red] reference {{[red]{listener_broker_ref}[/red]}}."
            else:
                eval_broker_ref["status"] = CheckTaskStatus.success.value
                ref_display = f"[green]Valid[/green] reference {{[green]{listener_broker_ref}[/green]}}."
            evaluate_listener_reference["actual"].append(eval_broker_ref)

            displays.append(
                Padding(
                    f"\n- Broker Listener {{[blue]{listener_name}[/blue]}}. {ref_display}",
                    (0, 0, 0, 8),
                ),
            )
            displays.append(
                Padding(
                    f"Port: {{[blue]{l['spec']['port']}[/blue]}}",
                    (0, 0, 0, 12),
                ),
            )
            displays.append(
                Padding(
                    f"AuthN enabled: {{[blue]{l['spec']['authenticationEnabled']}[/blue]}}",
                    (0, 0, 0, 12),
                ),
            )
            displays.append(
                Padding(
                    f"AuthZ enabled: {{[blue]{l['spec']['authenticationEnabled']}[/blue]}}",
                    (0, 0, 0, 12),
                ),
            )

            associated_service: V1Service = get_namespaced_service(name=listener_spec_service_name, namespace=namespace)
            if not associated_service:
                displays.append(
                    Padding(
                        f"Unable to fetch associated service {{[red]{listener_spec_service_name}[/red]}}.",
                        (0, 0, 0, 12),
                    ),
                )
                continue
            displays.append(
                Padding(
                    f"\nAssociated service {{[blue]{listener_spec_service_name}[/blue]}} of type {{[blue]{listener_spec_service_type}[/blue]}}",
                    (0, 0, 0, 12),
                ),
            )

            service_status: V1ServiceStatus = associated_service.status
            if listener_spec_service_type.lower() == "loadbalancer":
                evaluate_loadbalancer_ip_entry = {}
                load_balancer: V1LoadBalancerStatus = service_status.load_balancer
                # TODO
                ingress_rules: List[V1LoadBalancerIngress] = load_balancer.ingress
                evaluate_loadbalancer_ip_entry["namespace"] = namespace
                evaluate_loadbalancer_ip_entry["name"] = listener_name
                evaluate_loadbalancer_ip_entry["status.loadbalancer.ingress"] = ingress_rules

                if not ingress_rules:
                    evaluate_loadbalancer_ip_entry["status"] = CheckTaskStatus.warning.value
                else:
                    ingress_rules_count = len(ingress_rules)
                    displays.append(
                        Padding(
                            f"Status",
                            (0, 0, 0, 16),
                        ),
                    )
                    actual_ingress_count = (
                        f"{{[red]{ingress_rules_count}[/red]}}"
                        if not ingress_rules_count
                        else f"{{[green]{ingress_rules_count}[/green]}}"
                    )
                    displays.append(
                        Padding(
                            f"- Expecting at least {{[blue]{1}[/blue]}} ingress rule. Actual {actual_ingress_count}.",
                            (0, 0, 0, 20),
                        ),
                    )
                    for ingress in ingress_rules:
                        ing: dict = ingress.to_dict()
                        rule_display = ""
                        hostname = ing.get("hostname")
                        ip = ing.get("ip")
                        evaluate_loadbalancer_ip_entry["status"] = (
                            CheckTaskStatus.success.value if ip or hostname else CheckTaskStatus.warning.value
                        )
                        if hostname:
                            rule_display = f"hostname: {{[green]{hostname}[/green]}}"
                        if ip:
                            rule_display = f"{rule_display} ip: {{[green]{ip}[/green]}}"
                        displays.append(
                            Padding(
                                rule_display,
                                (0, 0, 0, 24),
                            ),
                        )
                evaluate_loadbalancer_ip["actual"].append(evaluate_loadbalancer_ip_entry)
            if listener_spec_service_type.lower() == "clusterip":
                safe_cluster_ip = associated_service.to_dict().get("spec", {}).get("cluster_ip")
                if safe_cluster_ip:
                    displays.append(
                        Padding(
                            f"Cluster IP: [blue]{safe_cluster_ip}[/blue]",
                            (0, 0, 0, 16),
                        ),
                    )

    if as_list:
        evaluate_listener_count["displays"] = displays
        result["description"] = f"{result['description']} in namespace {{[cyan]{namespace}[/cyan]}}"
    result["evaluations"].append(evaluate_listener_count)
    if evaluate_listener_reference.get("actual"):
        evaluate_listener_reference["status"] = _get_worst_status(evaluate_listener_reference["actual"])
        result["evaluations"].append(evaluate_listener_reference)
    if evaluate_loadbalancer_ip.get("actual"):
        evaluate_loadbalancer_ip["status"] = _get_worst_status(evaluate_loadbalancer_ip["actual"])
    result["status"] = _get_worst_status(result["evaluations"])

    return result


def evaluate_brokers(
    namespace: str,
    as_list: bool = False,
):
    check_manager = CheckManager(check_name="evaluateBrokers", check_desc="Evaluate E4K brokers", namespace=namespace)

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
    brokers_count_text = "- Expecting exactly [blue]1[/blue] broker resource per namespace. Detected {}."
    broker_eval_status = CheckTaskStatus.success.value

    if brokers_count == 1:
        brokers_count_text = brokers_count_text.format(f"[green]{brokers_count}[/green]")
    else:
        brokers_count_text = brokers_count_text.format(f"[red]{brokers_count}[/red]")
        broker_eval_status = CheckTaskStatus.error.value
    check_manager.add_display(target_name=target_brokers, display=Padding(brokers_count_text, (0, 0, 0, 8)))

    for b in brokers:
        broker_namespace = b["metadata"]["namespace"]
        broker_name = b["metadata"]["name"]
        broker_spec: dict = b["spec"]
        broker_mode = broker_spec.get("mode")
        broker_status_state = b.get("status", {})
        broker_status = broker_status_state.get("status", "N/A")
        broker_status_desc = broker_status_state.get("statusDescription")

        status_display_text = f"Status {{{_decorate_resource_status(broker_status)}}}."

        if broker_status_state:
            status_display_text = f"{status_display_text} {broker_status_desc}."

        target_broker_text = f"\n- Broker [blue]{broker_name}[/blue] mode [blue]{broker_mode}[/blue]."
        check_manager.add_display(target_name=target_brokers, display=Padding(target_broker_text, (0, 0, 0, 8)))

        broker_eval_value = {"status": {"status": broker_status, "statusDescription": broker_status_desc}}
        broker_eval_status = CheckTaskStatus.success.value

        if broker_status in [ResourceState.error.value, ResourceState.failed.value]:
            broker_eval_status = CheckTaskStatus.error.value
        elif broker_status in [
            ResourceState.recovering.value,
            ResourceState.warn.value,
        ]:
            broker_eval_status = CheckTaskStatus.warning.value
        check_manager.add_display(target_name=target_brokers, display=Padding(status_display_text, (0, 0, 0, 12)))

        if broker_mode == "distributed":
            broker_conditions.append("spec.cardinality")
            broker_conditions.append("spec.cardinality.backendChain.chainCount>=1")
            broker_conditions.append("spec.cardinality.backendChain.replicas>=1")
            broker_conditions.append("spec.cardinality.frontend.replicas>=1")

            check_manager.set_target_conditions(target_name=target_brokers, conditions=broker_conditions)
            check_manager.add_display(target_name=target_brokers, display=Padding("\nCardinality", (0, 0, 0, 12)))
            broker_cardinality: dict = broker_spec.get("cardinality")
            broker_eval_value["spec.cardinality"] = broker_cardinality
            if not broker_cardinality:
                broker_eval_status = CheckTaskStatus.error.value
                check_manager.add_display(
                    target_name=target_brokers,
                    display=Padding("[magenta]spec.cardinality is undefined![/magenta]", (0, 0, 0, 16)),
                )
            else:
                backend_cardinality_desc = (
                    "- Expecting backend chainCount [blue]>=1[/blue] and replicas [blue]>=1[/blue]. Actual {} and {}."
                )
                backend_chain = broker_cardinality.get("backendChain", {})
                backend_chain_count: Optional[int] = backend_chain.get("chainCount")
                backend_replicas: Optional[int] = backend_chain.get("replicas")

                if backend_chain_count and backend_chain_count >= 1:
                    backend_chain_count_colored = f"[green]{backend_chain_count}[/green]"
                else:
                    backend_chain_count_colored = f"[red]{backend_chain_count}[/red]"
                    broker_eval_status = CheckTaskStatus.error.value

                if backend_replicas and backend_replicas >= 1:
                    backend_replicas_colored = f"[green]{backend_replicas}[/green]"
                else:
                    backend_replicas_colored = f"[red]{backend_replicas}[/red]"
                    broker_eval_status = CheckTaskStatus.error.value

                check_manager.add_display(
                    target_name=target_brokers,
                    display=Padding(
                        backend_cardinality_desc.format(backend_chain_count_colored, backend_replicas_colored),
                        (0, 0, 0, 16),
                    ),
                )

                frontend_cardinality_desc = "- Expecting frontend replicas [blue]>=1[/blue]. Actual {}."
                frontend_replicas: Optional[int] = broker_cardinality.get("frontend", {}).get("replicas")

                if frontend_replicas and frontend_replicas >= 1:
                    frontend_replicas_colored = f"[green]{frontend_replicas}[/green]"
                else:
                    frontend_replicas_colored = f"[red]{frontend_replicas}[/red]"

                check_manager.add_display(
                    target_name=target_brokers,
                    display=Padding(frontend_cardinality_desc.format(frontend_replicas_colored), (0, 0, 0, 16)),
                )

        check_manager.add_target_eval(
            target_name=target_brokers, status=broker_eval_status, value=broker_eval_value, resource_name=broker_name
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
        missing_api_text = (
            f"[blue]{target_api}[/blue] API resources [red]not[/red] detected.\n\nSkipping deployment evaluation."
        )
        check_manager.add_display(target_name=target_api, display=Padding(missing_api_text, (0, 0, 0, 8)))
        return check_manager.as_dict(as_list), resource_kind_map

    api_header_display = Padding(f"[blue]{target_api}[/blue] API resources", (0, 0, 0, 8))
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
        check_manager.add_display(target_name=target_k8s_version, display=Padding((0, 0, 0, 8)))
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

        k8s_semver_text = f"Require [blue]k8s[/blue] >=[cyan]{MIN_K8S_VERSION}[/cyan] detected {semver_colored}."
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
        check_manager.add_display(target_name=target_helm_version, display=Padding(not_found_helm_text, 0, 0, 0, 8))
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
        check_manager.add_display(target_name=target_helm_version, display=Padding(process_error_text, 0, 0, 0, 8))
        return CheckManager.as_dict(as_list)

    helm_semver = completed_process.stdout.decode("utf-8").replace('"', "")
    if version.parse(helm_semver) >= version.parse(MIN_HELM_VERSION):
        helm_semver_status = CheckTaskStatus.success.value
        helm_semver_colored = f"[green]{helm_semver}[/green]"
    else:
        helm_semver_status = CheckTaskStatus.error.value
        helm_semver_colored = f"[red]{helm_semver}[/red]"
    helm_semver_text = f"Require [blue]helm[/blue] >=[cyan]{MIN_HELM_VERSION}[/cyan] detected {helm_semver_colored}."

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

            node_memory_display = Padding(f"[blue]{node_name}[/blue] {mem_colored} MiB", (0, 0, 0, 8))
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
    if status in [ResourceState.recovering.value, ResourceState.warn.value, "N/A"]:
        return f"[yellow]{status}[/yellow]"
    return f"[green]{status}[/green]"
    # TODO: light_sea_green


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


def _get_worst_status(evals: List[dict]) -> str:
    worst_status = CheckTaskStatus.success.value
    for e in evals:
        eval_status = e.get("status")
        if eval_status == CheckTaskStatus.error.value:
            return CheckTaskStatus.error.value
        if eval_status == CheckTaskStatus.warning.value and worst_status == CheckTaskStatus.success.value:
            worst_status = CheckTaskStatus.warning.value
    return worst_status


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

    def add_target(self, target_name: str, conditions: List[str] = None):
        if target_name not in self.targets:
            self.targets[target_name] = {}
        self.targets[target_name]["conditions"] = conditions
        self.targets[target_name]["evaluations"]: List[dict] = []
        self.targets[target_name]["status"] = CheckTaskStatus.success.value

    def set_target_conditions(self, target_name: str, conditions: List[str]):
        self.targets[target_name]["conditions"] = conditions

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
            ]:
                self.targets[target_name]["status"] = status
                self.worst_status = status
            elif existing_status == CheckTaskStatus.warning.value and status in [CheckTaskStatus.error.value]:
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
    target_service_pod = f"pod/{pod}"
    check_manager.add_target(target_name=target_service_pod, conditions=["status.phase"])
    diagnostics_pods, _ = get_namespaced_pods_by_prefix(prefix=pod, namespace=namespace)
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

            check_manager.add_target_eval(target_name=target_service_pod, status=status, value=pod_phase)
            check_manager.add_display(
                target_name=target_service_pod,
                display=Padding(
                    f"Pod {{[blue]{pod_name}[/blue]}} in phase {{{pod_phase_deco}}}.",
                    (0, 0, 0, display_padding),
                ),
            )
