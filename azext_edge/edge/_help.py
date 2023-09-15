# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------
"""
Help definitions for Digital Twins commands.
"""

from knack.help_files import helps
from .providers.edge_api import E4K_ACTIVE_API
from .providers.support_bundle import COMPAT_BLUEFIN_APIS, COMPAT_E4K_APIS, COMPAT_OPCUA_APIS, COMPAT_SYMPHONY_APIS


def load_iotedge_help():
    helps[
        "edge"
    ] = """
        type: group
        short-summary: Manage PAS resources.
        long-summary: |
            Project Alice Springs (PAS) is a set of highly aligned, but loosely coupled, first-party
            Kubernetes services that enable you to aggregate data from on-prem assets into an
            industrial-grade MQTT Broker, add edge compute and set up bi-directional data flow with
            a variety of services in the cloud.
    """

    helps[
        "edge support"
    ] = """
        type: group
        short-summary: Edge service support operations.
    """

    helps[
        "edge support create-bundle"
    ] = f"""
        type: command
        short-summary: Creates a standard support bundle zip archive for use in troubleshooting and diagnostics.
        long-summary: |
            [Supported edge service APIs]
                {COMPAT_E4K_APIS.as_str()}
                {COMPAT_OPCUA_APIS.as_str()}
                {COMPAT_BLUEFIN_APIS.as_str()}
                {COMPAT_SYMPHONY_APIS.as_str()}
    """

    helps[
        "edge check"
    ] = f"""
        type: command
        short-summary: Evaluate PAS edge service deployments for health, configuration and usability.
        long-summary: |
            [Supported edge service APIs]
                {E4K_ACTIVE_API.as_str()}
    """

    helps[
        "edge e4k"
    ] = """
        type: group
        short-summary: E4K specific tools.
    """

    helps[
        "edge e4k stats"
    ] = f"""
        type: command
        short-summary: Show dmqtt running statistics.
        long-summary: |
            [Supported edge service APIs]
                {E4K_ACTIVE_API.as_str()}
    """

    helps[
        "edge e4k get-password-hash"
    ] = """
        type: command
        short-summary: Generates a PBKDF2 hash of the passphrase applying PBKDF2-HMAC-SHA512. A 128-bit salt is used from os.urandom.
    """

    helps[
        "edge asset"
    ] = """
        type: group
        short-summary: Manage assets.
    """

    helps[
        "edge asset create"
    ] = """
        type: group
        short-summary: Create an asset.
    """

    helps[
        "edge asset list"
    ] = """
        type: group
        short-summary: List assets.
    """

    helps[
        "edge asset show"
    ] = """
        type: group
        short-summary: Show an asset.
        long-summary: If there are multiple assets with the same name within a subscription, please provide the resource group to ensure
            the correct asset is retrieved.
    """

    helps[
        "edge asset update"
    ] = """
        type: group
        short-summary: Update an asset.
        long-summary: If there are multiple assets with the same name within a subscription, please provide the resource group to ensure
            the correct asset is modified.
    """

    helps[
        "edge asset delete"
    ] = """
        type: group
        short-summary: Delete an asset.
        long-summary: If there are multiple assets with the same name within a subscription, please provide the resource group to ensure
            the correct asset is deleted.
    """
