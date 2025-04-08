# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from collections import defaultdict
from typing import TYPE_CHECKING, Iterable, List, Optional

from azure.cli.core.azclierror import InvalidArgumentValueError
from azure.core.exceptions import ResourceNotFoundError
from knack.log import get_logger
from rich.console import Console

from ....util.az_client import wait_for_terminal_state
from ....util.common import parse_kvp_nargs, should_continue_prompt, parse_dot_notation, upsert_by_discriminator
from ....util.queryable import Queryable
from .instances import Instances
from .reskit import GetInstanceExtLoc, get_file_config

logger = get_logger(__name__)


if TYPE_CHECKING:
    from ....vendor.clients.iotopsmgmt.operations import (
        BrokerAuthenticationOperations,
        BrokerAuthorizationOperations,
        BrokerListenerOperations,
        BrokerOperations,
    )

console = Console()


class Brokers(Queryable):
    def __init__(self, cmd):
        super().__init__(cmd=cmd)
        self.instances = Instances(cmd=cmd)
        self.iotops_mgmt_client = self.instances.iotops_mgmt_client

        self.ops: "BrokerOperations" = self.iotops_mgmt_client.broker
        self.listeners = BrokerListeners(self.iotops_mgmt_client.broker_listener, self.instances.get_ext_loc)
        self.authns = BrokerAuthn(self.iotops_mgmt_client.broker_authentication, self.instances.get_ext_loc)
        self.authzs = BrokerAuthz(self.iotops_mgmt_client.broker_authorization, self.instances.get_ext_loc)

    def show(self, name: str, instance_name: str, resource_group_name: str) -> dict:
        return self.ops.get(resource_group_name=resource_group_name, instance_name=instance_name, broker_name=name)

    def list(self, instance_name: str, resource_group_name: str) -> Iterable[dict]:
        return self.ops.list_by_resource_group(resource_group_name=resource_group_name, instance_name=instance_name)

    def delete(
        self, name: str, instance_name: str, resource_group_name: str, confirm_yes: Optional[bool] = None, **kwargs
    ):
        should_bail = not should_continue_prompt(confirm_yes=confirm_yes)
        if should_bail:
            return

        with console.status("Working..."):
            poller = self.ops.begin_delete(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                broker_name=name,
            )
            return wait_for_terminal_state(poller, **kwargs)


class BrokerListeners:
    def __init__(self, ops: "BrokerListenerOperations", get_ext_loc: GetInstanceExtLoc):
        self.ops = ops
        self.get_ext_loc = get_ext_loc

    def apply(
        self,
        name: str,
        broker_name: str,
        instance_name: str,
        resource_group_name: str,
        config_file: Optional[str] = None,
        **kwargs,
    ) -> dict:
        listener_config = get_file_config(config_file)
        resource = {}
        resource["extendedLocation"] = self.get_ext_loc(name=instance_name, resource_group_name=resource_group_name)
        resource["properties"] = listener_config

        with console.status("Working..."):
            poller = self.ops.begin_create_or_update(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                broker_name=broker_name,
                listener_name=name,
                resource=resource,
            )
            return wait_for_terminal_state(poller, **kwargs)

    def _build_tls_config(
        self,
        tls_auto_issuer_ref: Optional[str] = None,
        tls_auto_duration: Optional[str] = None,
        tls_auto_key_algo: Optional[str] = None,
        tls_auto_key_rotation_policy: Optional[str] = None,
        tls_auto_renew_before: Optional[str] = None,
        tls_auto_san_dns: Optional[List[str]] = None,
        tls_auto_san_ip: Optional[List[str]] = None,
        tls_auto_secret_name: Optional[str] = None,
        tls_manual_secret_ref: Optional[str] = None,
    ):
        config = {}
        cm_config = defaultdict(dict)
        man_config = defaultdict(dict)

        if tls_auto_issuer_ref:
            tls_auto_issuer_ref = parse_kvp_nargs(tls_auto_issuer_ref)
            issuer_config = {}
            for key in ["group", "kind", "name"]:
                if key in tls_auto_issuer_ref:
                    issuer_config[key] = tls_auto_issuer_ref[key]
            if "group" not in issuer_config:
                issuer_config["group"] = "cert-manager.io"
            cm_config["issuerRef"] = issuer_config
        if tls_auto_duration:
            cm_config["duration"] = tls_auto_duration
        if tls_auto_key_algo:
            cm_config["privateKey"]["algorithm"] = tls_auto_key_algo
        if tls_auto_key_rotation_policy:
            cm_config["privateKey"]["rotationPolicy"] = tls_auto_key_rotation_policy
        if tls_auto_renew_before:
            cm_config["renewBefore"] = tls_auto_renew_before
        if tls_auto_san_dns:
            cm_config["san"]["dns"] = tls_auto_san_dns
        if tls_auto_san_ip:
            cm_config["san"]["ip"] = tls_auto_san_ip
        if tls_auto_secret_name:
            cm_config["secretName"] = tls_auto_secret_name

        if tls_manual_secret_ref:
            man_config["secretRef"] = tls_manual_secret_ref

        if all([cm_config, man_config]):
            raise InvalidArgumentValueError("TLS may be setup with an automatic or manual config, not both.")

        if cm_config:
            config["tls"] = {"mode": "Automatic", "certManagerCertificateSpec": dict(cm_config)}

        if man_config:
            config["tls"] = {"mode": "Manual", "manual": dict(man_config)}

        return config

    def add_port(
        self,
        port: int,
        listener_name: str,
        broker_name: str,
        instance_name: str,
        resource_group_name: str,
        service_name: Optional[str] = None,
        service_type: Optional[str] = "LoadBalancer",
        authn_ref: Optional[str] = None,
        authz_ref: Optional[str] = None,
        protocol: Optional[str] = None,
        nodeport: Optional[int] = None,
        tls_auto_issuer_ref: Optional[str] = None,
        tls_auto_duration: Optional[str] = None,
        tls_auto_key_algo: Optional[str] = None,
        tls_auto_key_rotation_policy: Optional[str] = None,
        tls_auto_renew_before: Optional[str] = None,
        tls_auto_san_dns: Optional[List[str]] = None,
        tls_auto_san_ip: Optional[List[str]] = None,
        tls_auto_secret_name: Optional[str] = None,
        tls_manual_secret_ref: Optional[str] = None,
        show_config: Optional[bool] = None,
        **kwargs,
    ) -> dict:
        port_config = {"port": port}
        if authn_ref:
            port_config["authenticationRef"] = authn_ref
        if authz_ref:
            port_config["authorizationRef"] = authz_ref
        if protocol:
            port_config["protocol"] = protocol
        if nodeport:
            port_config["nodePort"] = nodeport

        tls_config = self._build_tls_config(
            tls_auto_issuer_ref=tls_auto_issuer_ref,
            tls_auto_duration=tls_auto_duration,
            tls_auto_key_algo=tls_auto_key_algo,
            tls_auto_key_rotation_policy=tls_auto_key_rotation_policy,
            tls_auto_renew_before=tls_auto_renew_before,
            tls_auto_san_dns=tls_auto_san_dns,
            tls_auto_san_ip=tls_auto_san_ip,
            tls_auto_secret_name=tls_auto_secret_name,
            tls_manual_secret_ref=tls_manual_secret_ref,
        )
        port_config.update(tls_config)

        listener = {}
        try:
            listener = self.show(
                name=listener_name,
                broker_name=broker_name,
                instance_name=instance_name,
                resource_group_name=resource_group_name,
            )
        except ResourceNotFoundError:
            pass

        if not listener:
            listener["name"] = listener_name
            listener["extendedLocation"] = self.get_ext_loc(
                name=instance_name, resource_group_name=resource_group_name
            )
            listener["properties"] = {"serviceType": str(service_type)}
            if service_name:
                listener["properties"]["serviceName"] = service_name

        port_configs: List[dict] = listener["properties"].get("ports", [])
        listener["properties"]["ports"] = upsert_by_discriminator(
            initial=port_configs, disc_key="port", config=port_config
        )

        if show_config:
            return listener["properties"]

        with console.status("Working..."):
            poller = self.ops.begin_create_or_update(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                broker_name=broker_name,
                listener_name=listener_name,
                resource=listener,
            )
            return wait_for_terminal_state(poller, **kwargs)

    def remove_port(
        self,
        port: int,
        listener_name: str,
        broker_name: str,
        instance_name: str,
        resource_group_name: str,
        confirm_yes: Optional[bool] = None,
        **kwargs,
    ):
        listener = self.show(
            name=listener_name,
            broker_name=broker_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
        )
        port_configs = listener["properties"].get("ports", [])
        orig_configs_len = len(port_configs)
        port_configs = [port_config for port_config in port_configs if port_config["port"] != port]
        mod_configs_len = len(port_configs)
        listener["properties"]["ports"] = port_configs

        if orig_configs_len == mod_configs_len:
            logger.warning("No port modification detected.")
            return

        if not len(port_configs):
            logger.warning("Listener resource will be deleted as it will no longer have any ports configured.")
            self.delete(
                name=listener_name,
                broker_name=broker_name,
                instance_name=instance_name,
                resource_group_name=resource_group_name,
                confirm_yes=confirm_yes,
                **kwargs,
            )
            return

        should_bail = not should_continue_prompt(confirm_yes=confirm_yes)
        if should_bail:
            return

        with console.status("Working..."):
            poller = self.ops.begin_create_or_update(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                broker_name=broker_name,
                listener_name=listener_name,
                resource=listener,
            )
            return wait_for_terminal_state(poller, **kwargs)

    def show(self, name: str, broker_name: str, instance_name: str, resource_group_name: str) -> dict:
        return self.ops.get(
            listener_name=name,
            broker_name=broker_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
        )

    def list(self, broker_name: str, instance_name: str, resource_group_name: str) -> Iterable[dict]:
        return self.ops.list_by_resource_group(
            resource_group_name=resource_group_name, instance_name=instance_name, broker_name=broker_name
        )

    def delete(
        self,
        name: str,
        broker_name: str,
        instance_name: str,
        resource_group_name: str,
        confirm_yes: Optional[bool] = None,
        **kwargs,
    ):
        should_bail = not should_continue_prompt(confirm_yes=confirm_yes)
        if should_bail:
            return

        with console.status("Working..."):
            poller = self.ops.begin_delete(
                listener_name=name,
                broker_name=broker_name,
                instance_name=instance_name,
                resource_group_name=resource_group_name,
            )
            return wait_for_terminal_state(poller, **kwargs)


class BrokerAuthn:
    def __init__(self, ops: "BrokerAuthenticationOperations", get_ext_loc: GetInstanceExtLoc):
        self.ops = ops
        self.get_ext_loc = get_ext_loc

    def apply(
        self, name: str, broker_name: str, instance_name: str, resource_group_name: str, config_file: str, **kwargs
    ):
        authn_config = get_file_config(config_file)
        resource = {}
        resource["extendedLocation"] = self.get_ext_loc(name=instance_name, resource_group_name=resource_group_name)
        resource["properties"] = authn_config

        with console.status("Working..."):
            poller = self.ops.begin_create_or_update(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                broker_name=broker_name,
                authentication_name=name,
                resource=resource,
            )
            return wait_for_terminal_state(poller, **kwargs)

    def _build_authn_methods(
        self,
        sat_audiences: Optional[List[str]] = None,
        x509_client_ca_cm: Optional[str] = None,
        x509_attrs: Optional[List[str]] = None,
        custom_endpoint: Optional[str] = None,
        custom_ca_cm: Optional[str] = None,
        custom_x509_secret_ref: Optional[str] = None,
        custom_http_headers: Optional[List[str]] = None,
    ) -> List[dict]:
        methods = []

        if sat_audiences:
            sat_config = {"method": "ServiceAccountToken", "serviceAccountTokenSettings": {"audiences": sat_audiences}}
            methods.append(sat_config)

        x509_config = defaultdict(dict)
        if x509_client_ca_cm:
            x509_config["x509Settings"]["trustedClientCaCert"] = x509_client_ca_cm
        if x509_attrs:
            x509_config["x509Settings"]["authorizationAttributes"] = parse_dot_notation(x509_attrs)
        if x509_config:
            x509_config["method"] = "X509"
            methods.append(dict(x509_config))

        custom_config = defaultdict(dict)
        if custom_endpoint:
            custom_config["customSettings"]["endpoint"] = custom_endpoint
        if custom_ca_cm:
            custom_config["customSettings"]["caCertConfigMap"] = custom_ca_cm
        if custom_x509_secret_ref:
            custom_config["customSettings"]["auth"] = {"x509": {"secretRef": custom_x509_secret_ref}}
        if custom_http_headers:
            custom_config["customSettings"]["headers"] = parse_kvp_nargs(custom_http_headers)
        if custom_config:
            custom_config["method"] = "Custom"
            methods.append(dict(custom_config))

        if not methods:
            raise InvalidArgumentValueError("At least one authn config is required.")
        return methods

    def add_method(
        self,
        name: str,
        broker_name: str,
        instance_name: str,
        resource_group_name: str,
        sat_audiences: Optional[List[str]] = None,
        x509_client_ca_cm: Optional[str] = None,
        x509_attrs: Optional[List[str]] = None,
        custom_endpoint: Optional[str] = None,
        custom_ca_cm: Optional[str] = None,
        custom_x509_secret_ref: Optional[str] = None,
        custom_http_headers: Optional[List[str]] = None,
        show_config: Optional[bool] = None,
        **kwargs,
    ):
        methods = self._build_authn_methods(
            sat_audiences=sat_audiences,
            x509_client_ca_cm=x509_client_ca_cm,
            x509_attrs=x509_attrs,
            custom_endpoint=custom_endpoint,
            custom_ca_cm=custom_ca_cm,
            custom_x509_secret_ref=custom_x509_secret_ref,
            custom_http_headers=custom_http_headers,
        )

        authn = {}
        try:
            authn = self.show(
                name=name,
                broker_name=broker_name,
                instance_name=instance_name,
                resource_group_name=resource_group_name,
            )
        except ResourceNotFoundError:
            pass

        if not authn:
            authn["name"] = name
            authn["extendedLocation"] = self.get_ext_loc(name=instance_name, resource_group_name=resource_group_name)
            authn["properties"] = {}

        authn_methods: List[dict] = authn["properties"].get("authenticationMethods", [])
        authn_methods.extend(methods)
        authn["properties"]["authenticationMethods"] = authn_methods

        if show_config:
            return authn["properties"]

        with console.status("Working..."):
            poller = self.ops.begin_create_or_update(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                broker_name=broker_name,
                authentication_name=name,
                resource=authn,
            )
            return wait_for_terminal_state(poller, **kwargs)

    def show(self, name: str, broker_name: str, instance_name: str, resource_group_name: str) -> dict:
        return self.ops.get(
            authentication_name=name,
            broker_name=broker_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
        )

    def list(self, broker_name: str, instance_name: str, resource_group_name: str) -> Iterable[dict]:
        return self.ops.list_by_resource_group(
            resource_group_name=resource_group_name, instance_name=instance_name, broker_name=broker_name
        )

    def delete(
        self,
        name: str,
        broker_name: str,
        instance_name: str,
        resource_group_name: str,
        confirm_yes: Optional[bool] = None,
        **kwargs,
    ):
        should_bail = not should_continue_prompt(confirm_yes=confirm_yes)
        if should_bail:
            return

        with console.status("Working..."):
            poller = self.ops.begin_delete(
                authentication_name=name,
                broker_name=broker_name,
                instance_name=instance_name,
                resource_group_name=resource_group_name,
            )
            return wait_for_terminal_state(poller, **kwargs)


class BrokerAuthz:
    def __init__(self, ops: "BrokerAuthorizationOperations", get_ext_loc: GetInstanceExtLoc):
        self.ops = ops
        self.get_ext_loc = get_ext_loc

    def apply(
        self, name: str, broker_name: str, instance_name: str, resource_group_name: str, config_file: str, **kwargs
    ):
        authz_config = get_file_config(config_file)
        resource = {}
        resource["extendedLocation"] = self.get_ext_loc(name=instance_name, resource_group_name=resource_group_name)
        resource["properties"] = authz_config

        with console.status("Working..."):
            poller = self.ops.begin_create_or_update(
                resource_group_name=resource_group_name,
                instance_name=instance_name,
                broker_name=broker_name,
                authorization_name=name,
                resource=resource,
            )
            return wait_for_terminal_state(poller, **kwargs)

    def show(self, name: str, broker_name: str, instance_name: str, resource_group_name: str) -> dict:
        return self.ops.get(
            authorization_name=name,
            broker_name=broker_name,
            instance_name=instance_name,
            resource_group_name=resource_group_name,
        )

    def list(self, broker_name: str, instance_name: str, resource_group_name: str) -> Iterable[dict]:
        return self.ops.list_by_resource_group(
            resource_group_name=resource_group_name, instance_name=instance_name, broker_name=broker_name
        )

    def delete(
        self,
        name: str,
        broker_name: str,
        instance_name: str,
        resource_group_name: str,
        confirm_yes: Optional[bool] = None,
        **kwargs,
    ):
        should_bail = not should_continue_prompt(confirm_yes=confirm_yes)
        if should_bail:
            return

        with console.status("Working..."):
            poller = self.ops.begin_delete(
                authorization_name=name,
                broker_name=broker_name,
                instance_name=instance_name,
                resource_group_name=resource_group_name,
            )
            return wait_for_terminal_state(poller, **kwargs)
