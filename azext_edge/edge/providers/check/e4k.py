# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from typing import Any, Dict, List, Optional, Union
from enum import Enum
from .base import (
    CheckManager,
    decorate_resource_status,
    check_post_deployment,
    check_pre_deployment,
    evaluate_pod_health,
    process_as_list
)

from rich.console import Console, NewLine
from rich.padding import Padding

from ...common import (
    AZEDGE_DIAGNOSTICS_SERVICE,
    CheckTaskStatus,
    ResourceState,
)

from .common import (
    AZEDGE_DIAGNOSTICS_PROBE_PREFIX,
    AZEDGE_FRONTEND_PREFIX,
    AZEDGE_BACKEND_PREFIX,
    AZEDGE_AUTH_PREFIX,
    KafkaTopicMapRouteType,
    ResourceOutputDetailLevel,
)

from ...providers.edge_api import (
    E4K_ACTIVE_API,
    E4kResourceKinds
)
from ..support.e4k import E4K_LABEL

from ..base import get_namespaced_service


def check_e4k_deployment(
    console: Console,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    namespace: Optional[str] = None,
    pre_deployment: bool = True,
    post_deployment: bool = True,
    as_list: bool = False,
    resource_kinds: List[str] = None,
    result: Dict[str, Any] = None,
) -> Union[Dict[str, Any], None]:
    if pre_deployment:
        check_pre_deployment(result, as_list)

    if post_deployment:
        if not namespace:
            from ..base import DEFAULT_NAMESPACE

            namespace = DEFAULT_NAMESPACE
        result["postDeployment"] = []

        # check post deployment according to edge_service type
        check_e4k_post_deployment(
            detail_level=detail_level,
            result=result,
            as_list=as_list,
            resource_kinds=resource_kinds,
        )

    if not as_list:
        return result

    return process_as_list(console=console, result=result)


def check_e4k_post_deployment(
    result: Dict[str, Any],
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_kinds: List[str] = None,
) -> None:
    evaluate_funcs = {
        E4kResourceKinds.BROKER: evaluate_brokers,
        E4kResourceKinds.BROKER_LISTENER: evaluate_broker_listeners,
        E4kResourceKinds.DIAGNOSTIC_SERVICE: evaluate_diagnostics_service,
        E4kResourceKinds.MQTT_BRIDGE_CONNECTOR: evaluate_mqtt_bridge_connectors,
        E4kResourceKinds.DATALAKE_CONNECTOR: evaluate_datalake_connectors,
        E4kResourceKinds.KAFKA_CONNECTOR: evaluate_kafka_connectors,
    }

    return check_post_deployment(
        api_info=E4K_ACTIVE_API,
        check_name="enumerateE4kApi",
        check_desc="Enumerate E4K API resources",
        result=result,
        resource_kinds_enum=E4kResourceKinds,
        evaluate_funcs=evaluate_funcs,
        as_list=as_list,
        detail_level=detail_level,
        resource_kinds=resource_kinds
    )


def evaluate_diagnostics_service(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
) -> Dict[str, Any]:
    check_manager = CheckManager(
        check_name="evalBrokerDiag",
        check_desc="Evaluate E4K Diagnostics Service",
    )
    diagnostics_service_list: dict = E4K_ACTIVE_API.get_resources(
        kind=E4kResourceKinds.DIAGNOSTIC_SERVICE
    )
    diagnostics_service_resources = diagnostics_service_list.get("items", [])
    target_diagnostic_service = "diagnosticservices.az-edge.com"

    namespaces = {res.get("metadata", {}).get("namespace") for res in diagnostics_service_resources}

    diagnostic_service_resources_by_namespace = {}

    for namespace in namespaces:
        diagnostic_service_resources_by_namespace[namespace] = [
            res for res in diagnostics_service_resources if res.get("metadata", {}).get("namespace") == namespace
        ]
    
    for namespace in diagnostic_service_resources_by_namespace:
        check_manager.add_target(
            target_name=target_diagnostic_service,
            namespace=namespace,
            conditions=["len(diagnosticservices)==1", "spec"],
        )
        check_manager.add_display(
            target_name=target_diagnostic_service,
            namespace=namespace,
            display=Padding(
                f"Diagnostic Service Resources in namespace {{[purple]{namespace}[/purple]}}",
                (0,0,0,8)
            )
        )
        diagnostics_service_resources = diagnostic_service_resources_by_namespace[namespace]

        diagnostics_count_text = "- Expecting [bright_blue]1[/bright_blue] diagnostics service resource per namespace. {}."
        diagnostic_service_count = len(diagnostics_service_resources)

        service_count_status = CheckTaskStatus.success.value
        service_status_color = "green"

        # warn if we have <0, >1 diagnostic service resources
        if diagnostic_service_count != 1:
            service_count_status = CheckTaskStatus.warning.value
            service_status_color = "yellow"

        diagnostics_count_text = diagnostics_count_text.format(
            f"[{service_status_color}]Detected {diagnostic_service_count}[/{service_status_color}]"
        )

        check_manager.add_target_eval(
            target_name=target_diagnostic_service,
            namespace=namespace,
            status=service_count_status,
            value=diagnostic_service_count,
        )
        check_manager.add_display(
            target_name=target_diagnostic_service,
            namespace=namespace,
            display=Padding(diagnostics_count_text, (0, 0, 0, 8)),
        )

        for diag_service_resource in diagnostics_service_resources:
            diag_service_resource_name = diag_service_resource["metadata"]["name"]
            diag_service_resource_spec: dict = diag_service_resource["spec"]

            check_manager.add_display(
                target_name=target_diagnostic_service,
                namespace=namespace,
                display=Padding(
                    f"\n- Diagnostic service resource {{[bright_blue]{diag_service_resource_name}[/bright_blue]}}.",
                    (0, 0, 0, 8),
                ),
            )

            for (key, label, suffix) in [
                ("dataExportFrequencySeconds", "Data Export Frequency", " seconds"),
                ("logFormat", "Log Format", None),
                ("logLevel", "Log Level", None),
                ("maxDataStorageSize", "Max Data Storage Size", None),
                ("metricsPort", "Metrics Port", None),
                ("staleDataTimeoutSeconds", "Stale Data Timeout", " seconds"),
            ]:
                val = diag_service_resource_spec.get(key)
                check_manager.add_display(
                target_name=target_diagnostic_service,
                namespace=namespace,
                display=Padding(
                    f"{label}: [bright_blue]{val}[/bright_blue]{suffix or ''}",
                    (0, 0, 0, 12),
                ),
            )
            check_manager.add_target_eval(
                target_name=target_diagnostic_service,
                namespace=namespace,
                status=CheckTaskStatus.success.value,
                value={"spec": diag_service_resource_spec},
            )

            target_service_deployed = f"service/{AZEDGE_DIAGNOSTICS_SERVICE}"
            check_manager.add_target(target_name=target_service_deployed, namespace=namespace, conditions=["spec.clusterIP", "spec.ports"])
            check_manager.add_display(
                target_name=target_service_deployed,
                namespace=namespace,
                display=Padding(
                    "\nService Status",
                    (0, 0, 0, 8),
                ),
            )

            diagnostics_service = get_namespaced_service(name=AZEDGE_DIAGNOSTICS_SERVICE, namespace=namespace, as_dict=True)
            if not diagnostics_service:
                check_manager.add_target_eval(
                    target_name=target_service_deployed,
                    namespace=namespace,
                    status=CheckTaskStatus.error.value,
                    value=None,
                )
                diag_service_desc_suffix = "[red]not detected[/red]."
                diag_service_desc = (
                    f"Service {{[bright_blue]{AZEDGE_DIAGNOSTICS_SERVICE}[/bright_blue]}} {diag_service_desc_suffix}"
                )
                check_manager.add_display(
                    target_name=target_service_deployed,
                    namespace=namespace,
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
                    namespace=namespace,
                    status=CheckTaskStatus.success.value,
                    value={"spec": {"clusterIP": clusterIP, "ports": ports}},
                    resource_name=diagnostics_service["metadata"]["name"],
                )
                diag_service_desc_suffix = "[green]detected[/green]."
                diag_service_desc = (
                    f"Service {{[bright_blue]{AZEDGE_DIAGNOSTICS_SERVICE}[/bright_blue]}} {diag_service_desc_suffix}"
                )
                check_manager.add_display(
                    target_name=target_service_deployed,
                    namespace=namespace,
                    display=Padding(
                        diag_service_desc,
                        (0, 0, 0, 12),
                    ),
                )
                if ports:
                    for port in ports:
                        check_manager.add_display(
                            target_name=target_service_deployed,
                            namespace=namespace,
                            display=Padding(
                                f"[cyan]{port.get('name')}[/cyan] "
                                f"port [bright_blue]{port.get('port')}[/bright_blue] "
                                f"protocol [cyan]{port.get('protocol')}[/cyan]",
                                (0, 0, 0, 16),
                            ),
                        )
                    check_manager.add_display(target_name=target_service_deployed, namespace=namespace, display=NewLine())

                evaluate_pod_health(
                    check_manager=check_manager,
                    namespace=namespace,
                    pod=AZEDGE_DIAGNOSTICS_SERVICE,
                    display_padding=12,
                    service_label=E4K_LABEL
                )

    return check_manager.as_dict(as_list)


def evaluate_broker_listeners(
    namespace: Optional[str] = None,
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
) -> Dict[str, Any]:
    check_manager = CheckManager(
        check_name="evalBrokerListeners",
        check_desc="Evaluate E4K broker listeners",
    )

    target_listeners = "brokerlisteners.az-edge.com"
    listener_conditions = [
        "len(brokerlisteners)>=1",
        "spec",
        "valid(spec.brokerRef)",
        "spec.serviceName",
        "status",
    ]
    check_manager.add_target(target_name=target_listeners, conditions=listener_conditions)

    valid_broker_refs = _get_valid_references(kind=E4kResourceKinds.BROKER, namespace=namespace)
    listener_list: dict = E4K_ACTIVE_API.get_resources(E4kResourceKinds.BROKER_LISTENER, namespace=namespace)

    if not listener_list:
        fetch_listeners_error_text = f"Unable to fetch {E4kResourceKinds.BROKER_LISTENER.value}s."
        check_manager.add_target_eval(
            target_name=target_listeners,
            status=CheckTaskStatus.error.value,
            value=fetch_listeners_error_text,
        )
        check_manager.add_display(
            target_name=target_listeners,
            display=Padding(fetch_listeners_error_text, (0, 0, 0, 8)),
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
        namespace: str = namespace or listener["metadata"]["namespace"]
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
                        conditions=[
                            "status",
                            "len(status.loadBalancer.ingress[*].ip)>=1",
                        ],
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
                        display=Padding(
                            ingress_rules_desc.format(ingress_count_colored),
                            (0, 0, 0, 12),
                        ),
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
                        target_name=target_listener_service,
                        status=listener_service_eval_status,
                        value=service_status,
                    )

                if listener_spec_service_type.lower() == "clusterip":
                    check_manager.set_target_conditions(
                        target_name=target_listener_service,
                        conditions=["spec.clusterIP"],
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
    as_list: bool = False,
    namespace: Optional[str] = None,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
) -> Dict[str, Any]:
    check_manager = CheckManager(check_name="evalBrokers", check_desc="Evaluate E4K broker")

    target_brokers = "brokers.az-edge.com"
    broker_conditions = ["len(brokers)==1", "status", "spec.mode"]
    check_manager.add_target(target_name=target_brokers, conditions=broker_conditions)

    broker_list: dict = E4K_ACTIVE_API.get_resources(E4kResourceKinds.BROKER, namespace=namespace)
    if not broker_list:
        fetch_brokers_error_text = f"Unable to fetch namespace {E4kResourceKinds.BROKER.value}s."
        check_manager.add_target_eval(
            target_name=target_brokers,
            status=CheckTaskStatus.error.value,
            value=fetch_brokers_error_text,
        )
        check_manager.add_display(
            target_name=target_brokers,
            display=Padding(fetch_brokers_error_text, (0, 0, 0, 8)),
        )
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

        status_display_text = f"Status {{{decorate_resource_status(broker_status)}}}."

        if broker_status_state:
            status_display_text = f"{status_display_text} {broker_status_desc}."

        target_broker_text = (
            f"\n- Broker {{[bright_blue]{broker_name}[/bright_blue]}} mode [bright_blue]{broker_mode}[/bright_blue]."
        )
        check_manager.add_display(
            target_name=target_brokers,
            display=Padding(target_broker_text, (0, 0, 0, 8)),
        )

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
        check_manager.add_display(
            target_name=target_brokers,
            display=Padding(status_display_text, (0, 0, 0, 12)),
        )

        if broker_mode == "distributed":
            if not added_distributed_conditions:
                # TODO - conditional evaluations
                broker_conditions.append("spec.cardinality")
                broker_conditions.append("spec.cardinality.backendChain.partitions>=1")
                broker_conditions.append("spec.cardinality.backendChain.replicas>=1")
                broker_conditions.append("spec.cardinality.backendChain.workers>=1")
                broker_conditions.append("spec.cardinality.frontend.replicas>=1")
                added_distributed_conditions = True

            check_manager.set_target_conditions(target_name=target_brokers, conditions=broker_conditions)
            check_manager.add_display(
                target_name=target_brokers,
                display=Padding("\nCardinality", (0, 0, 0, 12)),
            )
            broker_cardinality: dict = broker_spec.get("cardinality")
            broker_eval_value["spec.cardinality"] = broker_cardinality
            broker_eval_value["spec.mode"] = broker_mode
            if not broker_cardinality:
                broker_eval_status = CheckTaskStatus.error.value
                check_manager.add_display(
                    target_name=target_brokers,
                    display=Padding(
                        "[magenta]spec.cardinality is undefined![/magenta]",
                        (0, 0, 0, 16),
                    ),
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
                    display=Padding(
                        frontend_cardinality_desc.format(frontend_replicas_colored),
                        (0, 0, 0, 16),
                    ),
                )

        diagnostic_detail_padding = (0, 0, 0, 16)
        if broker_diagnostics:
            check_manager.add_display(
                target_name=target_brokers,
                display=Padding("\nBroker Diagnostics", (0, 0, 0, 12)),
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
                display=Padding(
                    f"Enable Metrics: [bright_blue]{diag_enable_metrics}[/bright_blue]",
                    diagnostic_detail_padding,
                ),
            )
            check_manager.add_display(
                target_name=target_brokers,
                display=Padding(
                    f"Enable Self-Check: [bright_blue]{diag_enable_selfcheck}[/bright_blue]",
                    diagnostic_detail_padding,
                ),
            )
            check_manager.add_display(
                target_name=target_brokers,
                display=Padding(
                    f"Enable Tracing: [bright_blue]{diag_enable_tracing}[/bright_blue]",
                    diagnostic_detail_padding,
                ),
            )
            check_manager.add_display(
                target_name=target_brokers,
                display=Padding(
                    f"Log Level: [cyan]{diag_loglevel}[/cyan]",
                    diagnostic_detail_padding,
                ),
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
            target_name=target_brokers,
            status=broker_eval_status,
            value=broker_eval_value,
            resource_name=broker_name,
        )

    if brokers_count > 0:
        check_manager.add_display(
            target_name=target_brokers,
            display=Padding(
                "\nRuntime Health",
                (0, 0, 0, 8),
            ),
        )

        for pod in [
            AZEDGE_DIAGNOSTICS_PROBE_PREFIX,
            AZEDGE_FRONTEND_PREFIX,
            AZEDGE_BACKEND_PREFIX,
            AZEDGE_AUTH_PREFIX
        ]:
            evaluate_pod_health(
                check_manager=check_manager,
                namespace=namespace,
                pod=pod,
                display_padding=12,
                service_label=E4K_LABEL
            )

    return check_manager.as_dict(as_list)


# Cloud connector checks
# TODO - further consolidate / pull out duplicate connector logic
def evaluate_mqtt_bridge_connectors(
    as_list: bool = False,
    namespace: Optional[str]=None,
    detail_level: str = ResourceOutputDetailLevel.summary.value,
) -> Dict[str, Any]:
    from rich.table import Table

    def add_routes_display(
        check_manager: CheckManager,
        target: str,
        routes: List[Dict[str, str]],
        padding: tuple,
    ) -> None:
        for route in routes:
            route_name = route.get("name")
            check_manager.add_display(
                target_name=target,
                display=Padding(
                    f"- Route {{[blue]{route_name}[/blue]}}",
                    padding,
                ),
            )

    def create_routes_table(routes: List[Dict[str, str]]) -> Table:
        table = Table(title="Route Details", title_justify="left", title_style="None", show_lines=True)

        columns = ["Route", "Direction", "Source/Target", "QOS"]

        for column in columns:
            table.add_column(column, justify="left", style="blue", no_wrap=False)

        for route in routes:
            table.add_row(
                f"{route.get('name')}",
                f"{route.get('direction')}",
                f"{route.get('source')} -> {route.get('target')}",
                f"{route.get('qos')}",
            )
        return table

    def display_topic_maps(
        check_manager: CheckManager,
        target: str,
        topic_maps: List[Dict[str, str]],
        detail_level: str,
        padding: tuple,
    ) -> None:
        # Show warning if no topic maps
        if not len(bridge_topic_maps):
            check_manager.add_display(
                target_name=target,
                display=Padding(
                    "[yellow]No MQTT Bridge Topic Maps reference this resource[/yellow]",
                    padding,
                ),
            )

        # topic maps that reference this bridge
        for topic_map in topic_maps:
            name = topic_map.get("metadata", {}).get("name")

            check_manager.add_display(
                target_name=target,
                display=Padding(f"- Topic Map {{[blue]{name}[/blue]}}", padding),
            )

            if detail_level != ResourceOutputDetailLevel.summary.value:
                route_padding = (0, 0, 0, padding[3] + 4)
                routes = topic_map.get("spec", {}).get("routes", [])
                if detail_level == ResourceOutputDetailLevel.verbose.value:
                    route_table = create_routes_table(routes)
                    check_manager.add_display(target_name=target, display=Padding(route_table, route_padding))
                    return
                else:
                    add_routes_display(
                        check_manager=check_manager,
                        target=target,
                        routes=routes,
                        padding=route_padding,
                    )

    def display_bridge_info(check_manager: CheckManager, target: str, bridge: Dict[str, str], detail_level: str, padding: tuple) -> None:
        # bridge resource
        bridge_metadata = bridge.get("metadata", {})
        bridge_name = bridge_metadata.get("name")

        # bridge resource status
        bridge_status = bridge.get("status", {})
        bridge_status_level = bridge_status.get("configStatusLevel", "N/A")

        bridge_eval_status = CheckTaskStatus.success.value

        if bridge_status_level in [ResourceState.error.value, ResourceState.failed.value]:
            bridge_eval_status = CheckTaskStatus.error.value
        elif bridge_status_level in [
            ResourceState.recovering.value,
            ResourceState.warn.value,
            ResourceState.starting.value,
            "N/A",
        ]:
            bridge_eval_status = CheckTaskStatus.warning.value

        check_manager.add_target_eval(
            target_name=target,
            status=bridge_eval_status,
            value=bridge_status,
            resource_name=bridge_name,
            resource_kind=E4kResourceKinds.MQTT_BRIDGE_CONNECTOR.value,
        )

        bridge_status_desc = bridge_status.get("configStatusDescription")

        bridge_status_text = f" {bridge_status_desc}" if bridge_status_desc else ""
        check_manager.add_display(
            target_name=target,
            display=Padding(
                f"\n- Bridge {{[bright_blue]{bridge_name}[/bright_blue]}} status {{{decorate_resource_status(bridge_status_level)}}}.{bridge_status_text}",
                padding,
            ),
        )

        # bridge resource instance details
        spec = bridge.get("spec", {})
        bridge_eval_status = (
            CheckTaskStatus.error.value
            if not all(
                [
                    spec.get("localBrokerConnection"),
                    spec.get("remoteBrokerConnection"),
                ]
            )
            else CheckTaskStatus.success.value
        )

        check_manager.add_target_eval(
            target_name=target,
            status=bridge_eval_status,
            value={"spec": spec},
            resource_name=bridge_name,
            resource_kind=E4kResourceKinds.MQTT_BRIDGE_CONNECTOR.value,
        )

        bridge_instances = spec.get("bridgeInstances")
        client_prefix = spec.get("clientIdPrefix")

        check_manager.add_display(
            target_name=target,
            display=Padding(
                f"Bridge instances: [bright_blue]{bridge_instances}[/bright_blue]",
                bridge_detail_padding,
            ),
        )
        check_manager.add_display(
            target_name=target,
            display=Padding(
                f"Client Prefix: [bright_blue]{client_prefix}[/bright_blue]",
                bridge_detail_padding,
            ),
        )
        # local broker endpoint
        local_broker = spec.get("localBrokerConnection", {})
        local_broker_endpoint = local_broker.get("endpoint")
        check_manager.add_display(
            target_name=target,
            display=Padding(
                f"Local Broker Connection: [bright_blue]{local_broker_endpoint}[/bright_blue]",
                bridge_detail_padding,
            ),
        )
        if detail_level != ResourceOutputDetailLevel.summary.value:
            local_broker_auth = next(iter(local_broker.get("authentication")))
            local_broker_tls = local_broker.get("tls", {}).get("tlsEnabled", False)
            check_manager.add_display(
                target_name=target,
                display=Padding(
                    f"Auth: [bright_blue]{local_broker_auth}[/bright_blue] TLS: [bright_blue]{local_broker_tls}[/bright_blue]",
                    broker_detail_padding,
                ),
            )

        # remote broker endpoint
        remote_broker = spec.get("remoteBrokerConnection", {})
        remote_broker_endpoint = remote_broker.get("endpoint")
        check_manager.add_display(
            target_name=target,
            display=Padding(
                f"Remote Broker Connection: [bright_blue]{remote_broker_endpoint}[/bright_blue]",
                bridge_detail_padding,
            ),
        )

        if detail_level != ResourceOutputDetailLevel.summary.value:
            remote_broker_auth = next(iter(remote_broker.get("authentication")))
            remote_broker_tls = remote_broker.get("tls", {}).get("tlsEnabled", False)

            check_manager.add_display(
                target_name=target,
                display=Padding(
                    f"Auth: [bright_blue]{remote_broker_auth}[/bright_blue] TLS: [bright_blue]{remote_broker_tls}[/bright_blue]",
                    broker_detail_padding,
                ),
            )

    check_manager = CheckManager(
        check_name="evalMQTTBridgeConnectors",
        check_desc="Evaluate MQTT Bridge Connectors",
    )

    # MQTT Bridge Connector checks are purely informational, so mark as skipped
    bridge_target = "mqttbridgeconnectors.az-edge.com"
    check_manager.add_target(target_name=bridge_target)

    top_level_padding = (0, 0, 0, 8)
    bridge_detail_padding = (0, 0, 0, 12)
    broker_detail_padding = (0, 0, 0, 16)

    bridge_objects: dict = E4K_ACTIVE_API.get_resources(
        kind=E4kResourceKinds.MQTT_BRIDGE_CONNECTOR
    )
    bridge_resources: List[dict] = bridge_objects.get("items", [])

    # attempt to map each topic_map to its referenced bridge
    topic_map_objects: dict = E4K_ACTIVE_API.get_resources(
        kind=E4kResourceKinds.MQTT_BRIDGE_TOPIC_MAP
    )
    topic_map_list: List[dict] = topic_map_objects.get("items", [])
    topic_maps_by_bridge = {}
    bridge_refs = {ref.get("spec", {}).get("mqttBridgeConnectorRef") for ref in topic_map_list}

    for bridge in bridge_refs:
        topic_maps_by_bridge[bridge] = [
            topic for topic in topic_map_list if topic.get("spec", {}).get("mqttBridgeConnectorRef") == bridge
        ]

    if len(bridge_resources):
        check_manager.set_target_conditions(target_name=bridge_target, conditions=["status", "valid(spec)"])

        for bridge in bridge_resources:
            bridge_metadata = bridge.get("metadata", {})
            bridge_name = bridge_metadata.get("name")
            bridge_topic_maps = topic_maps_by_bridge.get(bridge_name, [])

            display_bridge_info(
                check_manager=check_manager,
                target=bridge_target,
                bridge=bridge,
                detail_level=detail_level,
                padding=top_level_padding,
            )
            # topic maps for this specific bridge
            display_topic_maps(
                check_manager=check_manager,
                target=bridge_target,
                topic_maps=bridge_topic_maps,
                detail_level=detail_level,
                padding=bridge_detail_padding,
            )
            # remove topic map by bridge reference
            topic_maps_by_bridge.pop(bridge_name, None)
        
        _display_connector_runtime_health(
           check_manager=check_manager,
            namespace=namespace,
            target=bridge_target,
            connectors=bridge_resources
        )
    else:
        _mark_connector_target_as_skipped(
            check_manager=check_manager,
            target=bridge_target,
            message="No MQTT Bridge Connector resources detected",
            padding=top_level_padding
        )

    # warn about topic maps with invalid bridge references
    flattened_topic_maps = [key for maps in topic_maps_by_bridge.values() for key in maps]
    _display_invalid_topic_maps(
        check_manager=check_manager,
        target=bridge_target,
        topic_maps=flattened_topic_maps,
        ref_key="mqttBridgeConnectorRef",
        padding=top_level_padding
    )

    return check_manager.as_dict(as_list)


def evaluate_datalake_connectors(
    namespace: Optional[str] = None,
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
) -> Dict[str, Any]:
    from rich.table import Table

    def create_schema_table(name: str, schema: List[Dict[str, str]]) -> Table:
        table = Table(title="Topic Map Schema", title_justify="left")

        columns = [
            {"name": "Name", "style": "white"},
            {"name": "Mapping", "style": "white"},
            {"name": "Format", "style": "white"},
            {"name": "Optional", "style": "white"},
        ]

        for column in columns:
            table.add_column(column["name"], justify="left", style=column["style"], no_wrap=True)

        for value in schema:
            table.add_row(
                f"{value['name']}",
                f"{value['mapping']}",
                f"{value['format']}",
                f"{value['optional']}",
            )
        return table

    def display_topic_maps(
        check_manager: CheckManager,
        target: str,
        topic_maps: List[Dict[str, str]],
        detail_level: str,
        padding: tuple,
    ) -> None:
        # Show warning if no topic maps
        if not len(connector_topic_maps):
            check_manager.add_display(
                target_name=target,
                display=Padding(
                    "[yellow]No Data Lake Connector Topic Maps reference this resource[/yellow]",
                    padding,
                ),
            )
            return

        for topic_map in topic_maps:
            topic_name = topic_map.get("metadata", {}).get("name")
            check_manager.add_display(
                target_name=target,
                display=Padding(
                    f"- Topic Map {{[bright_blue]{topic_name}[/bright_blue]}}",
                    padding,
                ),
            )
            if detail_level != ResourceOutputDetailLevel.summary.value:
                topic_spec = topic_map.get("spec", {})
                topic_mapping = topic_spec.get("mapping", {})
                max_msg_per_batch = topic_mapping.get("maxMessagesPerBatch")
                msg_payload_type = topic_mapping.get("messagePayloadType")
                source_topic = topic_mapping.get("mqttSourceTopic")
                qos = topic_mapping.get("qos")

                delta_table = topic_mapping.get("deltaTable", {})
                table_name = delta_table.get("tableName")

                detail_padding = (0, 0, 0, padding[3] + 4)
                for row in [
                    ["Table Name", table_name],
                    ["Max Messages Per Batch", max_msg_per_batch],
                    ["Message Payload Type", msg_payload_type],
                    ["MQTT Source Topic", source_topic],
                    ["QOS", qos],
                ]:
                    check_manager.add_display(
                        target_name=target,
                        display=Padding(
                            f"- {row[0]}: [bright_blue]{row[1]}[/bright_blue]",
                            detail_padding,
                        ),
                    )
                if detail_level == ResourceOutputDetailLevel.verbose.value:
                    delta_table = topic_mapping.get("deltaTable", {})
                    schema = delta_table.get("schema", [])
                    route_table = create_schema_table(topic_name, schema)
                    check_manager.add_display(target_name=target, display=Padding(route_table, padding))

    def display_connector_info(
        check_manager: CheckManager,
        target: str,
        connector: Dict[str, str],
        detail_level: str,
        padding: tuple,
    ) -> None:
        # connector resource status
        connector_status = connector.get("status", {})
        connector_status_level = connector_status.get("configStatusLevel", "N/A")

        connector_eval_status = CheckTaskStatus.success.value

        if connector_status_level in [ResourceState.error.value, ResourceState.failed.value]:
            connector_eval_status = CheckTaskStatus.error.value
        elif connector_status_level in [
            ResourceState.recovering.value,
            ResourceState.warn.value,
            ResourceState.starting.value,
            "N/A",
        ]:
            connector_eval_status = CheckTaskStatus.warning.value

        check_manager.add_target_eval(
            target_name=target,
            status=connector_eval_status,
            value=connector_status,
            resource_name=connector_name,
            resource_kind=E4kResourceKinds.DATALAKE_CONNECTOR.value,
        )

        connector_status_desc = connector_status.get("configStatusDescription")
        connector_status_text = f" {connector_status_desc}" if connector_status_desc else ""

        check_manager.add_display(
            target_name=target,
            display=Padding(
                f"\n- Connector {{[bright_blue]{connector_name}[/bright_blue]}} status {{{decorate_resource_status(connector_status_level)}}}.{connector_status_text}",
                padding,
            ),
        )
        detail_padding = (0, 0, 0, padding[3] + 4)
        spec = connector.get("spec", {})
        connector_eval_status = connector_eval_status = (
            CheckTaskStatus.error.value
            if not all(
                [
                    spec.get("target", {}).get("datalakeStorage", {}).get("endpoint"),
                    spec.get("instances"),
                ]
            )
            else CheckTaskStatus.success.value
        )
        check_manager.add_target_eval(
            target_name=target,
            status=connector_eval_status,
            value={"spec": spec},
            resource_name=connector_name,
            resource_kind=E4kResourceKinds.DATALAKE_CONNECTOR.value,
        )
        connector_instances = spec.get("instances")

        # connector target
        datalake_target = spec.get("target", {}).get("datalakeStorage", {})
        datalake_endpoint = datalake_target.get("endpoint")
        check_manager.add_display(
            target_name=target,
            display=Padding(
                f"Connector instances: [bright_blue]{connector_instances}[/bright_blue]",
                detail_padding,
            ),
        )
        check_manager.add_display(
            target_name=target,
            display=Padding(
                f"Target endpoint: [bright_blue]{datalake_endpoint}[/bright_blue]",
                detail_padding,
            ),
        )

    check_manager = CheckManager(
        check_name="evalDataLakeConnectors",
        check_desc="Evaluate Data Lake Connectors",
    )

    # These checks are purely informational, so mark as skipped
    connector_target = "datalakeconnectors.az-edge.com"
    check_manager.add_target(target_name=connector_target)

    top_level_padding = (0, 0, 0, 8)
    connector_detail_padding = (0, 0, 0, 12)

    connector_resources: dict = E4K_ACTIVE_API.get_resources(
        kind=E4kResourceKinds.DATALAKE_CONNECTOR, namespace=namespace
    )
    connectors: List[dict] = connector_resources.get("items", [])

    # attempt to map each topic_map to its referenced connector
    topic_map_objects: dict = E4K_ACTIVE_API.get_resources(
        kind=E4kResourceKinds.DATALAKE_CONNECTOR_TOPIC_MAP, namespace=namespace
    )
    topic_map_list: List[dict] = topic_map_objects.get("items", [])
    topic_maps_by_connector = {}
    connector_refs = {ref.get("spec", {}).get("dataLakeConnectorRef") for ref in topic_map_list}

    for connector in connector_refs:
        topic_maps_by_connector[connector] = [
            topic for topic in topic_map_list if topic.get("spec", {}).get("dataLakeConnectorRef") == connector
        ]

    if len(connectors):
        check_manager.set_target_conditions(
            target_name=connector_target,
            conditions=["status", "valid(spec)", "len(spec.instances)>=1"],
        )
        for connector in connectors:
            # connector resource
            connector_metadata = connector.get("metadata", {})
            connector_name = connector_metadata.get("name")
            connector_topic_maps = topic_maps_by_connector.get(connector_name, [])

            display_connector_info(
                check_manager=check_manager,
                target=connector_target,
                connector=connector,
                detail_level=detail_level,
                padding=top_level_padding,
            )
            display_topic_maps(
                check_manager=check_manager,
                target=connector_target,
                topic_maps=connector_topic_maps,
                detail_level=detail_level,
                padding=connector_detail_padding,
            )
            # remove all topic maps for this connector
            topic_maps_by_connector.pop(connector_name, None)
    else:
        _mark_connector_target_as_skipped(
            check_manager=check_manager,
            target=connector_target,
            message="No Data Lake Connector resources detected",
            padding=top_level_padding
        )

    # warn about topic maps with invalid references
    flattened_topic_maps = [key for maps in topic_maps_by_connector.values() for key in maps]
    _display_invalid_topic_maps(
        check_manager=check_manager,
        target=connector_target,
        topic_maps=flattened_topic_maps,
        ref_key="dataLakeConnectorRef",
        padding=top_level_padding
    )
    # evaluate resource health
    _display_connector_runtime_health(
        check_manager=check_manager,
        namespace=namespace,
        target=connector_target,
        connectors=connectors
    )

    return check_manager.as_dict(as_list)


def evaluate_kafka_connectors(
    namespace: Optional[str] = None,
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
):
    def display_connector_info(check_manager: CheckManager, target: str, connector: Dict[str, Any], detail_level: str, padding: tuple):
        metadata = connector.get("metadata", {})
        connector_name = metadata.get("name")
        connector_status = connector.get("status", {})
        connector_status_level = connector_status.get("configStatusLevel", "N/A")
        eval_status = CheckTaskStatus.success.value

        if connector_status_level in [ResourceState.error.value, ResourceState.failed.value]:
            eval_status = CheckTaskStatus.error.value
        elif connector_status_level in [
            ResourceState.recovering.value,
            ResourceState.warn.value,
            ResourceState.starting.value,
            "N/A",
        ]:
            eval_status = CheckTaskStatus.warning.value

        check_manager.add_target_eval(
            target_name=target,
            status=eval_status,
            value=connector_status,
            resource_name=connector_name,
            resource_kind=E4kResourceKinds.KAFKA_CONNECTOR.value,
        )

        connector_status_desc = connector_status.get("statusDescription")

        connector_status_text = f" {connector_status_desc}" if connector_status_desc else ""
        check_manager.add_display(
            target_name=target,
            display=Padding(
                f"\n- Connector {{[bright_blue]{connector_name}[/bright_blue]}} status {{{decorate_resource_status(connector_status_level)}}}.{connector_status_text}",
                padding,
            ),
        )

        spec = connector.get("spec", {})

        clientIdPrefix = spec.get("clientIdPrefix")
        instances = spec.get("instances")
        logLevel = spec.get("logLevel")

        local_broker = spec.get("localBrokerConnection", {})
        kafka_broker = spec.get("kafkaConnection", {})

        connector_eval_status = (
            CheckTaskStatus.error.value
            if not all(
                [
                    clientIdPrefix,
                    instances,
                    local_broker,
                    kafka_broker,
                ]
            )
            else CheckTaskStatus.success.value
        )

        detail_padding = (0, 0, 0, padding[3] + 4)

        check_manager.add_target_eval(
            target_name=target,
            status=connector_eval_status,
            value={"spec": spec},
            resource_name=connector_name,
            resource_kind=E4kResourceKinds.KAFKA_CONNECTOR.value,
        )

        check_manager.add_display(
            target_name=target,
            display=Padding(f"Client ID Prefix: [bright_blue]{clientIdPrefix}[/bright_blue]", detail_padding),
        )
        check_manager.add_display(
            target_name=target, display=Padding(f"Instances: [bright_blue]{instances}[/bright_blue]", detail_padding)
        )

        broker_detail_padding = (0, 0, 0, detail_padding[3] + 4)

        # local broker endpoint
        local_broker_endpoint = local_broker.get("endpoint")
        check_manager.add_display(
            target_name=target,
            display=Padding(
                f"Local Broker Connection: [bright_blue]{local_broker_endpoint}[/bright_blue]",
                detail_padding,
            ),
        )
        if detail_level != ResourceOutputDetailLevel.summary.value:
            local_broker_auth = next(iter(local_broker.get("authentication", {})))
            local_broker_tls = local_broker.get("tls", {}).get("tlsEnabled", False)

            check_manager.add_display(
                target_name=target,
                display=Padding(
                    f"Auth: [bright_blue]{local_broker_auth}[/bright_blue] TLS: [bright_blue]{local_broker_tls}[/bright_blue]",
                    broker_detail_padding,
                ),
            )
            check_manager.add_display(
                target_name=target, display=Padding(f"logLevel: [bright_blue]{logLevel}[/bright_blue]", detail_padding)
            )

        # kafka endpoint
        kafka_broker_endpoint = kafka_broker.get("endpoint")
        check_manager.add_display(
            target_name=target,
            display=Padding(
                f"Remote Broker Connection: [bright_blue]{kafka_broker_endpoint}[/bright_blue]",
                detail_padding,
            ),
        )
        if detail_level != ResourceOutputDetailLevel.summary.value:
            kafka_broker_auth = next(iter(kafka_broker.get("authentication", {})))
            kafka_broker_tls = kafka_broker.get("tls", {}).get("tlsEnabled", False)

            check_manager.add_display(
                target_name=target,
                display=Padding(
                    f"Auth: [bright_blue]{kafka_broker_auth}[/bright_blue] TLS: [bright_blue]{kafka_broker_tls}[/bright_blue]",
                    broker_detail_padding,
                ),
            )

    def display_topic_maps(check_manager: CheckManager, target: str, topic_maps: List[Dict[str, Any]], detail_level: str, padding: tuple):
        # Show warning if no topic maps
        if not len(connector_topic_maps):
            check_manager.add_display(
                target_name=target,
                display=Padding(
                    "[yellow]No Kafka Topic Maps reference this resource[/yellow]",
                    padding,
                ),
            )
            return
        for topic_map in topic_maps:
            topic_name = topic_map.get("metadata", {}).get("name")
            check_manager.add_display(
                target_name=target,
                display=Padding(
                    f"- Topic Map {{[bright_blue]{topic_name}[/bright_blue]}}",
                    padding,
                ),
            )

            if detail_level != ResourceOutputDetailLevel.summary.value:
                detail_padding = (0, 0, 0, padding[3] + 4)
                spec = topic_map.get("spec", {})

                for label, key in [
                    ("Compression", "compression"),
                    ("Partition Key", "partitionKeyProperty"),
                    ("Partition Strategy", "partitionStrategy"),
                ]:
                    val = spec.get(key)

                    check_manager.add_display(
                        target_name=target,
                        display=Padding(
                            f"{label}: [bright_blue]{val}[/bright_blue]",
                            detail_padding,
                        ),
                    )

                if detail_level == ResourceOutputDetailLevel.verbose.value:
                    check_manager.add_display(
                        target_name=target,
                        display=Padding(
                            "Batching:",
                            detail_padding
                        )
                    )
                    batch_detail_padding = (0, 0, 0, detail_padding[3] + 4)
                    batching = spec.get("batching", {})
                    for label, key in [
                        ("Enabled", "enabled"),
                        ("Latency (ms)", "latencyMs"),
                        ("Max bytes", "maxBytes"),
                        ("Max messages", "maxMessages"),
                    ]:
                        val = batching.get(key)
                        check_manager.add_display(
                            target_name=target,
                            display=Padding(
                                f"{label}: [bright_blue]{val}[/bright_blue]",
                                batch_detail_padding,
                            ),
                        )

                display_routes(
                    check_manager=check_manager, target=target, routes=spec.get("routes", []), detail_level=detail_level, padding=detail_padding
                )

    def display_routes(check_manager: CheckManager, target: str, routes: List[Dict[str, str]], detail_level: str, padding: tuple):
        for route in routes:
            # route key is mqttToKafka | kafkaToMqtt
            route_type = next(iter(route))
            route_details = route[route_type]

            # shared properties
            name = route_details.get("name")
            check_manager.add_display(
                target_name=target,
                display=Padding(
                    f"- Route: {{[bright_blue]{name}[/bright_blue]}}",
                    padding,
                ),
            )

            # route details are verbose
            # TODO - table output?
            if detail_level == ResourceOutputDetailLevel.verbose.value:
                route_detail_padding = (0, 0, 0, padding[3] + 4)

                kafkaTopic = route_details.get("kafkaTopic")
                mqttTopic = route_details.get("mqttTopic")
                qos = route_details.get("qos")

                check_manager.add_display(
                    target_name=target,
                    display=Padding(
                        f"Kafka topic: [bright_blue]{kafkaTopic}[/bright_blue]",
                        route_detail_padding,
                    ),
                )
                check_manager.add_display(
                    target_name=target,
                    display=Padding(
                        f"MQTT Topic: [bright_blue]{mqttTopic}[/bright_blue]",
                        route_detail_padding,
                    ),
                )
                check_manager.add_display(
                    target_name=target,
                    display=Padding(
                        f"QOS: [bright_blue]{qos}[/bright_blue]",
                        route_detail_padding,
                    ),
                )
                if route_type == KafkaTopicMapRouteType.mqtt_to_kafka.value:
                    kafkaAcks = route_details.get("kafkaAcks")
                    sharedSubscription = route_details.get("sharedSubscription", {})
                    groupName = sharedSubscription.get("groupName")
                    groupMinimumShareNumber = sharedSubscription.get("groupMinimumShareNumber")

                    check_manager.add_display(
                        target_name=target,
                        display=Padding(
                            f"Kafka Acks: [bright_blue]{kafkaAcks}[/bright_blue]",
                            route_detail_padding,
                        ),
                    )
                    check_manager.add_display(
                        target_name=target,
                        display=Padding(
                            f"Shared Subscription Group Name: [bright_blue]{groupName}[/bright_blue]",
                            route_detail_padding,
                        ),
                    )
                    check_manager.add_display(
                        target_name=target,
                        display=Padding(
                            f"Shared Subscription Group Minimum Share: [bright_blue]{groupMinimumShareNumber}[/bright_blue]",
                            route_detail_padding,
                        ),
                    )
                else:
                    consumerGroupId = route_details.get("consumerGroupId")
                    check_manager.add_display(
                        target_name=target,
                        display=Padding(
                            f"Consumer Group ID: [bright_blue]{consumerGroupId}[/bright_blue]",
                            route_detail_padding,
                        ),
                    )

    check_manager = CheckManager(
        check_name="evalKafkaConnectors",
        check_desc="Evaluate Kafka Connectors",
    )

    connector_padding = (0, 0, 0, 8)
    topic_map_padding = (0, 0, 0, 12)

    # These checks are purely informational, so mark as skipped
    connector_target = "kafkaconnectors.az-edge.com"
    check_manager.add_target(target_name=connector_target)

    connector_objects: dict = E4K_ACTIVE_API.get_resources(kind=E4kResourceKinds.KAFKA_CONNECTOR, namespace=namespace)
    connector_resources: List[dict] = connector_objects.get("items", [])

    topic_map_objects: dict = E4K_ACTIVE_API.get_resources(
        kind=E4kResourceKinds.KAFKA_CONNECTOR_TOPIC_MAP, namespace=namespace
    )

    topic_map_list: List[dict] = topic_map_objects.get("items", [])

    connector_refs = {ref.get("spec", {}).get("kafkaConnectorRef") for ref in topic_map_list}

    topic_maps_by_connector = {}
    for connector in connector_refs:
        topic_maps_by_connector[connector] = [
            topic for topic in topic_map_list if topic.get("spec", {}).get("kafkaConnectorRef") == connector
        ]

    if len(connector_resources):
        check_manager.set_target_conditions(target_name=connector_target, conditions=["status", "valid(spec)"])

        for connector in connector_resources:
            connector_metadata = connector.get("metadata", {})
            connector_name = connector_metadata.get("name")
            connector_topic_maps = topic_maps_by_connector.get(connector_name, [])
            display_connector_info(
                check_manager=check_manager,
                target=connector_target,
                connector=connector,
                detail_level=detail_level,
                padding=connector_padding
            )
            display_topic_maps(
                check_manager=check_manager,
                target=connector_target,
                topic_maps=connector_topic_maps,
                detail_level=detail_level,
                padding=topic_map_padding,
            )
            # remove all topic maps for this connector
            topic_maps_by_connector.pop(connector_name, None)
    else:
        _mark_connector_target_as_skipped(
            check_manager=check_manager,
            target=connector_target,
            message="No Kafka Connector resources detected",
            padding=connector_padding
        )

    flattened_topic_maps = [key for maps in topic_maps_by_connector.values() for key in maps]
    _display_invalid_topic_maps(
        check_manager=check_manager,
        target=connector_target,
        topic_maps=flattened_topic_maps,
        ref_key="kafkaConnectorRef",
        padding=connector_padding
    )
    _display_connector_runtime_health(
        check_manager=check_manager,
        namespace=namespace,
        target=connector_target,
        connectors=connector_resources
    )

    return check_manager.as_dict(as_list)


def _get_valid_references(kind: Union[Enum, str], namespace: Optional[str] = None) -> Dict[str, Any]:
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


def _display_connector_runtime_health(
    check_manager: CheckManager,
    namespace: str,
    target: str,
    connectors: Optional[List[Dict[str, Any]]] = None,
    prefix: str = 'azedge-',
    padding: int = 8
):
    if connectors:
        check_manager.add_display(
            target_name=target,
            display=Padding(
                "\nRuntime Health",
                (0, 0, 0, padding),
            ),
        )
        padding += 4
        pod_name_prefixes = [f"{prefix}{connector['metadata']['name']}" for connector in connectors]
        for pod in pod_name_prefixes:
            evaluate_pod_health(
                check_manager=check_manager,
                namespace=namespace,
                pod=pod,
                display_padding=padding,
                service_label=E4K_LABEL
            )


def _display_invalid_topic_maps(
    check_manager: CheckManager,
    target: str,
    topic_maps: List[Dict[str, Any]],
    ref_key: str,
    padding: tuple
):
    for map in topic_maps:
        name = map.get("metadata", {}).get("name")
        ref = map.get("spec", {}).get(ref_key)
        check_manager.add_display(
            target_name=target,
            display=Padding(
                f"\nTopic map {{[red]{name}[/red]}}"
                f" references invalid connector {{[red]{ref}[/red]}}.",
                padding
            )
        )


def _mark_connector_target_as_skipped(check_manager: CheckManager, target: str, message: str, padding: int = 8):
    check_manager.add_target_eval(
        target_name=target,
        status=CheckTaskStatus.skipped.value,
        value=message,
    )
    check_manager.set_target_status(target_name=target, status=CheckTaskStatus.skipped.value)
    check_manager.add_display(target_name=target, display=Padding(message, padding))
