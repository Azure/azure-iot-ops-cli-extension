# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import pytest
from time import sleep

from ....generators import generate_random_string
from ....helpers import run

# pytest mark for cloud (cloud-side) tests
pytestmark = pytest.mark.cloud


@pytest.fixture(scope="function")
def dataflow_profile_test_setup(settings):
    from ....settings import EnvironmentVariables

    settings.add_to_config(EnvironmentVariables.rg.value)
    settings.add_to_config(EnvironmentVariables.instance.value)
    if not all([settings.env.azext_edge_instance, settings.env.azext_edge_rg]):
        raise AssertionError(
            "Cannot run instance tests without an instance and resource group. " f"Current settings:\n {settings}"
        )

    yield {"resourceGroup": settings.env.azext_edge_rg, "instanceName": settings.env.azext_edge_instance}


def test_dataflow_profile(dataflow_profile_test_setup, tracked_resources):
    profile1_name = f"test-profile-{generate_random_string(force_lower=True, size=6)}"
    profile2_name = f"test-profile-{generate_random_string(force_lower=True, size=6)}"
    rg = dataflow_profile_test_setup["resourceGroup"]
    instance = dataflow_profile_test_setup["instanceName"]

    # CREATE 1
    profile1 = run(f"az iot ops dataflow profile create -n {profile1_name} -g {rg} -i {instance}")
    tracked_resources.append(profile1["id"])
    assert_dataflow_profile(
        profile=profile1,
        name=profile1_name,
        resource_group=rg,
        instance_count=1,
        log_level="info",
    )

    # SHOW
    show_profile1 = run(f"az iot ops dataflow profile show -n {profile1_name} -g {rg} -i {instance}")
    assert_dataflow_profile(
        profile=show_profile1, name=profile1_name, resource_group=rg, instance_count=1, log_level="info"
    )

    # UPDATE with retry
    log_level = "debug"
    max_retries = 10
    retry_delay = 60
    update_profile1 = None
    
    for attempt in range(max_retries):
        try:
            update_profile1 = run(
                f"az iot ops dataflow profile create -n {profile1_name} -g {rg} -i {instance} --log-level {log_level}"
            )
            break  # Success, exit retry loop
        except Exception as e:
            error_message = str(e)
            if "Conflict" in error_message:
                if attempt < max_retries - 1:
                    print(f"Conflict detected on attempt {attempt + 1}/{max_retries}. Retrying in {retry_delay} seconds...")
                    sleep(retry_delay)
                else:
                    raise  # Re-raise on final attempt
            else:
                raise  # Re-raise non-conflict errors
    
    assert update_profile1 is not None, "Update failed after all retry attempts"
    assert_dataflow_profile(
        profile=update_profile1,
        name=profile1_name,
        resource_group=rg,
        instance_count=1,
        log_level=log_level,
    )

    # CREATE 2
    instance_count = 5
    log_level = "debug"
    profile2 = run(
        f"az iot ops dataflow profile create -n {profile2_name} -g {rg} -i {instance} "
        f"--profile-instances {instance_count} --log-level {log_level}"
    )
    tracked_resources.append(profile2["id"])
    assert_dataflow_profile(
        profile=profile2,
        name=profile2_name,
        resource_group=rg,
        instance_count=instance_count,
        log_level=log_level,
    )

    # LIST
    list_profiles = run(f"az iot ops dataflow profile list -g {rg} -i {instance}")
    list_profile_names = [profile["name"] for profile in list_profiles]
    assert profile1_name in list_profile_names
    assert profile2_name in list_profile_names

    # DELETE
    run(f"az iot ops dataflow profile delete -n {profile1_name} -g {rg} -i {instance} --y")
    tracked_resources.remove(profile1["id"])
    run(f"az iot ops dataflow profile delete -n {profile2_name} -g {rg} -i {instance} --y")
    tracked_resources.remove(profile2["id"])
    list_profiles = run(f"az iot ops dataflow profile list -g {rg} -i {instance}")
    list_profile_names = [profile["name"] for profile in list_profiles]
    assert profile1_name not in list_profile_names
    assert profile2_name not in list_profile_names


def assert_dataflow_profile(profile: dict, **expected):
    assert profile["name"] == expected["name"]
    assert profile["resourceGroup"] == expected["resource_group"]

    profile_props = profile["properties"]
    assert profile_props["instanceCount"] == expected["instance_count"]
    assert profile_props.get("diagnostics", {}).get("logs", {}).get("level") == expected["log_level"]
