# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Any, Dict, List, Optional, Union
from enum import Enum

from azext_edge.edge.providers.check.cloud_connectors import process_cloud_connector
from .base import (
    CheckManager,
    decorate_resource_status,
    check_post_deployment,
    evaluate_pod_health,
    get_resource_name,
    get_resources_by_name,
    resources_grouped_by_namespace
)

from rich.console import NewLine
from rich.padding import Padding

from ...common import (
    AIO_MQ_DIAGNOSTICS_SERVICE,
    CheckTaskStatus,
    ResourceState,
)

from .common import (
    AIO_MQ_DIAGNOSTICS_PROBE_PREFIX,
    AIO_MQ_FRONTEND_PREFIX,
    AIO_MQ_BACKEND_PREFIX,
    AIO_MQ_AUTH_PREFIX,
    KafkaTopicMapRouteType,
    ResourceOutputDetailLevel,
)

from ...providers.edge_api import (
    MQ_ACTIVE_API,
    MqResourceKinds
)
from ..support.mq import MQ_LABEL

from ..base import get_namespaced_service


def check_mq_deployment(
    result: Dict[str, Any],
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_kinds: List[str] = None,
    resource_name: str = None,
) -> None:
    evaluate_funcs = {
        MqResourceKinds.BROKER: evaluate_brokers,
        MqResourceKinds.BROKER_LISTENER: evaluate_broker_listeners,
        MqResourceKinds.DIAGNOSTIC_SERVICE: evaluate_diagnostics_service,
        MqResourceKinds.MQTT_BRIDGE_CONNECTOR: evaluate_mqtt_bridge_connectors,
        MqResourceKinds.DATALAKE_CONNECTOR: evaluate_datalake_connectors,
        MqResourceKinds.KAFKA_CONNECTOR: evaluate_kafka_connectors,
    }

    check_post_deployment(
        api_info=MQ_ACTIVE_API,
        check_name="enumerateMqApi",
        check_desc="Enumerate MQ API resources",
        result=result,
        resource_kinds_enum=MqResourceKinds,
        evaluate_funcs=evaluate_funcs,
        as_list=as_list,
        detail_level=detail_level,
        resource_kinds=resource_kinds,
        resource_name=resource_name,
    )


def evaluate_diagnostics_service(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_name: str = None,
) -> Dict[str, Any]:
    check_manager = CheckManager(
        check_name="evalBrokerDiag",
        check_desc="Evaluate MQ Diagnostics Service",
    )
    all_diagnostic_services = get_resources_by_name(
        api_info=MQ_ACTIVE_API,
        kind=MqResourceKinds.DIAGNOSTIC_SERVICE,
        resource_name=resource_name,
    )
    target_diagnostic_service = "diagnosticservices.mq.iotoperations.azure.com"

    if not all_diagnostic_services:
        status = CheckTaskStatus.skipped.value if resource_name else CheckTaskStatus.error.value
        fetch_diagnostics_services_error = f"Unable to fetch {MqResourceKinds.DIAGNOSTIC_SERVICE.value}s in any namespace."
        check_manager.add_target(
            target_name=target_diagnostic_service
        )
        check_manager.add_target_eval(
            target_name=target_diagnostic_service,
            status=status,
            value=fetch_diagnostics_services_error,
        )
        check_manager.add_display(
            target_name=target_diagnostic_service,
            display=Padding(fetch_diagnostics_services_error, (0, 0, 0, 8)),
        )
        return check_manager.as_dict(as_list)

    for (namespace, diagnostic_services) in resources_grouped_by_namespace(all_diagnostic_services):
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
                (0, 0, 0, 8)
            )
        )
        diagnostic_services = list(diagnostic_services)
        diagnostic_service_count = len(diagnostic_services)
        diagnostics_count_text = "- Expecting [bright_blue]1[/bright_blue] diagnostics service resource per namespace. {}."

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

        for diag_service_resource in diagnostic_services:
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
                if detail_level != ResourceOutputDetailLevel.summary.value:
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

            target_service_deployed = f"service/{AIO_MQ_DIAGNOSTICS_SERVICE}"
            check_manager.add_target(target_name=target_service_deployed, namespace=namespace, conditions=["spec.clusterIP", "spec.ports"])
            check_manager.add_display(
                target_name=target_service_deployed,
                namespace=namespace,
                display=Padding(
                    "Service Status",
                    (0, 0, 0, 8),
                ),
            )

            diagnostics_service = get_namespaced_service(name=AIO_MQ_DIAGNOSTICS_SERVICE, namespace=namespace, as_dict=True)
            if not diagnostics_service:
                check_manager.add_target_eval(
                    target_name=target_service_deployed,
                    namespace=namespace,
                    status=CheckTaskStatus.error.value,
                    value=None,
                )
                diag_service_desc_suffix = "[red]not detected[/red]."
                diag_service_desc = (
                    f"Service {{[bright_blue]{AIO_MQ_DIAGNOSTICS_SERVICE}[/bright_blue]}} {diag_service_desc_suffix}"
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
                    f"Service {{[bright_blue]{AIO_MQ_DIAGNOSTICS_SERVICE}[/bright_blue]}} {diag_service_desc_suffix}"
                )
                check_manager.add_display(
                    target_name=target_service_deployed,
                    namespace=namespace,
                    display=Padding(
                        diag_service_desc,
                        (0, 0, 0, 12),
                    ),
                )
                if ports and detail_level != ResourceOutputDetailLevel.summary.value:
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
                    target=target_service_deployed,
                    pod=AIO_MQ_DIAGNOSTICS_SERVICE,
                    display_padding=12,
                    service_label=MQ_LABEL
                )

    return check_manager.as_dict(as_list)


def evaluate_broker_listeners(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_name: str = None,
) -> Dict[str, Any]:
    check_manager = CheckManager(
        check_name="evalBrokerListeners",
        check_desc="Evaluate MQ broker listeners",
    )

    target_listeners = "brokerlisteners.mq.iotoperations.azure.com"
    listener_conditions = [
        "len(brokerlisteners)>=1",
        "spec",
        "valid(spec.brokerRef)",
        "spec.serviceName",
        "status",
    ]

    # all_listeners = MQ_ACTIVE_API.get_resources(MqResourceKinds.BROKER_LISTENER).get("items", [])
    all_listeners = get_resources_by_name(
        api_info=MQ_ACTIVE_API,
        kind=MqResourceKinds.BROKER_LISTENER,
        resource_name=resource_name,
    )
    if not all_listeners:
        status = CheckTaskStatus.skipped.value if resource_name else CheckTaskStatus.error.value
        fetch_listeners_error_text = f"Unable to fetch {MqResourceKinds.BROKER_LISTENER.value}s in any namespace."
        check_manager.add_target(
            target_name=target_listeners
        )
        check_manager.add_target_eval(
            target_name=target_listeners,
            status=status,
            value=fetch_listeners_error_text,
        )
        check_manager.add_display(
            target_name=target_listeners,
            display=Padding(fetch_listeners_error_text, (0, 0, 0, 8)),
        )
        return check_manager.as_dict(as_list)

    for (namespace, listeners) in resources_grouped_by_namespace(all_listeners):
        valid_broker_refs = _get_valid_references(kind=MqResourceKinds.BROKER, namespace=namespace)

        check_manager.add_target(
            target_name=target_listeners,
            namespace=namespace,
            conditions=listener_conditions,
        )
        check_manager.add_display(
            target_name=target_listeners,
            namespace=namespace,
            display=Padding(
                f"Broker Listeners in namespace {{[purple]{namespace}[/purple]}}",
                (0, 0, 0, 8)
            )
        )

        listeners = list(listeners)
        listeners_count = len(listeners)
        listener_count_desc = "- Expecting [bright_blue]>=1[/bright_blue] broker listeners per namespace. {}"
        listeners_eval_status = CheckTaskStatus.success.value

        if listeners_count >= 1:
            listener_count_desc = listener_count_desc.format(f"[green]Detected {listeners_count}[/green].")
        else:
            listener_count_desc = listener_count_desc.format(f"[yellow]Detected {listeners_count}[/yellow].")
            check_manager.set_target_status(target_name=target_listeners, namespace=namespace, status=CheckTaskStatus.warning.value)
            # TODO listeners_eval_status = CheckTaskStatus.warning.value
        check_manager.add_display(target_name=target_listeners, namespace=namespace, display=Padding(listener_count_desc, (0, 0, 0, 8)))

        processed_services = {}
        for listener in listeners:
            namespace: str = namespace or listener["metadata"]["namespace"]
            listener_name: str = listener["metadata"]["name"]
            listener_spec = listener['spec']
            listener_spec_service_name: str = listener_spec["serviceName"]
            listener_spec_service_type: str = listener_spec["serviceType"]
            listener_broker_ref: str = listener_spec["brokerRef"]

            listener_eval_value = {}
            listener_eval_value["spec"] = listener_spec

            if listener_broker_ref not in valid_broker_refs:
                ref_display = f"[red]Invalid[/red] broker reference {{[red]{listener_broker_ref}[/red]}}."
                listeners_eval_status = CheckTaskStatus.error.value
                listener_eval_value["valid(spec.brokerRef)"] = False
            else:
                ref_display = f"[green]Valid[/green] broker reference {{[green]{listener_broker_ref}[/green]}}."
                listener_eval_value["valid(spec.brokerRef)"] = True

            listener_desc = f"\n- Broker Listener {{[bright_blue]{listener_name}[/bright_blue]}}. {ref_display}"
            check_manager.add_display(target_name=target_listeners, namespace=namespace, display=Padding(listener_desc, (0, 0, 0, 8)))
            if detail_level != ResourceOutputDetailLevel.summary.value:
                for (label, val) in [
                    ("Port", 'port'),
                    ("AuthN enabled", 'authenticationEnabled'),
                    ("AuthZ enabled", 'authorizationEnabled')
                ]:
                    check_manager.add_display(
                        target_name=target_listeners,
                        namespace=namespace,
                        display=Padding(
                            f"{label}: [bright_blue]{listener_spec.get(val)}[/bright_blue]",
                            (0, 0, 0, 12),
                        ),
                    )
                node_port = listener_spec.get("nodePort")
                if node_port:
                    check_manager.add_display(
                        target_name=target_listeners,
                        namespace=namespace,
                        display=Padding(
                            f"Node Port: [bright_blue]{node_port}[/bright_blue]",
                            (0, 0, 0, 12),
                        ),
                    )

            if listener_spec_service_name not in processed_services:
                target_listener_service = f"service/{listener_spec_service_name}"
                listener_service_eval_status = CheckTaskStatus.success.value
                check_manager.add_target(target_name=target_listener_service, namespace=namespace)

                associated_service: dict = get_namespaced_service(
                    name=listener_spec_service_name, namespace=namespace, as_dict=True
                )
                processed_services[listener_spec_service_name] = True
                if not associated_service:
                    listener_service_eval_status = CheckTaskStatus.warning.value
                    check_manager.add_display(
                        target_name=target_listeners,
                        namespace=namespace,
                        display=Padding(
                            f"\n[red]Unable[/red] to fetch service {{[red]{listener_spec_service_name}[/red]}}.",
                            (0, 0, 0, 12),
                        ),
                    )
                    check_manager.add_target_eval(
                        target_name=target_listener_service,
                        namespace=namespace,
                        status=listener_service_eval_status,
                        value="Unable to fetch service.",
                    )
                else:
                    check_manager.add_display(
                        target_name=target_listener_service,
                        namespace=namespace,
                        display=Padding(
                            f"Service {{[bright_blue]{listener_spec_service_name}[/bright_blue]}} of type [bright_blue]{listener_spec_service_type}[/bright_blue]",
                            (0, 0, 0, 8),
                        ),
                    )
                    if detail_level != ResourceOutputDetailLevel.summary.value:
                        if listener_spec_service_type.lower() == "loadbalancer":
                            check_manager.set_target_conditions(
                                target_name=target_listener_service,
                                namespace=namespace,
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
                                namespace=namespace,
                                display=Padding(
                                    ingress_rules_desc.format(ingress_count_colored),
                                    (0, 0, 0, 12),
                                ),
                            )

                            if ingress_rules:
                                check_manager.add_display(
                                    target_name=target_listener_service,
                                    namespace=namespace,
                                    display=Padding("\nIngress", (0, 0, 0, 12)),
                                )

                            for ingress in ingress_rules:
                                ip = ingress.get("ip")
                                if ip:
                                    rule_desc = f"- ip: [green]{ip}[/green]"
                                    check_manager.add_display(
                                        target_name=target_listener_service,
                                        namespace=namespace,
                                        display=Padding(rule_desc, (0, 0, 0, 16)),
                                    )
                                else:
                                    listener_service_eval_status = CheckTaskStatus.warning.value

                            check_manager.add_target_eval(
                                target_name=target_listener_service,
                                namespace=namespace,
                                status=listener_service_eval_status,
                                value=service_status,
                            )

                        if listener_spec_service_type.lower() == "clusterip":
                            check_manager.set_target_conditions(
                                target_name=target_listener_service,
                                namespace=namespace,
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
                                namespace=namespace,
                                display=Padding(cluster_ip_desc, (0, 0, 0, 12)),
                            )
                            check_manager.add_target_eval(
                                target_name=target_listener_service,
                                namespace=namespace,
                                status=listener_service_eval_status,
                                value={"spec.clusterIP": cluster_ip},
                            )

                        if listener_spec_service_type.lower() == "nodeport":
                            pass

            check_manager.add_target_eval(
                target_name=target_listeners,
                namespace=namespace,
                status=listeners_eval_status,
                value=listener_eval_value,
                resource_name=listener_name,
            )

    return check_manager.as_dict(as_list)


def evaluate_brokers(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_name: str = None,
) -> Dict[str, Any]:
    check_manager = CheckManager(check_name="evalBrokers", check_desc="Evaluate MQ brokers")

    target_brokers = "brokers.mq.iotoperations.azure.com"
    broker_conditions = ["len(brokers)==1", "status", "spec.mode"]
    all_brokers: dict = get_resources_by_name(
        api_info=MQ_ACTIVE_API,
        kind=MqResourceKinds.BROKER,
        resource_name=resource_name,
    )

    if not all_brokers:
        status = CheckTaskStatus.skipped.value if resource_name else CheckTaskStatus.error.value
        fetch_brokers_error_text = f"Unable to fetch {MqResourceKinds.BROKER.value}s in any namespace."
        check_manager.add_target(
            target_name=target_brokers
        )
        check_manager.add_target_eval(
            target_name=target_brokers,
            status=status,
            value=fetch_brokers_error_text,
        )
        check_manager.add_display(
            target_name=target_brokers,
            display=Padding(fetch_brokers_error_text, (0, 0, 0, 8)),
        )
        return check_manager.as_dict(as_list)

    for (namespace, brokers) in resources_grouped_by_namespace(all_brokers):
        check_manager.add_target(target_name=target_brokers, namespace=namespace, conditions=broker_conditions)
        check_manager.add_display(
            target_name=target_brokers,
            namespace=namespace,
            display=Padding(
                f"MQ Brokers in namespace {{[purple]{namespace}[/purple]}}",
                (0, 0, 0, 8)
            )
        )
        brokers = list(brokers)
        brokers_count = len(brokers)
        brokers_count_text = "- Expecting [bright_blue]1[/bright_blue] broker resource per namespace. {}."
        broker_eval_status = CheckTaskStatus.success.value

        if brokers_count == 1:
            brokers_count_text = brokers_count_text.format(f"[green]Detected {brokers_count}[/green]")
        else:
            brokers_count_text = brokers_count_text.format(f"[red]Detected {brokers_count}[/red]")
            check_manager.set_target_status(target_name=target_brokers, namespace=namespace, status=CheckTaskStatus.error.value)
        check_manager.add_display(target_name=target_brokers, namespace=namespace, display=Padding(brokers_count_text, (0, 0, 0, 8)))

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
                namespace=namespace,
                display=Padding(target_broker_text, (0, 0, 0, 8)),
            )

            broker_eval_value = {"status": {"status": broker_status, "statusDescription": broker_status_desc}}
            broker_eval_status = _calculate_connector_status(broker_status)

            check_manager.add_display(
                target_name=target_brokers,
                namespace=namespace,
                display=Padding(status_display_text, (0, 0, 0, 12)),
            )

            if broker_mode == "distributed":
                if not added_distributed_conditions:
                    # TODO - conditional evaluations
                    broker_conditions.append("spec.cardinality")
                    broker_conditions.append("spec.cardinality.backendChain.partitions>=1")
                    broker_conditions.append("spec.cardinality.backendChain.redundancyFactor>=1")
                    broker_conditions.append("spec.cardinality.backendChain.workers>=1")
                    broker_conditions.append("spec.cardinality.frontend.replicas>=1")
                    added_distributed_conditions = True

                check_manager.set_target_conditions(target_name=target_brokers, namespace=namespace, conditions=broker_conditions)
                broker_cardinality: dict = broker_spec.get("cardinality")
                broker_eval_value["spec.cardinality"] = broker_cardinality
                broker_eval_value["spec.mode"] = broker_mode
                if not broker_cardinality:
                    broker_eval_status = CheckTaskStatus.error.value
                    # show cardinality display (regardless of detail level) if it's missing
                    check_manager.add_display(
                        target_name=target_brokers,
                        namespace=namespace,
                        display=Padding("\nCardinality", (0, 0, 0, 12)),
                    )
                    check_manager.add_display(
                        target_name=target_brokers,
                        namespace=namespace,
                        display=Padding(
                            "[magenta]spec.cardinality is undefined![/magenta]",
                            (0, 0, 0, 16),
                        ),
                    )
                else:
                    backend_cardinality_desc = "- Expecting backend partitions [bright_blue]>=1[/bright_blue]. {}"
                    backend_redundancy_desc = "- Expecting backend redundancy factor [bright_blue]>=1[/bright_blue]. {}"
                    backend_workers_desc = "- Expecting backend workers [bright_blue]>=1[/bright_blue]. {}"
                    frontend_cardinality_desc = "- Expecting frontend replicas [bright_blue]>=1[/bright_blue]. {}"

                    backend_chain = broker_cardinality.get("backendChain", {})
                    backend_partition_count: Optional[int] = backend_chain.get("partitions")
                    backend_redundancy: Optional[int] = backend_chain.get("redundancyFactor")
                    backend_workers: Optional[int] = backend_chain.get("workers")
                    frontend_replicas: Optional[int] = broker_cardinality.get("frontend", {}).get("replicas")

                    if backend_partition_count and backend_partition_count >= 1:
                        backend_chain_count_colored = f"[green]Actual {backend_partition_count}[/green]."
                    else:
                        backend_chain_count_colored = f"[red]Actual {backend_partition_count}[/red]."
                        broker_eval_status = CheckTaskStatus.error.value

                    if backend_redundancy and backend_redundancy >= 1:
                        backend_replicas_colored = f"[green]Actual {backend_redundancy}[/green]."
                    else:
                        backend_replicas_colored = f"[red]Actual {backend_redundancy}[/red]."
                        broker_eval_status = CheckTaskStatus.error.value

                    if backend_workers and backend_workers >= 1:
                        backend_workers_colored = f"[green]Actual {backend_workers}[/green]."
                    else:
                        backend_workers_colored = f"[red]Actual {backend_workers}[/red]."
                        broker_eval_status = CheckTaskStatus.error.value

                    if frontend_replicas and frontend_replicas >= 1:
                        frontend_replicas_colored = f"[green]Actual {frontend_replicas}[/green]."
                    else:
                        frontend_replicas_colored = f"[red]Actual {frontend_replicas}[/red]."

                    # show cardinality display on non-summary detail_levels
                    if detail_level != ResourceOutputDetailLevel.summary.value:
                        check_manager.add_display(
                            target_name=target_brokers,
                            namespace=namespace,
                            display=Padding("\nCardinality", (0, 0, 0, 12)),
                        )

                        for display in [
                            backend_cardinality_desc.format(backend_chain_count_colored),
                            backend_redundancy_desc.format(backend_replicas_colored),
                            backend_workers_desc.format(backend_workers_colored),
                            frontend_cardinality_desc.format(frontend_replicas_colored)
                        ]:
                            check_manager.add_display(
                                target_name=target_brokers,
                                namespace=namespace,
                                display=Padding(display, (0, 0, 0, 16)),
                            )

            diagnostic_detail_padding = (0, 0, 0, 16)
            # show diagnostics display only on verbose detail_level
            if broker_diagnostics and detail_level == ResourceOutputDetailLevel.verbose.value:
                check_manager.add_display(
                    target_name=target_brokers,
                    namespace=namespace,
                    display=Padding("\nBroker Diagnostics", (0, 0, 0, 12)),
                )
                for (key, label) in [
                    ("enableMetrics", "Enable Metrics"),
                    ("enableSelfCheck", "Enable Self-Check"),
                    ("enableTracing", "Enable Tracing"),
                    ("metricUpdateFrequencySeconds", "Update Frequency (s)"),
                    ("logLevel", "Log Level"),
                ]:
                    val = broker_diagnostics.get(key)
                    check_manager.add_display(
                        target_name=target_brokers,
                        namespace=namespace,
                        display=Padding(
                            f"{label}: [cyan]{val}[/cyan]",
                            diagnostic_detail_padding,
                        ),
                    )
            # show broker diagnostics error regardless of detail_level
            elif not broker_diagnostics:
                check_manager.add_target_eval(
                    target_name=target_brokers,
                    namespace=namespace,
                    status=CheckTaskStatus.warning.value,
                    value=None,
                )
                check_manager.add_display(
                    target_name=target_brokers,
                    namespace=namespace,
                    display=Padding("\nBroker Diagnostics", (0, 0, 0, 12)),
                )
                check_manager.add_display(
                    target_name=target_brokers,
                    namespace=namespace,
                    display=Padding(
                        "[yellow]Unable to fetch broker diagnostics.[/yellow]",
                        diagnostic_detail_padding,
                    ),
                )

            check_manager.add_target_eval(
                target_name=target_brokers,
                namespace=namespace,
                status=broker_eval_status,
                value=broker_eval_value,
                resource_name=broker_name,
            )

        if brokers_count > 0:
            check_manager.add_display(
                target_name=target_brokers,
                namespace=namespace,
                display=Padding(
                    "\nRuntime Health",
                    (0, 0, 0, 8),
                ),
            )

            for pod in [
                AIO_MQ_DIAGNOSTICS_PROBE_PREFIX,
                AIO_MQ_FRONTEND_PREFIX,
                AIO_MQ_BACKEND_PREFIX,
                AIO_MQ_AUTH_PREFIX
            ]:
                evaluate_pod_health(
                    check_manager=check_manager,
                    target=target_brokers,
                    namespace=namespace,
                    pod=pod,
                    display_padding=12,
                    service_label=MQ_LABEL
                )

    return check_manager.as_dict(as_list)


# Cloud connector checks
def evaluate_mqtt_bridge_connectors(
    as_list: bool = False,
    detail_level: str = ResourceOutputDetailLevel.summary.value,
    resource_name: str = None,
) -> Dict[str, Any]:
    from rich.table import Table

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
        namespace: str,
        topic_maps: List[Dict[str, str]],
        detail_level: str,
        padding: tuple,
    ) -> None:
        # Show warning if no topic maps
        if not len(topic_maps):
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(
                    "[yellow]No MQTT Bridge Topic Maps reference this resource[/yellow]",
                    padding,
                ),
            )

        # topic maps that reference this bridge
        for topic_map in topic_maps:
            name = get_resource_name(topic_map)

            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(f"- Topic Map {{[blue]{name}[/blue]}}", padding),
            )

            if detail_level != ResourceOutputDetailLevel.summary.value:
                route_padding = (0, 0, 0, padding[3] + 4)
                routes = topic_map.get("spec", {}).get("routes", [])
                if detail_level == ResourceOutputDetailLevel.verbose.value:
                    route_table = create_routes_table(routes)
                    check_manager.add_display(target_name=target, namespace=namespace, display=Padding(route_table, route_padding))
                    continue
                for route in routes:
                    route_name = route.get("name")
                    check_manager.add_display(
                        target_name=target,
                        namespace=namespace,
                        display=Padding(
                            f"- Route {{[blue]{route_name}[/blue]}}",
                            route_padding,
                        ),
                    )

    def display_connector_info(check_manager: CheckManager, target: str, namespace: str, connector: Dict[str, str], detail_level: str, padding: tuple) -> None:
        # bridge resource
        connector_metadata = connector.get("metadata", {})
        connector_name = connector_metadata.get("name")

        # bridge resource status
        connector_status = connector.get("status", {})
        connector_status_level = connector_status.get("configStatusLevel", "N/A")

        connector_eval_status = _calculate_connector_status(connector_status_level)
        check_manager.add_target_eval(
            target_name=target,
            namespace=namespace,
            status=connector_eval_status,
            value=connector_status,
            resource_name=connector_name,
            resource_kind=MqResourceKinds.MQTT_BRIDGE_CONNECTOR.value,
        )

        connector_status_desc = connector_status.get("configStatusDescription")

        connector_status_text = f" {connector_status_desc}" if connector_status_desc else ""
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding(
                f"\n- Bridge {{[bright_blue]{connector_name}[/bright_blue]}} status {{{decorate_resource_status(connector_status_level)}}}.{connector_status_text}",
                padding,
            ),
        )

        # bridge resource instance details
        spec = connector.get("spec", {})
        connector_eval_status = (
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
            namespace=namespace,
            status=connector_eval_status,
            value={"spec": spec},
            resource_name=connector_name,
            resource_kind=MqResourceKinds.MQTT_BRIDGE_CONNECTOR.value,
        )

        connector_instances = spec.get("bridgeInstances")
        client_prefix = spec.get("clientIdPrefix")
        detail_padding = (0, 0, 0, padding[-1] + 4)
        if detail_level != ResourceOutputDetailLevel.summary.value:
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(
                    f"Bridge instances: [bright_blue]{connector_instances}[/bright_blue]",
                    detail_padding,
                ),
            )
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(
                    f"Client Prefix: [bright_blue]{client_prefix}[/bright_blue]",
                    detail_padding,
                ),
            )
            # local broker endpoint
            for (label, key) in [
                ("Local Broker Connection", "localBrokerConnection"),
                ("Remote Broker Connection", "remoteBrokerConnection")
            ]:
                broker = spec.get(key, {})
                endpoint = broker.get("endpoint")
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=Padding(
                        f"{label}: [bright_blue]{endpoint}[/bright_blue]",
                        detail_padding,
                    ),
                )
                if detail_level == ResourceOutputDetailLevel.verbose.value:
                    auth = next(iter(broker.get("authentication")))
                    tls = broker.get("tls", {}).get("tlsEnabled", False)
                    check_manager.add_display(
                        target_name=target,
                        namespace=namespace,
                        display=Padding(
                            f"Auth: [bright_blue]{auth}[/bright_blue] TLS: [bright_blue]{tls}[/bright_blue]",
                            detail_padding,
                        ),
                    )

    return process_cloud_connector(
        connector_target="mqttbridgeconnectors.mq.iotoperations.azure.com",
        topic_map_target="mqttbridgetopicmaps.mq.iotoperations.azure.com",
        connector_display_name="MQTT Bridge Connector",
        topic_map_reference_key="mqttBridgeConnectorRef",
        connector_resource_kind=MqResourceKinds.MQTT_BRIDGE_CONNECTOR,
        topic_map_resource_kind=MqResourceKinds.MQTT_BRIDGE_TOPIC_MAP,
        connector_display_func=display_connector_info,
        topic_map_display_func=display_topic_maps,
        detail_level=detail_level,
        as_list=as_list,
        connector_resource_name=resource_name,
    )


def evaluate_datalake_connectors(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_name: str = None,
) -> Dict[str, Any]:
    from rich.table import Table

    def create_schema_table(schema: List[Dict[str, str]]) -> Table:
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
        namespace: str,
        topic_maps: List[Dict[str, str]],
        detail_level: str,
        padding: tuple,
    ) -> None:
        # Show warning if no topic maps
        if not len(topic_maps):
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(
                    "[yellow]No Data Lake Connector Topic Maps reference this resource[/yellow]",
                    padding,
                ),
            )
            return

        for topic_map in topic_maps:
            topic_name = get_resource_name(topic_map)
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
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
                allowed_latency = topic_mapping.get("allowedLatencySecs")
                qos = topic_mapping.get("qos")

                table = topic_mapping.get("table", {})
                table_name = table.get("tableName")

                detail_padding = (0, 0, 0, padding[3] + 4)
                for row in [
                    ["Table Name", table_name],
                    ["Allowed Latency (s)", allowed_latency],
                    ["Max Messages Per Batch", max_msg_per_batch],
                    ["Message Payload Type", msg_payload_type],
                    ["MQTT Source Topic", source_topic],
                    ["QOS", qos],
                ]:
                    check_manager.add_display(
                        target_name=target,
                        namespace=namespace,
                        display=Padding(
                            f"- {row[0]}: [bright_blue]{row[1]}[/bright_blue]",
                            detail_padding,
                        ),
                    )
            if detail_level == ResourceOutputDetailLevel.verbose.value:
                table = topic_mapping.get("table", {})
                schema = table.get("schema", [])
                route_table = create_schema_table(schema)
                check_manager.add_display(target_name=target, namespace=namespace, display=Padding(route_table, padding))

    def display_connector_info(
        check_manager: CheckManager,
        target: str,
        namespace: str,
        connector: Dict[str, str],
        detail_level: str,
        padding: tuple,
    ) -> None:
        connector_name = get_resource_name(connector)

        # connector resource status
        connector_status = connector.get("status", {})
        connector_status_level = connector_status.get("configStatusLevel", "N/A")

        connector_eval_status = _calculate_connector_status(connector_status_level)

        check_manager.add_target_eval(
            target_name=target,
            namespace=namespace,
            status=connector_eval_status,
            value=connector_status,
            resource_name=connector_name,
            resource_kind=MqResourceKinds.DATALAKE_CONNECTOR.value,
        )

        connector_status_desc = connector_status.get("configStatusDescription")
        connector_status_text = f" {connector_status_desc}" if connector_status_desc else ""

        check_manager.add_display(
            target_name=target,
            namespace=namespace,
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
            namespace=namespace,
            status=connector_eval_status,
            value={"spec": spec},
            resource_name=connector_name,
            resource_kind=MqResourceKinds.DATALAKE_CONNECTOR.value,
        )
        connector_instances = spec.get("instances")

        datalake_target = spec.get("target", {}).get("datalakeStorage", {})
        datalake_endpoint = datalake_target.get("endpoint")
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding(
                f"Connector instances: [bright_blue]{connector_instances}[/bright_blue]",
                detail_padding,
            ),
        )
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding(
                f"Target endpoint: [bright_blue]{datalake_endpoint}[/bright_blue]",
                detail_padding,
            ),
        )

    return process_cloud_connector(
        connector_target="datalakeconnectors.mq.iotoperations.azure.com",
        topic_map_target="datalakeconnectortopicmaps.mq.iotoperations.azure.com",
        connector_display_name="Data Lake Connector",
        topic_map_reference_key="dataLakeConnectorRef",
        connector_resource_kind=MqResourceKinds.DATALAKE_CONNECTOR,
        topic_map_resource_kind=MqResourceKinds.DATALAKE_CONNECTOR_TOPIC_MAP,
        connector_display_func=display_connector_info,
        topic_map_display_func=display_topic_maps,
        detail_level=detail_level,
        as_list=as_list,
        connector_resource_name=resource_name,
    )


def evaluate_kafka_connectors(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_name: str = None,
) -> Dict[str, Any]:
    def display_connector_info(check_manager: CheckManager, target: str, namespace: str, connector: Dict[str, Any], detail_level: str, padding: tuple):
        connector_name = get_resource_name(connector)
        connector_status = connector.get("status", {})
        connector_status_level = connector_status.get("configStatusLevel", "N/A")
        eval_status = _calculate_connector_status(connector_status_level)

        check_manager.add_target_eval(
            target_name=target,
            namespace=namespace,
            status=eval_status,
            value=connector_status,
            resource_name=connector_name,
            resource_kind=MqResourceKinds.KAFKA_CONNECTOR.value,
        )

        connector_status_desc = connector_status.get("statusDescription")

        connector_status_text = f" {connector_status_desc}" if connector_status_desc else ""
        check_manager.add_display(
            target_name=target,
            namespace=namespace,
            display=Padding(
                f"\n- Connector {{[bright_blue]{connector_name}[/bright_blue]}} status {{{decorate_resource_status(connector_status_level)}}}.{connector_status_text}",
                padding,
            ),
        )

        spec = connector.get("spec", {})

        clientIdPrefix = spec.get("clientIdPrefix")
        instances = spec.get("instances")
        logLevel = spec.get("logLevel")
        broker = spec.get("localBrokerConnection")
        kafka_broker = spec.get("kafkaConnection")

        connector_eval_status = (
            CheckTaskStatus.error.value
            if not all(
                [
                    clientIdPrefix,
                    instances,
                    broker,
                    kafka_broker,
                ]
            )
            else CheckTaskStatus.success.value
        )

        detail_padding = (0, 0, 0, padding[3] + 4)

        check_manager.add_target_eval(
            target_name=target,
            namespace=namespace,
            status=connector_eval_status,
            value={"spec": spec},
            resource_name=connector_name,
            resource_kind=MqResourceKinds.KAFKA_CONNECTOR.value,
        )

        if detail_level != ResourceOutputDetailLevel.summary.value:
            for (label, val) in [
                ("Client ID Prefix", clientIdPrefix),
                ("Instances", instances),
                ("Log Level", logLevel),
            ]:
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=Padding(f"{label}: [bright_blue]{val}[/bright_blue]", detail_padding),
                )

            broker_detail_padding = (0, 0, 0, detail_padding[3] + 4)

            for (label, broker) in [
                ("Local Broker Connection", broker),
                ("Kafka Broker Connection", kafka_broker)
            ]:
                endpoint = broker.get("endpoint")
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=Padding(
                        f"{label}: [bright_blue]{endpoint}[/bright_blue]",
                        detail_padding,
                    ),
                )
                if detail_level == ResourceOutputDetailLevel.verbose.value:
                    auth = next(iter(broker.get("authentication", {})))
                    tls = broker.get("tls", {}).get("tlsEnabled", False)

                    check_manager.add_display(
                        target_name=target,
                        namespace=namespace,
                        display=Padding(
                            f"Auth: [bright_blue]{auth}[/bright_blue] TLS: [bright_blue]{tls}[/bright_blue]",
                            broker_detail_padding,
                        ),
                    )

    def display_topic_maps(check_manager: CheckManager, target: str, namespace: str, topic_maps: List[Dict[str, Any]], detail_level: str, padding: tuple):
        # Show warning if no topic maps
        if not len(topic_maps):
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(
                    "[yellow]No Kafka Topic Maps reference this resource[/yellow]",
                    padding,
                ),
            )
            return
        for topic_map in topic_maps:
            topic_name = get_resource_name(topic_map)
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
                display=Padding(
                    f"- Topic Map {{[bright_blue]{topic_name}[/bright_blue]}}",
                    padding,
                ),
            )
            spec = topic_map.get("spec", {})
            detail_padding = (0, 0, 0, padding[3] + 4)
            if detail_level == ResourceOutputDetailLevel.verbose.value:

                for label, key in [
                    ("Compression", "compression"),
                    ("Partition Key", "partitionKeyProperty"),
                    ("Partition Strategy", "partitionStrategy"),
                ]:
                    val = spec.get(key)

                    check_manager.add_display(
                        target_name=target,
                        namespace=namespace,
                        display=Padding(
                            f"{label}: [bright_blue]{val}[/bright_blue]",
                            detail_padding,
                        ),
                    )

                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
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
                        namespace=namespace,
                        display=Padding(
                            f"{label}: [bright_blue]{val}[/bright_blue]",
                            batch_detail_padding,
                        ),
                    )

            display_routes(
                check_manager=check_manager, target=target, namespace=namespace, routes=spec.get("routes", []), detail_level=detail_level, padding=detail_padding
            )

    def display_routes(check_manager: CheckManager, target: str, namespace: str, routes: List[Dict[str, str]], detail_level: str, padding: tuple):
        for route in routes:
            # route key is mqttToKafka | kafkaToMqtt
            route_type = next(iter(route))
            route_details = route[route_type]

            # shared properties
            name = route_details.get("name")
            check_manager.add_display(
                target_name=target,
                namespace=namespace,
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
                    namespace=namespace,
                    display=Padding(
                        f"Kafka topic: [bright_blue]{kafkaTopic}[/bright_blue]",
                        route_detail_padding,
                    ),
                )
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
                    display=Padding(
                        f"MQTT Topic: [bright_blue]{mqttTopic}[/bright_blue]",
                        route_detail_padding,
                    ),
                )
                check_manager.add_display(
                    target_name=target,
                    namespace=namespace,
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
                        namespace=namespace,
                        display=Padding(
                            f"Kafka Acks: [bright_blue]{kafkaAcks}[/bright_blue]",
                            route_detail_padding,
                        ),
                    )
                    check_manager.add_display(
                        target_name=target,
                        namespace=namespace,
                        display=Padding(
                            f"Shared Subscription Group Name: [bright_blue]{groupName}[/bright_blue]",
                            route_detail_padding,
                        ),
                    )
                    check_manager.add_display(
                        target_name=target,
                        namespace=namespace,
                        display=Padding(
                            f"Shared Subscription Group Minimum Share: [bright_blue]{groupMinimumShareNumber}[/bright_blue]",
                            route_detail_padding,
                        ),
                    )
                else:
                    consumerGroupId = route_details.get("consumerGroupId")
                    check_manager.add_display(
                        target_name=target,
                        namespace=namespace,
                        display=Padding(
                            f"Consumer Group ID: [bright_blue]{consumerGroupId}[/bright_blue]",
                            route_detail_padding,
                        ),
                    )

    return process_cloud_connector(
        connector_target="kafkaconnectors.mq.iotoperations.azure.com",
        topic_map_target="kafkaconnectortopicmaps.mq.iotoperations.azure.com",
        connector_display_name="Kafka Connector",
        topic_map_reference_key="kafkaConnectorRef",
        connector_resource_kind=MqResourceKinds.KAFKA_CONNECTOR,
        topic_map_resource_kind=MqResourceKinds.KAFKA_CONNECTOR_TOPIC_MAP,
        connector_display_func=display_connector_info,
        topic_map_display_func=display_topic_maps,
        detail_level=detail_level,
        as_list=as_list,
        connector_resource_name=resource_name,
    )


def _get_valid_references(kind: Union[Enum, str], namespace: Optional[str] = None) -> Dict[str, Any]:
    result = {}
    custom_objects = MQ_ACTIVE_API.get_resources(kind=kind, namespace=namespace)
    if custom_objects:
        objects: List[dict] = custom_objects.get("items", [])
        for object in objects:
            o: dict = object
            metadata: dict = o.get("metadata", {})
            name = metadata.get("name")
            if name:
                result[name] = True

    return result


def _calculate_connector_status(resource_state: str) -> str:
    eval_status = CheckTaskStatus.success.value

    if resource_state in [ResourceState.error.value, ResourceState.failed.value]:
        eval_status = CheckTaskStatus.error.value
    elif resource_state in [
        ResourceState.recovering.value,
        ResourceState.warn.value,
        ResourceState.starting.value,
        "N/A",
    ]:
        eval_status = CheckTaskStatus.warning.value
    return eval_status
