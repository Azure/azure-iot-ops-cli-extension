# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Any, Dict, List, Optional, Union
from enum import Enum

from azext_edge.edge.providers.check.base.resource import process_dict_resource, process_resource_properties
from .base import (
    CheckManager,
    decorate_resource_status,
    check_post_deployment,
    evaluate_pod_health,
    get_resources_by_name,
    get_resources_grouped_by_namespace
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
    AIO_MQ_FLUENT_BIT,
    AIO_MQ_FRONTEND_PREFIX,
    AIO_MQ_BACKEND_PREFIX,
    AIO_MQ_AUTH_PREFIX,
    AIO_MQ_HEALTH_MANAGER,
    AIO_MQ_OPERATOR,
    BROKER_DIAGNOSTICS_PROPERTIES,
    ResourceOutputDetailLevel,
)

from ...providers.edge_api import (
    MQ_ACTIVE_API,
    MqResourceKinds
)
from ..support.mq import MQ_K8S_LABEL, MQ_NAME_LABEL

from ..base import get_namespaced_service


def check_mq_deployment(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_kinds: List[str] = None,
    resource_name: str = None,
) -> List[dict]:
    evaluate_funcs = {
        MqResourceKinds.BROKER: evaluate_brokers,
        MqResourceKinds.BROKER_LISTENER: evaluate_broker_listeners,
    }

    return check_post_deployment(
        api_info=MQ_ACTIVE_API,
        check_name="enumerateBrokerApi",
        check_desc="Enumerate MQTT Broker API resources",
        evaluate_funcs=evaluate_funcs,
        as_list=as_list,
        detail_level=detail_level,
        resource_kinds=resource_kinds,
        resource_name=resource_name,
    )


def evaluate_broker_listeners(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_name: str = None,
) -> Dict[str, Any]:
    check_manager = CheckManager(
        check_name="evalBrokerListeners",
        check_desc="Evaluate MQTT Broker Listeners",
    )

    target_listeners = "brokerlisteners.mqttbroker.iotoperations.azure.com"
    listener_conditions = [
        "len(brokerlisteners)>=1",
        "spec",
        "valid(spec.brokerRef)",
        "spec.serviceName",
        "status",
    ]

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

    for (namespace, listeners) in get_resources_grouped_by_namespace(all_listeners):
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
                ports = listener_spec.get("ports", [])

                for port in ports:
                    for (label, val) in [
                        ("Port", 'port'),
                        ("AuthN", 'authenticationRef'),
                        ("AuthZ", 'authorizationRef'),
                        ("Node Port", 'nodePort'),
                    ]:
                        val = port.get(val)

                        if val:
                            check_manager.add_display(
                                target_name=target_listeners,
                                namespace=namespace,
                                display=Padding(
                                    f"{label}: [bright_blue]{val}[/bright_blue]",
                                    (0, 0, 0, 12),
                                ),
                            )

            if listener_spec_service_name not in processed_services:
                _evaluate_listener_service(
                    check_manager=check_manager,
                    listener_spec=listener_spec,
                    processed_services=processed_services,
                    target_listeners=target_listeners,
                    namespace=namespace,
                    detail_level=detail_level,
                )

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
    check_manager = CheckManager(check_name="evalBrokers", check_desc="Evaluate MQTT Brokers")

    target_brokers = "brokers.mqttbroker.iotoperations.azure.com"
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

    for (namespace, brokers) in get_resources_grouped_by_namespace(all_brokers):
        check_manager.add_target(target_name=target_brokers, namespace=namespace, conditions=broker_conditions)
        check_manager.add_display(
            target_name=target_brokers,
            namespace=namespace,
            display=Padding(
                f"MQTT Brokers in namespace {{[purple]{namespace}[/purple]}}",
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
        added_diagnostics_conditions = False
        for b in brokers:
            broker_name = b["metadata"]["name"]
            broker_spec: dict = b["spec"]
            broker_diagnostics = broker_spec["diagnostics"]
            broker_status_state = b.get("status", {})
            broker_status = broker_status_state.get("status", "N/A")
            broker_status_desc = broker_status_state.get("statusDescription")

            status_display_text = f"Status {{{decorate_resource_status(broker_status)}}}."

            if broker_status_state:
                status_display_text = f"{status_display_text} {broker_status_desc}."

            target_broker_text = (
                f"\n- Broker {{[bright_blue]{broker_name}[/bright_blue]}}"
            )
            check_manager.add_display(
                target_name=target_brokers,
                namespace=namespace,
                display=Padding(target_broker_text, (0, 0, 0, 8)),
            )

            broker_eval_value = {"status": {"status": broker_status, "statusDescription": broker_status_desc}}
            broker_eval_status = _calculate_status(broker_status)

            check_manager.add_display(
                target_name=target_brokers,
                namespace=namespace,
                display=Padding(status_display_text, (0, 0, 0, 12)),
            )

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

            if not added_diagnostics_conditions:
                check_manager.add_target_conditions(
                    target_name=target_brokers,
                    conditions=["spec.diagnostics"],
                    namespace=namespace,
                )
                added_diagnostics_conditions = True

            broker_eval_value["spec.diagnostics"] = broker_diagnostics

            if broker_diagnostics:
                if detail_level != ResourceOutputDetailLevel.summary.value:
                    check_manager.add_display(
                        target_name=target_brokers,
                        namespace=namespace,
                        display=Padding("\nBroker Diagnostics", (0, 0, 0, 12)),
                    )

                    if detail_level == ResourceOutputDetailLevel.detail.value:
                        process_resource_properties(
                            check_manager=check_manager,
                            detail_level=detail_level,
                            target_name=target_brokers,
                            prop_value=broker_diagnostics,
                            properties=BROKER_DIAGNOSTICS_PROPERTIES,
                            namespace=namespace,
                            padding=diagnostic_detail_padding,
                        )
                    else:
                        process_dict_resource(
                            check_manager=check_manager,
                            target_name=target_brokers,
                            resource=broker_diagnostics,
                            namespace=namespace,
                            padding=diagnostic_detail_padding[3],
                        )
            # show broker diagnostics error regardless of detail_level
            else:
                broker_eval_status = CheckTaskStatus.warning.value
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

            _evaluate_broker_diagnostics_service(
                check_manager=check_manager,
                target_brokers=target_brokers,
                namespace=namespace,
                detail_level=detail_level,
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

            evaluate_pod_health(
                check_manager=check_manager,
                target=target_brokers,
                namespace=namespace,
                padding=12,
                pod_with_labels=[
                    (AIO_MQ_DIAGNOSTICS_PROBE_PREFIX, MQ_NAME_LABEL),
                    (AIO_MQ_FRONTEND_PREFIX, MQ_NAME_LABEL),
                    (AIO_MQ_BACKEND_PREFIX, MQ_NAME_LABEL),
                    (AIO_MQ_AUTH_PREFIX, MQ_NAME_LABEL),
                    (AIO_MQ_HEALTH_MANAGER, MQ_NAME_LABEL),
                    (AIO_MQ_DIAGNOSTICS_SERVICE, MQ_NAME_LABEL),
                    (AIO_MQ_OPERATOR, MQ_NAME_LABEL),
                    (AIO_MQ_FLUENT_BIT, MQ_K8S_LABEL),
                ],
                detail_level=detail_level,
            )

    return check_manager.as_dict(as_list)


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


def _calculate_status(resource_state: str) -> str:
    return ResourceState.map_to_status(resource_state).value


def _evaluate_listener_service(
    check_manager: CheckManager,
    listener_spec: dict,
    processed_services: dict,
    target_listeners: str,
    namespace: str,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
) -> None:
    listener_spec_service_name: str = listener_spec["serviceName"]
    listener_spec_service_type: str = listener_spec["serviceType"]
    target_listener_service = f"service/{listener_spec_service_name}"
    listener_service_eval_status = CheckTaskStatus.success.value
    check_manager.add_target(
        target_name=target_listener_service,
        namespace=namespace,
        conditions=["listener_service"],
    )

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
            value={"listener_service": "Unable to fetch service."},
            resource_name=f"service/{listener_spec_service_name}"
        )
    else:
        check_manager.add_target_eval(
            target_name=target_listener_service,
            namespace=namespace,
            status=CheckTaskStatus.success.value,
            value={"listener_service": target_listener_service},
            resource_name=f"service/{listener_spec_service_name}"
        )

        check_manager.add_display(
            target_name=target_listener_service,
            namespace=namespace,
            display=Padding(
                f"Service {{[bright_blue]{listener_spec_service_name}[/bright_blue]}} of type [bright_blue]{listener_spec_service_type}[/bright_blue]",
                (0, 0, 0, 8),
            ),
        )

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
            load_balancer = service_status.get("c", {})
            ingress_rules: List[dict] = load_balancer.get("ingress", [])

            if not ingress_rules:
                listener_service_eval_status = CheckTaskStatus.warning.value
                ingress_count_colored = "[red]Detected 0[/red]."
            else:
                ingress_count_colored = f"[green]Detected {len(ingress_rules)}[/green]."

            if detail_level != ResourceOutputDetailLevel.summary.value:
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
                    if detail_level != ResourceOutputDetailLevel.summary.value:
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
        elif listener_spec_service_type.lower() == "clusterip":
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

            if detail_level != ResourceOutputDetailLevel.summary.value:
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
        elif listener_spec_service_type.lower() == "nodeport":
            pass


def _evaluate_broker_diagnostics_service(
    check_manager: CheckManager,
    target_brokers: str,
    namespace: str,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
) -> None:
    diagnostics_service = get_namespaced_service(name=AIO_MQ_DIAGNOSTICS_SERVICE, namespace=namespace, as_dict=True)
    if not diagnostics_service:
        check_manager.add_target_eval(
            target_name=target_brokers,
            namespace=namespace,
            status=CheckTaskStatus.error.value,
            value=f"service/{AIO_MQ_DIAGNOSTICS_SERVICE} not found in namespace {namespace}",
            resource_name=f"service/{AIO_MQ_DIAGNOSTICS_SERVICE}",
        )
        diag_service_desc_suffix = "[red]not detected[/red]."
        diag_service_desc = (
            f"Diagnostics Service {{[bright_blue]{AIO_MQ_DIAGNOSTICS_SERVICE}[/bright_blue]}} {diag_service_desc_suffix}"
        )
        check_manager.add_display(
            target_name=target_brokers,
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
            target_name=target_brokers,
            namespace=namespace,
            status=CheckTaskStatus.success.value,
            value={"spec": {"clusterIP": clusterIP, "ports": ports}},
            resource_name=f"service/{AIO_MQ_DIAGNOSTICS_SERVICE}",
        )
        diag_service_desc_suffix = "[green]detected[/green]."
        diag_service_desc = (
            f"\nDiagnostics Service {{[bright_blue]{AIO_MQ_DIAGNOSTICS_SERVICE}[/bright_blue]}} {diag_service_desc_suffix}"
        )
        check_manager.add_display(
            target_name=target_brokers,
            namespace=namespace,
            display=Padding(
                diag_service_desc,
                (0, 0, 0, 12),
            ),
        )
        if ports and detail_level != ResourceOutputDetailLevel.summary.value:
            for port in ports:
                check_manager.add_display(
                    target_name=target_brokers,
                    namespace=namespace,
                    display=Padding(
                        f"[cyan]{port.get('name')}[/cyan] "
                        f"port [bright_blue]{port.get('port')}[/bright_blue] "
                        f"protocol [cyan]{port.get('protocol')}[/cyan]",
                        (0, 0, 0, 16),
                    ),
                )
            check_manager.add_display(target_name=target_brokers, namespace=namespace, display=NewLine())
