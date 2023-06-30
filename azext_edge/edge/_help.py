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
    ] = """
        type: command
        short-summary: Creates a standard support bundle zip archive for use in troubleshooting and diagnostics.
    """

    helps[
        "edge check"
    ] = """
        type: command
        short-summary: Evaluate PAS edge service deployments for health, configuration and usability.
    """

    helps[
        "edge e4k"
    ] = """
        type: group
        short-summary: E4K specific tools.
    """

    helps[
        "edge e4k stats"
    ] = """
        type: command
        short-summary: Show dmqtt running statistics.
    """

    # helps[
    #     "edge e4k config"
    # ] = """
    #     type: group
    #     short-summary: Config utilities.
    # """

    helps[
        "edge e4k get-password-hash"
    ] = """
        type: command
        short-summary: Generates a PBKDF2 hash of the passphrase applying PBKDF2-HMAC-SHA512. A 128-bit salt is used from os.urandom.
    """
