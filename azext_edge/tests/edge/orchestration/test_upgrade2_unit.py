# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import json
import re
from typing import Dict, List, Optional, Tuple, TypeVar
from unittest.mock import Mock

import pytest
import requests
import responses
from azure.cli.core.azclierror import ValidationError
from azure.core.exceptions import HttpResponseError

from azext_edge.edge.providers.orchestration.common import (
    EXTENSION_ALIAS_TO_TYPE_MAP,
    EXTENSION_MONIKER_TO_ALIAS_MAP,
    EXTENSION_TYPE_ACS,
    EXTENSION_TYPE_OPS,
    EXTENSION_TYPE_OSM,
    EXTENSION_TYPE_PLATFORM,
    EXTENSION_TYPE_SSC,
    EXTENSION_TYPE_TO_MONIKER_MAP,
    ClusterConnectStatus,
)
from azext_edge.edge.providers.orchestration.targets import InitTargets
from azext_edge.edge.util import parse_kvp_nargs

from ...generators import generate_random_string
from .resources.conftest import (
    BASE_URL,
    CLUSTER_EXTENSIONS_API_VERSION,
    CLUSTER_EXTENSIONS_URL_MATCH_RE,
    CONNECTED_CLUSTER_API_VERSION,
    get_base_endpoint,
    get_mock_resource,
)
from .resources.test_instances_unit import (
    get_instance_endpoint,
    get_mock_cl_record,
    get_mock_instance_record,
)

T = TypeVar("T", bound="UpgradeScenario")
STANDARD_HEADERS = {"content-type": "application/json"}


def get_mock_cluster_record(
    resource_group_name: str,
    name: str = "mycluster",
    connected_status: str = ClusterConnectStatus.CONNECTED.value,
) -> dict:
    return get_mock_resource(
        name=name,
        properties={"connectivityStatus": connected_status},
        resource_group_name=resource_group_name,
    )


def get_cluster_endpoint(resource_group_name: str, name: str = "mycluster") -> dict:
    resource_path = "/connectedClusters"
    if name:
        resource_path += f"/{name}"
    endpoint = get_base_endpoint(
        resource_group_name=resource_group_name,
        resource_path=resource_path,
        resource_provider="Microsoft.Kubernetes",
        api_version=CONNECTED_CLUSTER_API_VERSION,
    )
    endpoint = endpoint.replace("/resourceGroups/", "/resourcegroups/", 1)
    return endpoint


def get_cluster_extensions_endpoint(resource_group_name: str, cluster_name: str = "mycluster") -> dict:
    resource_path = f"/connectedClusters/{cluster_name}/providers/Microsoft.KubernetesConfiguration/extensions"
    return get_base_endpoint(
        resource_group_name=resource_group_name,
        resource_path=resource_path,
        resource_provider="Microsoft.Kubernetes",
        api_version=CLUSTER_EXTENSIONS_API_VERSION,
    )


@pytest.fixture
def mocked_logger(mocker):
    yield mocker.patch(
        "azext_edge.edge.providers.orchestration.upgrade2.logger",
    )


@pytest.fixture
def spy_upgrade_displays(mocker):
    from azext_edge.edge.providers.orchestration.upgrade2 import Console, Progress

    yield {
        "print": mocker.spy(Console, "print"),
        "progress.__init__": mocker.spy(Progress, "__init__"),
    }


class UpgradeScenario:
    def __init__(self, description: Optional[str] = None, confirm_yes: bool = True):
        self.extensions: Dict[str, dict] = {}
        self.targets = InitTargets(cluster_name=generate_random_string(), resource_group_name=generate_random_string())
        self.init_version_map: Dict[str, dict] = {}
        self.init_version_map.update(self.targets.get_extension_versions())
        self.init_version_map.update(self.targets.get_extension_versions(False))
        self.user_kwargs: Dict[str, dict] = {}
        self.patch_record: Dict[str, dict] = {}
        self.ext_type_response_map: Dict[str, Tuple[int, Optional[dict]]] = {}
        self.expect_exception: Optional[Exception] = None
        self.description = description
        self.confirm_yes = confirm_yes
        self.cluster_connected_status = ClusterConnectStatus.CONNECTED.value
        self._build_defaults()

    def _build_defaults(self):
        for ext_type in EXTENSION_TYPE_TO_MONIKER_MAP:
            self.extensions[ext_type] = {
                "properties": {
                    "extensionType": ext_type,
                    "version": self.init_version_map[EXTENSION_TYPE_TO_MONIKER_MAP[ext_type]]["version"],
                    "releaseTrain": self.init_version_map[EXTENSION_TYPE_TO_MONIKER_MAP[ext_type]]["train"],
                    "configurationSettings": {},
                },
                "name": EXTENSION_TYPE_TO_MONIKER_MAP[ext_type],
            }

    def set_cluster_connected_status(self: T, status: str) -> T:
        self.cluster_connected_status = status
        if status != ClusterConnectStatus.CONNECTED.value:
            self.expect_exception = ValidationError
        return self

    def set_user_kwargs(self: T, **kwargs):
        self.user_kwargs.update(kwargs)
        return self

    def set_extension(
        self: T, ext_type: str, ext_vers: Optional[str] = None, ext_train: Optional[str] = None, remove: bool = False
    ) -> T:
        if remove:
            del self.extensions[ext_type]
            self.expect_exception = ValidationError
            return self
        if ext_vers:
            self.extensions[ext_type]["properties"]["version"] = ext_vers
        if ext_train:
            self.extensions[ext_type]["properties"]["releaseTrain"] = ext_train
        return self

    def set_response_on_patch(self: T, ext_type: str, code: int = 200, body: Optional[dict] = None) -> T:
        if code not in (200, 202):
            self.expect_exception = HttpResponseError
        self.ext_type_response_map[ext_type] = (code, body)
        return self

    def set_instance_mock(self: T, mocked_responses: responses, instance_name: str, resource_group_name: str):
        mocked_responses.assert_all_requests_are_fired = False
        mock_instance_record = get_mock_instance_record(name=instance_name, resource_group_name=resource_group_name)
        mocked_responses.add(
            method=responses.GET,
            url=get_instance_endpoint(resource_group_name=resource_group_name, instance_name=instance_name),
            json=mock_instance_record,
            status=200,
            content_type="application/json",
        )

        cl_name = generate_random_string()
        mock_cl_record = get_mock_cl_record(name=cl_name, resource_group_name=resource_group_name)
        mocked_responses.add(
            method=responses.GET,
            url=f"{BASE_URL}{mock_instance_record['extendedLocation']['name']}",
            json=mock_cl_record,
            status=200,
            content_type="application/json",
        )

        mock_cluster_record = get_mock_cluster_record(
            resource_group_name=resource_group_name, connected_status=self.cluster_connected_status
        )
        mocked_responses.add(
            method=responses.GET,
            url=get_cluster_endpoint(resource_group_name=resource_group_name),
            json=mock_cluster_record,
            status=200,
            content_type="application/json",
        )

        mocked_responses.add(
            method=responses.GET,
            url=get_cluster_extensions_endpoint(resource_group_name=resource_group_name),
            json={"value": self.get_extensions()},
            status=200,
            content_type="application/json",
        )
        mocked_responses.add_callback(
            method=responses.PATCH,
            url=re.compile(CLUSTER_EXTENSIONS_URL_MATCH_RE),
            callback=self.patch_extension_response,
        )

    def patch_extension_response(self, request: requests.PreparedRequest) -> Optional[tuple]:
        ext_moniker = request.path_url.split("?")[0].split("/")[-1]
        for ext_type in EXTENSION_TYPE_TO_MONIKER_MAP:
            if EXTENSION_TYPE_TO_MONIKER_MAP[ext_type] == ext_moniker:
                status_code, response_body = self.ext_type_response_map.get(ext_type) or (
                    200,
                    json.loads(request.body),
                )
                if "properties" in response_body:
                    response_body["properties"]["extensionType"] = ext_type
                self.patch_record[ext_type] = response_body
                return (status_code, STANDARD_HEADERS, json.dumps(response_body))

        return (502, STANDARD_HEADERS, json.dumps({"error": "server error"}))

    def get_extensions(self) -> List[dict]:
        return list(self.extensions.values())


@pytest.mark.parametrize("no_progress", [False, True])
@pytest.mark.parametrize(
    "target_scenario,expected_patched_ext_types",
    [
        (UpgradeScenario("Nothing to update. Cluster extensions match deployment extensions."), []),
        (
            UpgradeScenario(
                "Nothing to update. Cluster extensions match deployment extensions sans platform which is ahead."
            ).set_extension(ext_type=EXTENSION_TYPE_PLATFORM, ext_vers="1.0.0"),
            [],
        ),
        (
            UpgradeScenario(
                "Patch a single extension, platform. Ensure confirm prompt.", confirm_yes=False
            ).set_extension(ext_type=EXTENSION_TYPE_PLATFORM, ext_vers="0.5.0"),
            [EXTENSION_TYPE_PLATFORM],
        ),
        (
            UpgradeScenario("Patch platform, osm and ops extensions.")
            .set_extension(ext_type=EXTENSION_TYPE_PLATFORM, ext_vers="0.5.0")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="0.2.0")
            .set_extension(ext_type=EXTENSION_TYPE_OSM, ext_vers="0.3.0"),
            [EXTENSION_TYPE_PLATFORM, EXTENSION_TYPE_OPS, EXTENSION_TYPE_OSM],
        ),
        (
            UpgradeScenario("Patch ops extension due to ops_config override").set_user_kwargs(
                ops_config=[f"{generate_random_string()}={generate_random_string()}"]
            ),
            [EXTENSION_TYPE_OPS],
        ),
        (
            UpgradeScenario("Patch ops extension due to ops_version override.").set_user_kwargs(ops_version="1.2.3"),
            [EXTENSION_TYPE_OPS],
        ),
        (
            UpgradeScenario("Patch ops extension due to ops_train override.").set_user_kwargs(
                ops_train=f"{generate_random_string()}"
            ),
            [EXTENSION_TYPE_OPS],
        ),
        (
            UpgradeScenario("Patch ops, ssc and acs extensions. Acs is patched due to overrides.")
            .set_extension(ext_type=EXTENSION_TYPE_SSC, ext_vers="0.1.0")
            .set_extension(ext_type=EXTENSION_TYPE_OPS, ext_vers="0.1.0")
            .set_extension(ext_type=EXTENSION_TYPE_ACS, ext_vers="9.9.9")
            .set_user_kwargs(
                acs_config=[f"{generate_random_string()}={generate_random_string()}"],
                acs_version="1.1.1",
                acs_train=generate_random_string(),
            ),
            [EXTENSION_TYPE_ACS, EXTENSION_TYPE_OPS, EXTENSION_TYPE_SSC],
        ),
        (
            UpgradeScenario("Throws ValidationError because cluster is not connected.")
            .set_extension(ext_type=EXTENSION_TYPE_PLATFORM, ext_vers="0.5.0")
            .set_cluster_connected_status("Disconnected"),
            [EXTENSION_TYPE_PLATFORM],
        ),
        (
            UpgradeScenario("Throws ValidationError because IoT Ops extension is missing.").set_extension(
                ext_type=EXTENSION_TYPE_OPS, remove=True
            ),
            [],
        ),
        (
            UpgradeScenario("Throws HttpResponseError due to service 500.")
            .set_extension(ext_type=EXTENSION_TYPE_PLATFORM, ext_vers="0.5.0")
            .set_response_on_patch(ext_type=EXTENSION_TYPE_PLATFORM, code=500, body={"error": "server error"}),
            [EXTENSION_TYPE_PLATFORM],
        ),
    ],
)
def test_ops_upgrade(
    mocked_cmd: Mock,
    mocked_responses: responses,
    target_scenario: UpgradeScenario,
    expected_patched_ext_types: List[str],
    no_progress: bool,
    mocked_logger: Mock,
    mocked_sleep: Mock,
    spy_upgrade_displays: Dict[str, Mock],
    mocked_confirm: Mock,
):
    from azext_edge.edge.commands_edge import upgrade_instance

    resource_group_name = generate_random_string()
    instance_name = generate_random_string()

    target_scenario.set_instance_mock(
        mocked_responses=mocked_responses, instance_name=instance_name, resource_group_name=resource_group_name
    )
    call_kwargs = {
        "cmd": mocked_cmd,
        "resource_group_name": resource_group_name,
        "instance_name": instance_name,
        "no_progress": no_progress,
        "confirm_yes": target_scenario.confirm_yes,
    }
    call_kwargs.update(target_scenario.user_kwargs)

    expect_exception = target_scenario.expect_exception

    if expect_exception:
        with pytest.raises(expect_exception):
            upgrade_instance(**call_kwargs)
        assert_displays(spy_upgrade_displays, no_progress, error_context=expect_exception)
        return

    upgrade_result = upgrade_instance(**call_kwargs)

    if not expected_patched_ext_types:
        assert upgrade_result is None
        mocked_logger.warning.assert_called_once_with("Nothing to upgrade :)")
        assert_displays(spy_upgrade_displays, no_progress, 1)
        return

    assert upgrade_result
    assert len(upgrade_result) == len(expected_patched_ext_types)
    assert len(mocked_confirm.ask.mock_calls) == bool(not target_scenario.confirm_yes)

    assert_patch_order(upgrade_result, expected_patched_ext_types)
    assert_overrides(target_scenario, upgrade_result)
    assert_displays(spy_upgrade_displays, no_progress)


def assert_overrides(target_scenario: UpgradeScenario, upgrade_result: List[dict]):
    user_kwargs = target_scenario.user_kwargs
    result_type_to_payload = {k["properties"]["extensionType"]: k for k in upgrade_result}

    for moniker in EXTENSION_MONIKER_TO_ALIAS_MAP:
        alias = EXTENSION_MONIKER_TO_ALIAS_MAP[moniker]
        ext_type = EXTENSION_ALIAS_TO_TYPE_MAP[alias]
        config = user_kwargs.get(f"{alias}_config")
        if config:
            parsed_config = parse_kvp_nargs(config)
            assert result_type_to_payload[ext_type]["properties"]["configurationSettings"] == parsed_config
        version = user_kwargs.get(f"{alias}_version")
        if version:
            assert result_type_to_payload[ext_type]["properties"]["version"] == version
        release_train = user_kwargs.get(f"{alias}_train")
        if release_train:
            assert result_type_to_payload[ext_type]["properties"]["releaseTrain"] == release_train


def assert_patch_order(upgrade_result: List[dict], expected_types: List[str]):
    result_type_to_payload = {k["properties"]["extensionType"]: k for k in upgrade_result}
    for ext_type in expected_types:
        assert ext_type in result_type_to_payload

    order_map = {}
    index = 0
    for key in EXTENSION_TYPE_TO_MONIKER_MAP:
        order_map[key] = index
        index = index + 1

    last_index = -1
    for patched_ext in upgrade_result:
        current_index = order_map[patched_ext["properties"]["extensionType"]]
        assert current_index > last_index
        last_index = current_index


def assert_displays(
    spy_upgrade_displays: Dict[str, Mock],
    no_progress: bool,
    progress_count: Optional[int] = None,
    error_context: Optional[Exception] = None,
):
    if not progress_count:
        progress_count = 2

    if error_context:
        if error_context == ValidationError:
            progress_count = 1

    if all([not no_progress, not error_context]):
        table = spy_upgrade_displays["print"].mock_calls[1].args[1]
        assert table.title

    assert len(spy_upgrade_displays["progress.__init__"].mock_calls) == progress_count
    assert spy_upgrade_displays["progress.__init__"].mock_calls[0].kwargs == {
        "transient": True,
        "disable": no_progress,
    }
    if progress_count > 1:
        assert spy_upgrade_displays["progress.__init__"].mock_calls[1].kwargs == {
            "transient": False,
            "disable": no_progress,
        }
