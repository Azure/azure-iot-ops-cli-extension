# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Any, Dict, List, Optional

from azext_edge.edge.providers.check.base.display import add_display_and_eval, colorize_string

from .base import (
    CheckManager,
    check_post_deployment,
    evaluate_pod_health,
    get_resources_by_name,
    get_resources_grouped_by_namespace,
    process_dict_resource,
    process_resource_properties,
    validate_one_of_conditions,
    process_custom_resource_status,
    get_valid_references,
    validate_ref,
)

from rich.console import NewLine
from rich.padding import Padding

from ...common import (
    AIO_BROKER_DIAGNOSTICS_SERVICE,
    CheckTaskStatus,
)

from .common import (
    AIO_BROKER_DIAGNOSTICS_PROBE_PREFIX,
    AIO_BROKER_FLUENT_BIT,
    AIO_BROKER_FRONTEND_PREFIX,
    AIO_BROKER_BACKEND_PREFIX,
    AIO_BROKER_AUTH_PREFIX,
    AIO_BROKER_HEALTH_MANAGER,
    AIO_BROKER_OPERATOR,
    BROKER_DIAGNOSTICS_PROPERTIES,
    DEFAULT_PADDING,
    CheckResult,
    ResourceOutputDetailLevel,
    ValidationResourceType,
)

from ...providers.edge_api import MQ_ACTIVE_API, MqResourceKinds
from ..support.mq import MQ_NAME_LABEL

from ..base import get_namespaced_pods_by_prefix, get_namespaced_service


def check_mq_deployment(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_kinds: List[str] = None,
    resource_name: str = None,
) -> List[dict]:
    evaluate_funcs = {
        MqResourceKinds.BROKER: evaluate_brokers,
        MqResourceKinds.BROKER_LISTENER: evaluate_broker_listeners,
        MqResourceKinds.BROKER_AUTHENTICATION: evaluate_broker_authentications,
        MqResourceKinds.BROKER_AUTHORIZATION: evaluate_broker_authorizations,
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
        "spec.serviceName",
    ]

    all_listeners = get_resources_by_name(
        api_info=MQ_ACTIVE_API,
        kind=MqResourceKinds.BROKER_LISTENER,
        resource_name=resource_name,
    )
    if not all_listeners:
        status = CheckTaskStatus.skipped.value if resource_name else CheckTaskStatus.error.value
        fetch_listeners_error_text = f"Unable to fetch {MqResourceKinds.BROKER_LISTENER.value}s in any namespace."
        check_manager.add_target(target_name=target_listeners)
        check_manager.add_target_eval(
            target_name=target_listeners,
            status=status,
            value=fetch_listeners_error_text,
        )
        check_manager.add_display(
            target_name=target_listeners,
            display=Padding(fetch_listeners_error_text, (0, 0, 0, DEFAULT_PADDING)),
        )
        return check_manager.as_dict(as_list)

    for namespace, listeners in get_resources_grouped_by_namespace(all_listeners):
        check_manager.add_target(
            target_name=target_listeners,
            namespace=namespace,
            conditions=listener_conditions,
        )
        check_manager.add_display(
            target_name=target_listeners,
            namespace=namespace,
            display=Padding(
                f"Broker Listeners in namespace {{[purple]{namespace}[/purple]}}", (0, 0, 0, DEFAULT_PADDING)
            ),
        )

        listeners = list(listeners)
        listeners_count = len(listeners)
        listener_count_desc = f"- Expecting {colorize_string('>=1')} broker listeners per namespace. "
        listeners_eval_status = CheckTaskStatus.success.value

        if listeners_count >= 1:
            listeners_count_color = "green"
        else:
            listeners_count_color = "yellow"
            check_manager.set_target_status(
                target_name=target_listeners, namespace=namespace, status=CheckTaskStatus.warning.value
            )

        listener_count_desc += f"{colorize_string(color=listeners_count_color, value=f'Detected {listeners_count}')}."
        check_manager.add_display(
            target_name=target_listeners,
            namespace=namespace,
            display=Padding(listener_count_desc, (0, 0, 0, DEFAULT_PADDING)),
        )

        processed_services = {}
        added_broker_ref_condition = False

        for listener in listeners:
            auth_metadata = listener["metadata"]

            namespace: str = namespace or listener["metadata"]["namespace"]
            listener_name: str = listener["metadata"]["name"]
            listener_spec = listener["spec"]
            listener_spec_service_name: str = listener_spec["serviceName"]
            listener_status_state = listener.get("status", {})

            listener_eval_value = {}
            listener_eval_value["spec"] = listener_spec

            # check broker reference
            listener_desc = f"\n- Broker Listener {{{colorize_string(listener_name)}}}."
            broker_ref = auth_metadata.get("ownerReferences", [])
            _evaluate_broker_reference(
                check_manager=check_manager,
                owner_reference=broker_ref,
                target_name=target_listeners,
                namespace=namespace,
                resource_name=listener_name,
                added_condition=added_broker_ref_condition,
                display_text=listener_desc,
            )

            listener_properties_padding = DEFAULT_PADDING + 4

            if listener_status_state:
                process_custom_resource_status(
                    check_manager=check_manager,
                    status=listener_status_state,
                    target_name=target_listeners,
                    namespace=namespace,
                    resource_name=listener_name,
                    padding=listener_properties_padding,
                    detail_level=detail_level,
                )

            ports = listener_spec.get("ports", [])

            for port in ports:
                tls = port.get("tls", {})
                authn = port.get("authenticationRef", {})
                authz = port.get("authorizationRef", {})
                if detail_level != ResourceOutputDetailLevel.summary.value:
                    for label, val in [
                        ("Port", "port"),
                        ("Node Port", "nodePort"),
                    ]:
                        val = port.get(val)

                        if val:
                            check_manager.add_display(
                                target_name=target_listeners,
                                namespace=namespace,
                                display=Padding(
                                    f"{label}: {colorize_string(val)}",
                                    (0, 0, 0, 12),
                                ),
                            )

                if authn:
                    authn_condition = "spec.ports[*].authenticationRef"
                    valid_authns = get_valid_references(
                        api=MQ_ACTIVE_API,
                        kind=MqResourceKinds.BROKER_AUTHENTICATION.value,
                        namespace=namespace,
                    )

                    check_manager.add_target_conditions(
                        target_name=target_listeners,
                        namespace=namespace,
                        conditions=[authn_condition],
                    )

                    authn_eval_value = {"spec.ports[*].authenticationRef": authn}

                    is_authn_valid = authn in valid_authns
                    authn_validity = "valid" if is_authn_valid else "invalid"
                    authn_color = "green" if is_authn_valid else "red"
                    authn_display = f"Authentication reference: {{{colorize_string(authn)}}} is {colorize_string(color=authn_color, value=authn_validity)}."
                    authn_eval_status = (
                        CheckTaskStatus.error.value if authn_validity == "invalid" else CheckTaskStatus.success.value
                    )

                    if (
                        detail_level > ResourceOutputDetailLevel.summary.value
                        or authn_eval_status == CheckTaskStatus.error.value
                    ):
                        check_manager.add_display(
                            target_name=target_listeners,
                            namespace=namespace,
                            display=Padding(authn_display, (0, 0, 0, 12)),
                        )

                    check_manager.add_target_eval(
                        target_name=target_listeners,
                        namespace=namespace,
                        status=authn_eval_status,
                        value=authn_eval_value,
                        resource_name=listener_name,
                    )

                if authz:
                    authz_condition = "spec.ports[*].authorizationRef"
                    valid_authzs = get_valid_references(
                        api=MQ_ACTIVE_API,
                        kind=MqResourceKinds.BROKER_AUTHORIZATION.value,
                        namespace=namespace,
                    )

                    check_manager.add_target_conditions(
                        target_name=target_listeners,
                        namespace=namespace,
                        conditions=[authz_condition],
                    )

                    authz_eval_value = {"spec.ports[*].authorizationRef": authz}
                    is_authz_valid = authz in valid_authzs
                    authz_validity = "valid" if is_authz_valid else "invalid"
                    authz_color = "green" if is_authz_valid else "red"
                    authz_display = (
                        f"Authorization reference: {{{colorize_string(authz)}}} is "
                        f"{colorize_string(color=authz_color, value=authz_validity)}."
                    )
                    authz_eval_status = (
                        CheckTaskStatus.success.value if authz_validity == "valid" else CheckTaskStatus.error.value
                    )

                    if (
                        detail_level > ResourceOutputDetailLevel.summary.value
                        or authz_eval_status == CheckTaskStatus.error.value
                    ):
                        check_manager.add_display(
                            target_name=target_listeners,
                            namespace=namespace,
                            display=Padding(authz_display, (0, 0, 0, 12)),
                        )

                    check_manager.add_target_eval(
                        target_name=target_listeners,
                        namespace=namespace,
                        status=authz_eval_status,
                        value=authz_eval_value,
                        resource_name=listener_name,
                    )

                if tls:
                    # "certManagerCertificateSpec" and "manual" are mutually exclusive
                    cert_spec = tls.get("certManagerCertificateSpec", {})
                    cert_spec_condition = "spec.ports[*].tls.certManagerCertificateSpec"
                    manual = tls.get("manual", {})
                    manual_condition = "spec.ports[*].tls.manual"
                    tls_eval_value = {
                        cert_spec_condition: cert_spec,
                        manual_condition: manual,
                    }
                    validate_one_of_conditions(
                        conditions=[
                            (cert_spec_condition, cert_spec),
                            (manual_condition, manual),
                        ],
                        check_manager=check_manager,
                        eval_value=tls_eval_value,
                        namespace=namespace,
                        target_name=target_listeners,
                        resource_name=listener_name,
                        padding=listener_properties_padding,
                    )

                    if detail_level == ResourceOutputDetailLevel.verbose.value:
                        check_manager.add_display(
                            target_name=target_listeners,
                            namespace=namespace,
                            display=Padding("TLS:", (0, 0, 0, listener_properties_padding)),
                        )
                        # TODO - add check for refs
                        for prop_name, prop_value in {
                            "Cert Manager certificate spec": cert_spec,
                            "Manual": manual,
                        }.items():
                            if prop_value:
                                process_dict_resource(
                                    check_manager=check_manager,
                                    target_name=target_listeners,
                                    resource=prop_value,
                                    namespace=namespace,
                                    padding=listener_properties_padding + 2,
                                    prop_name=prop_name,
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

        # remove duplicate conditions
        # TODO - add remove duplicates on insertion under checkmanager itself
        listener_conditions = check_manager.targets.get(target_listeners, {}).get(namespace, {}).get("conditions", [])
        listener_conditions = list(set(listener_conditions))
        check_manager.set_target_conditions(
            target_name=target_listeners, namespace=namespace, conditions=listener_conditions
        )

    return check_manager.as_dict(as_list)


def evaluate_brokers(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_name: str = None,
) -> Dict[str, Any]:
    check_manager = CheckManager(check_name="evalBrokers", check_desc="Evaluate MQTT Brokers")

    target_brokers = "brokers.mqttbroker.iotoperations.azure.com"
    broker_conditions = ["len(brokers)==1", "spec.mode"]
    all_brokers: dict = get_resources_by_name(
        api_info=MQ_ACTIVE_API,
        kind=MqResourceKinds.BROKER,
        resource_name=resource_name,
    )

    if not all_brokers:
        status = CheckTaskStatus.skipped.value if resource_name else CheckTaskStatus.error.value
        fetch_brokers_error_text = f"Unable to fetch {MqResourceKinds.BROKER.value}s in any namespace."
        check_manager.add_target(target_name=target_brokers)
        check_manager.add_target_eval(
            target_name=target_brokers,
            status=status,
            value=fetch_brokers_error_text,
        )
        check_manager.add_display(
            target_name=target_brokers,
            display=Padding(fetch_brokers_error_text, (0, 0, 0, DEFAULT_PADDING)),
        )
        return check_manager.as_dict(as_list)

    for namespace, brokers in get_resources_grouped_by_namespace(all_brokers):
        check_manager.add_target(target_name=target_brokers, namespace=namespace, conditions=broker_conditions)
        check_manager.add_display(
            target_name=target_brokers,
            namespace=namespace,
            display=Padding(f"MQTT Brokers in namespace {{[purple]{namespace}[/purple]}}", (0, 0, 0, DEFAULT_PADDING)),
        )
        brokers = list(brokers)
        brokers_count = len(brokers)
        brokers_count_text = f"- Expecting {colorize_string('1')} broker resource per namespace. "
        broker_eval_status = CheckTaskStatus.success.value

        broker_color = "green" if brokers_count == 1 else "red"
        brokers_count_text += f"{colorize_string(color=broker_color, value=f'Detected {brokers_count}')}."

        if brokers_count != 1:
            check_manager.set_target_status(
                target_name=target_brokers, namespace=namespace, status=CheckTaskStatus.error.value
            )
        check_manager.add_display(
            target_name=target_brokers,
            namespace=namespace,
            display=Padding(brokers_count_text, (0, 0, 0, DEFAULT_PADDING)),
        )

        added_distributed_conditions = False
        added_diagnostics_conditions = False
        for b in brokers:
            broker_name = b["metadata"]["name"]
            broker_spec: dict = b["spec"]
            broker_diagnostics = broker_spec["diagnostics"]
            broker_status_state = b.get("status", {})

            target_broker_text = f"\n- Broker {{{colorize_string(broker_name)}}}"
            check_manager.add_display(
                target_name=target_brokers,
                namespace=namespace,
                display=Padding(target_broker_text, (0, 0, 0, DEFAULT_PADDING)),
            )
            broker_properties_padding = DEFAULT_PADDING + 4

            if broker_status_state:
                process_custom_resource_status(
                    check_manager=check_manager,
                    status=broker_status_state,
                    target_name=target_brokers,
                    namespace=namespace,
                    resource_name=broker_name,
                    padding=broker_properties_padding,
                    detail_level=detail_level,
                )

            broker_eval_value = {}
            if not added_distributed_conditions:
                # TODO - conditional evaluations
                broker_conditions.append("spec.cardinality")
                broker_conditions.append("spec.cardinality.backendChain.partitions>=1")
                broker_conditions.append("spec.cardinality.backendChain.redundancyFactor>=1")
                broker_conditions.append("spec.cardinality.backendChain.workers>=1")
                broker_conditions.append("spec.cardinality.frontend.replicas>=1")
                added_distributed_conditions = True

            check_manager.set_target_conditions(
                target_name=target_brokers, namespace=namespace, conditions=broker_conditions
            )
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
                        f"cardinality {colorize_string(color='red', value='not detected')}.",
                        (0, 0, 0, 16),
                    ),
                )
            else:
                broker_cardinality_eval_status = _evaluate_broker_cardinality(
                    check_manager=check_manager,
                    broker_cardinality=broker_cardinality,
                    target_brokers=target_brokers,
                    namespace=namespace,
                    padding=broker_properties_padding,
                    detail_level=detail_level,
                )

                if broker_cardinality_eval_status == CheckTaskStatus.error.value:
                    broker_eval_status = CheckTaskStatus.error.value
                elif broker_cardinality_eval_status == CheckTaskStatus.warning.value:
                    broker_eval_status = (
                        CheckTaskStatus.warning.value
                        if broker_eval_status != CheckTaskStatus.error.value
                        else broker_eval_status
                    )

            diagnostic_detail_padding = (0, 0, 0, broker_properties_padding + 4)

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
                        colorize_string(color="yellow", value="Unable to fetch broker diagnostics."),
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
                    (0, 0, 0, DEFAULT_PADDING),
                ),
            )

            pods: List[dict] = []

            for prefix in [
                AIO_BROKER_DIAGNOSTICS_PROBE_PREFIX,
                AIO_BROKER_FRONTEND_PREFIX,
                AIO_BROKER_BACKEND_PREFIX,
                AIO_BROKER_AUTH_PREFIX,
                AIO_BROKER_HEALTH_MANAGER,
                AIO_BROKER_DIAGNOSTICS_SERVICE,
                AIO_BROKER_OPERATOR,
                AIO_BROKER_FLUENT_BIT,
            ]:
                prefixed_pods = get_namespaced_pods_by_prefix(
                    prefix=prefix,
                    namespace=namespace,
                    label_selector=MQ_NAME_LABEL,
                )

                if not prefixed_pods:
                    add_display_and_eval(
                        check_manager=check_manager,
                        target_name=target_brokers,
                        display_text=f"{prefix}* {colorize_string(color='yellow', value='not detected')}.",
                        eval_status=CheckTaskStatus.warning.value,
                        eval_value=None,
                        resource_name=prefix,
                        namespace=namespace,
                        padding=(0, 0, 0, broker_properties_padding),
                    )
                else:
                    pods.extend(
                        get_namespaced_pods_by_prefix(
                            prefix=prefix,
                            namespace="",
                            label_selector=MQ_NAME_LABEL,
                        )
                    )

            evaluate_pod_health(
                check_manager=check_manager,
                target=target_brokers,
                namespace=namespace,
                padding=broker_properties_padding,
                pods=pods,
                detail_level=detail_level,
            )

    return check_manager.as_dict(as_list)


def evaluate_broker_authentications(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_name: str = None,
) -> Dict[str, Any]:

    check_manager = CheckManager(
        check_name="evalBrokerAuthentications",
        check_desc="Evaluate MQTT Broker Authentications",
    )

    target_authentications = "brokerauthentications.mqttbroker.iotoperations.azure.com"
    auth_conditions = ["len(spec.authenticationMethods)"]
    all_authentications = get_resources_by_name(
        api_info=MQ_ACTIVE_API,
        kind=MqResourceKinds.BROKER_AUTHENTICATION,
        resource_name=resource_name,
    )

    if not all_authentications:
        status = CheckTaskStatus.skipped.value if resource_name else CheckTaskStatus.error.value
        fetch_authentications_error_text = (
            f"Unable to fetch {MqResourceKinds.BROKER_AUTHENTICATION.value}s in any namespace."
        )
        check_manager.add_target(target_name=target_authentications)
        check_manager.add_target_eval(
            target_name=target_authentications,
            status=status,
            value=fetch_authentications_error_text,
        )
        check_manager.add_display(
            target_name=target_authentications,
            display=Padding(fetch_authentications_error_text, (0, 0, 0, DEFAULT_PADDING)),
        )
        return check_manager.as_dict(as_list)

    for namespace, authentications in get_resources_grouped_by_namespace(all_authentications):
        check_manager.add_target(
            target_name=target_authentications,
            namespace=namespace,
            conditions=auth_conditions,
        )
        check_manager.add_display(
            target_name=target_authentications,
            namespace=namespace,
            display=Padding(
                f"Broker Authentications in namespace {{{colorize_string(color='purple', value=namespace)}}}",
                (0, 0, 0, DEFAULT_PADDING),
            ),
        )

        authentications = list(authentications)
        added_broker_ref_condition = False

        for auth in authentications:
            auth_metadata = auth["metadata"]
            auth_name = auth_metadata["name"]
            # store results for check that will used to display later
            sub_check_results: List[CheckResult] = []

            # check broker reference
            broker_ref = auth_metadata.get("ownerReferences", [])
            auth_desc = f"\n- Broker Authentication {{{colorize_string(auth_name)}}}."
            _evaluate_broker_reference(
                check_manager=check_manager,
                owner_reference=broker_ref,
                target_name=target_authentications,
                namespace=namespace,
                resource_name=auth_name,
                added_condition=added_broker_ref_condition,
                display_text=auth_desc,
            )

            authn_properties_padding = DEFAULT_PADDING + 4

            # status
            status = auth.get("status", {})

            if status:
                process_custom_resource_status(
                    check_manager=check_manager,
                    status=status,
                    target_name=target_authentications,
                    namespace=namespace,
                    resource_name=auth_name,
                    padding=authn_properties_padding,
                    detail_level=detail_level,
                )

            auth_spec = auth.get("spec", {})

            # check authentication methods
            auth_methods = auth_spec.get("authenticationMethods", [])
            auth_methods_desc = f"Expecting {colorize_string('>=1')} authentication methods. "
            auth_methods_eval_status = CheckTaskStatus.success.value

            if len(auth_methods) >= 1:
                auth_methods_desc = (
                    auth_methods_desc + f"Detected {colorize_string(color='green', value=len(auth_methods))}."
                )
            else:
                auth_methods_desc = auth_methods_desc + f"{colorize_string(color='red', value='Not Detected')}."
                auth_methods_eval_status = CheckTaskStatus.error.value

            sub_check_results.append(
                CheckResult(
                    display=Padding(auth_methods_desc, (0, 0, 0, 12)),
                    eval_status=auth_methods_eval_status,
                )
            )

            check_manager.add_target_eval(
                target_name=target_authentications,
                namespace=namespace,
                status=auth_methods_eval_status,
                value={"len(spec.authenticationMethods)": len(auth_methods)},
                resource_name=auth_name,
            )

            for method in auth_methods:
                _check_authentication_method(
                    check_manager=check_manager,
                    target_authentications=target_authentications,
                    namespace=namespace,
                    resource_name=auth_name,
                    method=method,
                    sub_check_results=sub_check_results,
                    detail_level=detail_level,
                )

            _display_sub_check_results(
                check_manager=check_manager,
                target_name=target_authentications,
                namespace=namespace,
                sub_check_results=sub_check_results,
                parent_padding=DEFAULT_PADDING,
                detail_level=detail_level,
            )

    return check_manager.as_dict(as_list)


def evaluate_broker_authorizations(
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_name: str = None,
) -> Dict[str, Any]:

    check_manager = CheckManager(
        check_name="evalBrokerAuthorizations",
        check_desc="Evaluate MQTT Broker Authorizations",
    )

    target_authorizations = "brokerauthorizations.mqttbroker.iotoperations.azure.com"
    authz_conditions = ["spec.authorizationPolicies"]

    all_authorizations = get_resources_by_name(
        api_info=MQ_ACTIVE_API,
        kind=MqResourceKinds.BROKER_AUTHORIZATION,
        resource_name=resource_name,
    )

    if not all_authorizations:
        fetch_authorizations_error_text = (
            f"Unable to fetch {MqResourceKinds.BROKER_AUTHORIZATION.value}s in any namespace."
        )
        check_manager.add_target(target_name=target_authorizations)
        check_manager.add_target_eval(
            target_name=target_authorizations,
            status=CheckTaskStatus.skipped.value,
            value=fetch_authorizations_error_text,
        )
        check_manager.add_display(
            target_name=target_authorizations,
            display=Padding(fetch_authorizations_error_text, (0, 0, 0, DEFAULT_PADDING)),
        )
        return check_manager.as_dict(as_list)

    for namespace, authorizations in get_resources_grouped_by_namespace(all_authorizations):
        check_manager.add_target(
            target_name=target_authorizations,
            namespace=namespace,
        )
        check_manager.add_display(
            target_name=target_authorizations,
            namespace=namespace,
            display=Padding(
                f"Broker Authorizations in namespace {{[purple]{namespace}[/purple]}}", (0, 0, 0, DEFAULT_PADDING)
            ),
        )

        authorizations = list(authorizations)
        added_broker_ref_condition = False

        for authz in authorizations:
            authz_metadata = authz["metadata"]
            authz_name = authz_metadata["name"]

            # check broker reference
            broker_ref = authz_metadata.get("ownerReferences", [])
            authz_desc = f"\n- Broker Authorization {{{colorize_string(authz_name)}}}."
            _evaluate_broker_reference(
                check_manager=check_manager,
                owner_reference=broker_ref,
                target_name=target_authorizations,
                namespace=namespace,
                resource_name=authz_name,
                added_condition=added_broker_ref_condition,
                display_text=authz_desc,
            )

            authz_properties_padding = DEFAULT_PADDING + 4

            # status
            status = authz.get("status", {})

            if status:
                process_custom_resource_status(
                    check_manager=check_manager,
                    status=status,
                    target_name=target_authorizations,
                    namespace=namespace,
                    resource_name=authz_name,
                    padding=authz_properties_padding,
                    detail_level=detail_level,
                )

            authz_spec = authz.get("spec", {})

            # check authorization policies
            authz_policies = authz_spec.get("authorizationPolicies", {})
            authz_policies_eval_status = CheckTaskStatus.success.value

            if authz_policies:
                authz_policies_desc = f"Authorization Policies {colorize_string(color='green', value='detected')}."
            else:
                authz_policies_desc = f"Authorization Policies {colorize_string(color='red', value='not detected')}."
                authz_policies_eval_status = CheckTaskStatus.error.value

            if (
                detail_level != ResourceOutputDetailLevel.summary.value
                or authz_policies_eval_status != CheckTaskStatus.success.value
            ):
                check_manager.add_display(
                    target_name=target_authorizations,
                    namespace=namespace,
                    display=Padding(authz_policies_desc, (0, 0, 0, 12)),
                )

            check_manager.add_target_eval(
                target_name=target_authorizations,
                namespace=namespace,
                status=authz_policies_eval_status,
                value={"spec.authorizationPolicies": authz_policies},
                resource_name=authz_name,
            )

            if authz_policies and detail_level == ResourceOutputDetailLevel.verbose.value:
                process_dict_resource(
                    check_manager=check_manager,
                    target_name=target_authorizations,
                    resource=authz_policies,
                    namespace=namespace,
                    padding=authz_properties_padding + 2,
                )

            check_manager.add_target_conditions(
                target_name=target_authorizations,
                namespace=namespace,
                conditions=authz_conditions,
            )

    return check_manager.as_dict(as_list)


def _evaluate_broker_reference(
    check_manager: CheckManager,
    owner_reference: dict,
    target_name: str,
    namespace: str,
    resource_name: str,
    added_condition: bool,
    display_text: str,
    padding: Optional[int] = DEFAULT_PADDING,
):
    broker_reference = [ref for ref in owner_reference if ref.get("kind").lower() == MqResourceKinds.BROKER.value]
    if not broker_reference:
        # skip this check
        return ""

    # should only have one broker reference
    broker_reference_name = broker_reference[0].get("name")

    if not added_condition:
        check_manager.add_target_conditions(
            target_name=target_name,
            namespace=namespace,
            conditions=["valid(brokerRef)"],
        )
        added_condition = True

    valid_broker_refs = get_valid_references(api=MQ_ACTIVE_API, kind=MqResourceKinds.BROKER, namespace=namespace)
    ref_eval_status = CheckTaskStatus.success.value
    ref_eval_value = {}

    if broker_reference_name not in valid_broker_refs:
        ref_color = "red"
        ref_eval_status = CheckTaskStatus.error.value
        ref_eval_value["valid(spec.brokerRef)"] = False
    else:
        ref_color = "green"
        ref_eval_value["valid(spec.brokerRef)"] = True

    ref_display = (
        f"Broker reference {{{colorize_string(broker_reference_name)}}} is "
        f"{colorize_string(color=ref_color, value='Invalid' if ref_color == 'red' else 'Valid')}."
    )

    check_manager.add_target_eval(
        target_name=target_name,
        namespace=namespace,
        status=ref_eval_status,
        value=ref_eval_value,
        resource_name=resource_name,
    )

    check_manager.add_display(
        target_name=target_name,
        namespace=namespace,
        display=Padding(f"{display_text} {ref_display}", (0, 0, 0, padding)),
    )


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
                f"\n{colorize_string(color='red', value='Unable')} to fetch service {{{colorize_string(color='red', value=listener_spec_service_name)}}}.",
                (0, 0, 0, 12),
            ),
        )
        check_manager.add_target_eval(
            target_name=target_listener_service,
            namespace=namespace,
            status=listener_service_eval_status,
            value={"listener_service": "Unable to fetch service."},
            resource_name=f"service/{listener_spec_service_name}",
        )
    else:
        check_manager.add_target_eval(
            target_name=target_listener_service,
            namespace=namespace,
            status=CheckTaskStatus.success.value,
            value={"listener_service": target_listener_service},
            resource_name=f"service/{listener_spec_service_name}",
        )

        check_manager.add_display(
            target_name=target_listener_service,
            namespace=namespace,
            display=Padding(
                f"Service {{{colorize_string(listener_spec_service_name)}}} of type {colorize_string(listener_spec_service_type)}",
                (0, 0, 0, DEFAULT_PADDING),
            ),
        )

        if listener_spec_service_type.lower() == "loadbalancer":
            check_manager.add_target_conditions(
                target_name=target_listener_service,
                namespace=namespace,
                conditions=[
                    "status",
                    "len(status.loadBalancer.ingress[*].ip)>=1",
                ],
            )
            ingress_rules_desc = f"- Expecting {colorize_string('>=1')} ingress rule. "

            service_status = associated_service.get("status", {})
            load_balancer = service_status.get("loadBalancer", {})
            ingress_rules: List[dict] = load_balancer.get("ingress", [])

            if not ingress_rules:
                listener_service_eval_status = CheckTaskStatus.warning.value
                ingress_color = "red"
            else:
                ingress_color = "green"

            ingress_count_colored = f"{colorize_string(color=ingress_color, value='Detected 0' if ingress_color == 'red' else str(len(ingress_rules)))}."

            if detail_level != ResourceOutputDetailLevel.summary.value:
                check_manager.add_display(
                    target_name=target_listener_service,
                    namespace=namespace,
                    display=Padding(
                        ingress_rules_desc + ingress_count_colored,
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
                        rule_desc = f"- ip: {colorize_string(color='green', value=ip)}"
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
                value={"status": service_status},
            )
        elif listener_spec_service_type.lower() == "clusterip":
            check_manager.add_target_conditions(
                target_name=target_listener_service,
                namespace=namespace,
                conditions=["spec.clusterIP"],
            )
            cluster_ip = associated_service.get("spec", {}).get("clusterIP")

            cluster_ip_desc = "Cluster IP: {}"
            if not cluster_ip:
                listener_service_eval_status = CheckTaskStatus.warning.value
                cluster_ip_desc = cluster_ip_desc.format(colorize_string(color="yellow", value="Undetermined"))
            else:
                cluster_ip_desc = cluster_ip_desc.format(colorize_string(cluster_ip))

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
    diagnostics_service = get_namespaced_service(
        name=AIO_BROKER_DIAGNOSTICS_SERVICE, namespace=namespace, as_dict=True
    )
    if not diagnostics_service:
        check_manager.add_target_eval(
            target_name=target_brokers,
            namespace=namespace,
            status=CheckTaskStatus.error.value,
            value=f"service/{AIO_BROKER_DIAGNOSTICS_SERVICE} not found in namespace {namespace}",
            resource_name=f"service/{AIO_BROKER_DIAGNOSTICS_SERVICE}",
        )
        diag_service_desc_suffix = colorize_string(color="red", value="not detected")
        diag_service_desc = (
            f"Diagnostics Service {{{colorize_string(AIO_BROKER_DIAGNOSTICS_SERVICE)}}} {diag_service_desc_suffix}."
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
            resource_name=f"service/{AIO_BROKER_DIAGNOSTICS_SERVICE}",
        )
        diag_service_desc_suffix = colorize_string(color="green", value="detected")
        diag_service_desc = (
            f"\nDiagnostics Service {{{colorize_string(AIO_BROKER_DIAGNOSTICS_SERVICE)}}} {diag_service_desc_suffix}."
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
                        f"{colorize_string(port.get('name'))} "
                        f"port {colorize_string(port.get('port'))} "
                        f"protocol {colorize_string(port.get('protocol'))}",
                        (0, 0, 0, 16),
                    ),
                )
            check_manager.add_display(target_name=target_brokers, namespace=namespace, display=NewLine())


def _display_sub_check_results(
    check_manager: CheckManager,
    target_name: str,
    namespace: str,
    sub_check_results: List[CheckResult],
    parent_padding: int,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
) -> None:
    errors_displays = []
    for result in sub_check_results:
        # summary level will only show header and non-success results
        # detail level will show all results with evaluation status
        # verbose level will show all results
        if (
            detail_level == ResourceOutputDetailLevel.summary.value
            and result.eval_status == CheckTaskStatus.error.value
        ):
            text = result.display.renderable.strip("- ")
            errors_displays.append(text)
        elif (detail_level == ResourceOutputDetailLevel.detail.value and result.eval_status is not None) or (
            detail_level == ResourceOutputDetailLevel.verbose.value
        ):
            check_manager.add_display(
                target_name=target_name,
                namespace=namespace,
                display=result.display,
            )

    # for errors displayed in summary level, align padding with parent
    for error_display in errors_displays:
        check_manager.add_display(
            target_name=target_name,
            namespace=namespace,
            display=Padding(error_display, (0, 0, 0, parent_padding + 4)),
        )


def _check_authentication_method(
    method: dict,
    check_manager: CheckManager,
    target_authentications: str,
    namespace: str,
    sub_check_results: List[CheckResult],
    resource_name: str,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
) -> None:
    conditions = []
    method_type = method.get("method")
    method_eval_status = CheckTaskStatus.success.value
    method_eval_value = {"method": method}

    if method_type.lower() == "custom":
        _evaluate_custom_authentication_method(
            conditions=conditions,
            method=method,
            method_type=method_type,
            check_manager=check_manager,
            target_authentications=target_authentications,
            namespace=namespace,
            sub_check_results=sub_check_results,
            method_eval_status=method_eval_status,
        )
    elif method_type.lower() == "x509":
        conditions.append("spec.authenticationMethods[*].x509Settings")
        setting = method.get("x509Settings", {})

        if not setting:
            method_display = (
                f"- x509 Method: {{{colorize_string(method_type)}}} {colorize_string(color='red', value='not found')}."
            )
            method_eval_status = CheckTaskStatus.error.value
        else:
            method_display = f"- x509 method: {{{colorize_string(method_type)}}} {colorize_string(color='green', value='detected')}."

        sub_check_results.append(
            CheckResult(
                display=Padding(method_display, (0, 0, 0, 16)),
                eval_status=method_eval_status,
            )
        )

        # authorizationAttributes
        auth_attrs = setting.get("authorizationAttributes", {}).get("additionalProperties")

        if auth_attrs:
            conditions.append("spec.authenticationMethods[*].x509Settings.authorizationAttributes")
            attributes_additional_properties = setting.get("authorizationAttributes", {}).get(
                "additionalProperties", {}
            )

            # attributes
            attributes = attributes_additional_properties.get("attributes")
            if not attributes:
                attributes_display = f"Authorization Attributes {colorize_string(color='red', value='not found')}."
                method_eval_status = CheckTaskStatus.error.value
            else:
                attributes_display = f"Authorization Attributes: {colorize_string(attributes)} {colorize_string(color='green', value='detected')}."
            sub_check_results.append(
                CheckResult(
                    display=Padding(attributes_display, (0, 0, 0, 20)),
                    eval_status=CheckTaskStatus.success.value,
                )
            )

            # subject
            subject = attributes_additional_properties.get("subject")

            if not subject:
                subject_display = f"Subject {colorize_string(color='red', value='not found')}."
                method_eval_status = CheckTaskStatus.error.value
            else:
                subject_display = (
                    f"Subject: {colorize_string(subject)} {colorize_string(color='green', value='detected')}."
                )
            sub_check_results.append(
                CheckResult(
                    display=Padding(subject_display, (0, 0, 0, 20)),
                    eval_status=CheckTaskStatus.success.value,
                )
            )

        # trustedClientCaCert
        trusted_client_ca_cert = setting.get("trustedClientCaCert")

        if trusted_client_ca_cert:
            trusted_client_ca_cert_value = {
                "spec.authenticationMethods[*].x509Settings.trustedClientCaCert": trusted_client_ca_cert
            }
            is_valid = validate_ref(
                namespace=namespace,
                name=trusted_client_ca_cert,
                ref_type=ValidationResourceType.configmap,
            )

            if is_valid:
                configmap_validate_text = f"[green]Valid[/green] {ValidationResourceType.configmap.value} reference {{[green]{trusted_client_ca_cert}[/green]}}."
            else:
                configmap_validate_text = f"[red]Invalid[/red] {ValidationResourceType.configmap.value} reference {{[red]{trusted_client_ca_cert}[/red]}}."

            trusted_client_ca_cert_display = "Trusted Client CA Cert: {}"
            trusted_client_ca_cert_status = CheckTaskStatus.success.value if is_valid else CheckTaskStatus.error.value

            sub_check_results.append(
                CheckResult(
                    display=Padding(trusted_client_ca_cert_display.format(configmap_validate_text), (0, 0, 0, 20)),
                    eval_status=trusted_client_ca_cert_status,
                )
            )

            conditions.append("valid(spec.authenticationMethods[*].x509Settings.trustedClientCaCert)")

            check_manager.add_target_eval(
                target_name=target_authentications,
                namespace=namespace,
                status=trusted_client_ca_cert_status,
                value=trusted_client_ca_cert_value,
                resource_name=f"configmap/{trusted_client_ca_cert}",
            )
    elif method_type.lower() == "serviceaccounttoken":
        conditions.append("spec.authenticationMethods[*].serviceAccountTokenSettings")
        setting = method.get("serviceAccountTokenSettings", {})

        if not setting:
            method_display = f"- Service Account Token Method: {{{colorize_string(method_type)}}} {colorize_string(color='red', value='not found')}."
            method_eval_status = CheckTaskStatus.error.value
        else:
            method_display = f"- Service Account Token Method: {{{colorize_string(method_type)}}} {colorize_string(color='green', value='detected')}."
        sub_check_results.append(
            CheckResult(
                display=Padding(method_display, (0, 0, 0, 16)),
                eval_status=method_eval_status,
            )
        )

        # audiences
        audiences = setting.get("audiences")
        conditions.append("spec.authenticationMethods[*].serviceAccountTokenSettings.audiences")

        if not audiences:
            audiences_display = f"Audiences {colorize_string(color='red', value='not found')}."
            method_eval_status = CheckTaskStatus.error.value
        else:
            audiences_display = (
                f"Audiences: {colorize_string(str(audiences))} {colorize_string(color='green', value='detected')}."
            )

        if detail_level != ResourceOutputDetailLevel.summary.value:
            sub_check_results.append(
                CheckResult(
                    display=Padding(audiences_display, (0, 0, 0, 20)),
                    eval_status=CheckTaskStatus.success.value,
                )
            )
    else:
        conditions.append("spec.authenticationMethods[*].method")
        method_display = (
            f"- Unknown method type: {colorize_string(color='red', value=method_type)}."
            if method_type
            else f"- Method {colorize_string(color='red', value='not found')}."
        )
        method_eval_status = CheckTaskStatus.error.value
        sub_check_results.append(
            CheckResult(
                display=Padding(method_display, (0, 0, 0, 16)),
                eval_status=method_eval_status,
            )
        )

    # remove duplicate conditions
    check_conditions = check_manager.targets.get(target_authentications, {}).get(namespace, {}).get("conditions", [])
    conditions = list(set(conditions + check_conditions))
    check_manager.set_target_conditions(
        target_name=target_authentications,
        namespace=namespace,
        conditions=conditions,
    )
    check_manager.add_target_eval(
        target_name=target_authentications,
        namespace=namespace,
        status=method_eval_status,
        value=method_eval_value,
        resource_name=resource_name,
    )


def _evaluate_custom_authentication_method(
    conditions: List[str],
    method: dict,
    method_type: str,
    check_manager: CheckManager,
    target_authentications: str,
    namespace: str,
    sub_check_results: List[CheckResult],
    method_eval_status: str,
):
    conditions.append("spec.authenticationMethods[*].customSettings")
    setting = method.get("customSettings", {})

    if not setting:
        method_color = "red"
        method_eval_status = CheckTaskStatus.error.value
        method_status = "not found"
    else:
        method_color = "green"
        method_status = "detected"

    method_display = (
        f"- Custom Method: {{{colorize_string(method_type)}}} "
        f"{colorize_string(color=method_color, value=method_status)}."
    )
    sub_check_results.append(
        CheckResult(
            display=Padding(method_display, (0, 0, 0, 16)),
            eval_status=method_eval_status,
        )
    )

    # endpoint
    endpoint = setting.get("endpoint", "")

    conditions.append("spec.authenticationMethods[*].customSettings.endpoint")

    if not endpoint:
        endpoint_display = f"Endpoint {colorize_string(color='red', value='not found')}."
        method_eval_status = CheckTaskStatus.error.value
    elif not endpoint.lower().startswith("https://"):
        endpoint_display = f"Endpoint: {colorize_string(color='red', value='Invalid')} endpoint format {{{colorize_string(endpoint)}}}."
        method_eval_status = CheckTaskStatus.error.value
    else:
        endpoint_display = (
            f"Endpoint: {{{colorize_string(endpoint)}}} {colorize_string(color='green', value='detected')}."
        )

    sub_check_results.append(
        CheckResult(
            display=Padding(endpoint_display, (0, 0, 0, 20)),
            eval_status=method_eval_status,
        )
    )

    # auth
    auth = setting.get("auth")

    if auth:
        # check x509
        secret_ref = auth.get("x509", {}).get("secretRef")
        secret_ref_value = {"spec.authenticationMethods[*].customSettings.auth.x509.secretRef": secret_ref}
        is_valid = validate_ref(
            namespace=namespace,
            name=secret_ref,
            ref_type=ValidationResourceType.secret,
        )

        if is_valid:
            secret_validate_text = f"[green]Valid[/green] {ValidationResourceType.secret.value} reference {{[green]{secret_ref}[/green]}}."
        else:
            secret_validate_text = (
                f"[red]Invalid[/red] {ValidationResourceType.secret.value} reference {{[red]{secret_ref}[/red]}}."
            )

        secret_ref_display = "X.509 Client Certificate Secret reference: {}"
        secret_ref_status = CheckTaskStatus.success.value if is_valid else CheckTaskStatus.error.value

        sub_check_results.append(
            CheckResult(
                display=Padding(secret_ref_display.format(secret_validate_text), (0, 0, 0, 20)),
                eval_status=secret_ref_status,
            )
        )

        conditions.append("valid(spec.authenticationMethods[*].customSettings.auth.x509.secretRef)")

        # add eval separately for secret ref
        check_manager.add_target_eval(
            target_name=target_authentications,
            namespace=namespace,
            status=secret_ref_status,
            value=secret_ref_value,
            resource_name=f"secret/{secret_ref}",
        )

    # caCertConfigMap
    ca_cert_config_map = setting.get("caCertConfigMap")

    if ca_cert_config_map:
        ca_cert_config_map_value = {"spec.authenticationMethods[*].customSettings.caCertConfigMap": ca_cert_config_map}
        is_valid = validate_ref(
            namespace=namespace,
            name=ca_cert_config_map,
            ref_type=ValidationResourceType.configmap,
        )

        if is_valid:
            configmap_validate_text = f"[green]Valid[/green] {ValidationResourceType.configmap.value} reference {{[green]{ca_cert_config_map}[/green]}}."
        else:
            configmap_validate_text = f"[red]Invalid[/red] {ValidationResourceType.configmap.value} reference {{[red]{ca_cert_config_map}[/red]}}."

        ca_cert_config_map_display = "CA Certificate Config Map: {}"
        ca_cert_config_map_status = CheckTaskStatus.success.value if is_valid else CheckTaskStatus.error.value

        sub_check_results.append(
            CheckResult(
                display=Padding(ca_cert_config_map_display.format(configmap_validate_text), (0, 0, 0, 20)),
                eval_status=ca_cert_config_map_status,
            )
        )

        conditions.append("valid(spec.authenticationMethods[*].customSettings.caCertConfigMap)")

        check_manager.add_target_eval(
            target_name=target_authentications,
            namespace=namespace,
            status=ca_cert_config_map_status,
            value=ca_cert_config_map_value,
            resource_name=f"configmap/{ca_cert_config_map}",
        )

    # headers
    headers = setting.get("headers", {}).get("additionalProperties")

    if headers:
        sub_check_results.append(
            CheckResult(
                display=Padding(f"HTTP Headers: {colorize_string(headers)}", (0, 0, 0, 20)),
                eval_status=None,
            ),
        )


def _evaluate_broker_cardinality(
    broker_cardinality: dict,
    check_manager: CheckManager,
    target_brokers: str,
    namespace: str,
    padding: int,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
) -> str:
    check_condition_colored_text = colorize_string(">=1")
    backend_cardinality_desc = f"- Expecting backend partitions {check_condition_colored_text}. "
    backend_redundancy_desc = f"- Expecting backend redundancy factor {check_condition_colored_text}. "
    backend_workers_desc = f"- Expecting backend workers {check_condition_colored_text}. "
    frontend_cardinality_desc = f"- Expecting frontend replicas {check_condition_colored_text}. "

    backend_chain = broker_cardinality.get("backendChain", {})
    backend_partition_count: Optional[int] = backend_chain.get("partitions")
    backend_redundancy: Optional[int] = backend_chain.get("redundancyFactor")
    backend_workers: Optional[int] = backend_chain.get("workers")
    frontend_replicas: Optional[int] = broker_cardinality.get("frontend", {}).get("replicas")
    broker_eval_status = CheckTaskStatus.success.value

    if backend_partition_count and backend_partition_count >= 1:
        backend_color = "green"
    else:
        backend_color = "red"
        broker_eval_status = CheckTaskStatus.error.value
    backend_chain_count_colored = f"{colorize_string(color=backend_color, value=f'Actual {backend_partition_count}')}."

    if backend_redundancy and backend_redundancy >= 1:
        backend_redundancy_color = "green"
    else:
        backend_redundancy_color = "red"
        broker_eval_status = CheckTaskStatus.error.value

    backend_replicas_colored = (
        f"{colorize_string(color=backend_redundancy_color, value=f'Actual {backend_redundancy}')}."
    )

    if backend_workers and backend_workers >= 1:
        backend_workers_color = "green"
    else:
        backend_workers_color = "red"
        broker_eval_status = CheckTaskStatus.error.value

    backend_workers_colored = f"{colorize_string(color=backend_workers_color, value=f'Actual {backend_workers}')}."

    if frontend_replicas and frontend_replicas >= 1:
        frontend_replicas_color = "green"
    else:
        frontend_replicas_color = "red"
        broker_eval_status = CheckTaskStatus.error.value

    frontend_replicas_colored = (
        f"{colorize_string(color=frontend_replicas_color, value=f'Actual {frontend_replicas}')}."
    )

    # show cardinality display on non-summary detail_levels
    if detail_level != ResourceOutputDetailLevel.summary.value:
        check_manager.add_display(
            target_name=target_brokers,
            namespace=namespace,
            display=Padding("\nCardinality", (0, 0, 0, 12)),
        )

        for display in [
            backend_cardinality_desc + backend_chain_count_colored,
            backend_redundancy_desc + backend_replicas_colored,
            backend_workers_desc + backend_workers_colored,
            frontend_cardinality_desc + frontend_replicas_colored,
        ]:
            check_manager.add_display(
                target_name=target_brokers,
                namespace=namespace,
                display=Padding(display, (0, 0, 0, padding + 4)),
            )
    return broker_eval_status
