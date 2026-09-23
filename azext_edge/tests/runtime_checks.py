# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Live integration assertions; expected channel is never inferred from a version suffix."""

import json
import os
import shlex

from azext_edge.edge.providers.orchestration.runtime import resolve_runtime
from azext_edge.edge.providers.orchestration.runtime_catalog import get_runtime_catalog
from azext_edge.edge.providers.orchestration.runtime_profiles import RuntimeChannel, resolve_runtime_identity
from .helpers import run


def expected_runtime(channel, baseline=None):
    catalog = get_runtime_catalog()
    channel = RuntimeChannel(channel)
    if baseline:
        identity = resolve_runtime_identity(
            baseline["version"], baseline["train"], catalog.qualification_identities,
        )
        assert identity.channel == channel, "Upgrade baseline is for the wrong runtime channel."
        return identity
    return catalog.get(channel).identity


def read_runtime(instance_name, resource_group):
    instance = run(f"az iot ops show -n {shlex.quote(instance_name)} -g {shlex.quote(resource_group)}")
    location_id = instance["extendedLocation"]["name"]
    location = run(f"az rest --method get --url {shlex.quote(location_id + '?api-version=2021-08-15')}")
    cluster_id = location["properties"]["hostResourceId"]
    cluster = run(f"az rest --method get --url {shlex.quote(cluster_id + '?api-version=2024-01-01')}")
    url = cluster_id + "/providers/Microsoft.KubernetesConfiguration/extensions?api-version=2023-05-01"
    extensions = []
    while url:
        page = run(f"az rest --method get --url {shlex.quote(url)}")
        extensions.extend(page["value"])
        url = page.get("nextLink")
    runtime = resolve_runtime(instance, location, cluster, extensions, get_runtime_catalog().qualification_identities)
    return runtime, instance, extensions


def assert_runtime(instance_name, resource_group, channel, baseline=None):
    runtime, _, _ = read_runtime(instance_name, resource_group)
    runtime.require_ready()
    expected = expected_runtime(channel, baseline)
    assert runtime.identity == expected, f"Expected {expected}, observed installed runtime {runtime.identity}."
    return runtime


def configured_baseline():
    return json.loads(os.environ.get("azext_edge_upgrade_baseline", "null"))
