# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------
"""
Help definitions for Digital Twins commands.
"""

from knack.help_files import helps


def load_iotedge_help():
    helps[
        "edge"
    ] = """
        type: group
        short-summary: Manage Azure Edge resources.
    """

    helps[
        "edge e4k"
    ] = """
        type: group
        short-summary: Manage E4K resources.
        long-summary: |
          Project E4K is a set of highly aligned, but loosely coupled, first-party Kubernetes services that enable you to aggregate data from on-prem assets into an industrial-grade MQTT Broker, add edge compute and set up bi-directional data flow with a variety of services in the cloud.

          E4K is seamlessly integrated with Azure Arc, bringing the power of the Azure control plane to digital operations in industries around the world.
    """

    helps[
        "edge e4k check"
    ] = """
        type: command
        short-summary: Run tests to validate E4K prerequisites and E4K deployment for health, configuration and usability.
    """

    helps[
        "edge e4k stats"
    ] = """
        type: command
        short-summary: Show dmqtt running statistics.
    """

    helps[
        "edge e4k config"
    ] = """
        type: group
        short-summary: Configuration utilities.
    """

    helps[
        "edge e4k config hash"
    ] = """
        type: command
        short-summary: Generates the PBKDF2 hash of the phrase applying PBKDF2-HMAC-SHA512. A 128-bit salt is used from os.urandom.
    """

    helps[
        "edge e4k support"
    ] = """
        type: group
        short-summary: Support operations and tools.
    """

    helps[
        "edge e4k support create-bundle"
    ] = """
        type: command
        short-summary: Creates a standard support bundle zip archive for use in troubleshooting and diagnostics.
    """

    # OPC UA segment

    helps[
        "edge opcua"
    ] = """
        type: group
        short-summary: Manage OPC-UA broker resources.
    """

    helps[
        "edge opcua support"
    ] = """
        type: group
        short-summary: Support operations and tools.
    """

    helps[
        "edge opcua support create-bundle"
    ] = """
        type: command
        short-summary: Creates a standard support bundle zip archive for use in troubleshooting and diagnostics.
    """
