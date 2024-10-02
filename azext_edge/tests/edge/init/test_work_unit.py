# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------


# import json
# import string
# from os import environ
# from pathlib import Path
# from random import randint
# from typing import Dict, FrozenSet, List
# from unittest.mock import Mock

# import pytest

# from azext_edge.edge.commands_edge import init
# from azext_edge.edge.common import INIT_NO_PREFLIGHT_ENV_KEY
# from azext_edge.edge.providers.base import DEFAULT_NAMESPACE
# from azext_edge.edge.providers.orchestration.common import (
#     KubernetesDistroType,
#     MqMemoryProfile,
#     MqServiceType,
# )
# from azext_edge.edge.providers.orchestration.work import (
#     CURRENT_TEMPLATE,
#     WorkCategoryKey,
#     WorkManager,
#     WorkStepKey,
#     get_basic_dataflow_profile,
# )

# from ...generators import generate_random_string

# MOCK_BROKER_CONFIG_PATH = Path(__file__).parent.joinpath("./broker_config.json")


# @pytest.fixture(scope="module")
# def mock_broker_config():
#     custom_config = {generate_random_string(): generate_random_string()}
#     MOCK_BROKER_CONFIG_PATH.write_text(json.dumps(custom_config), encoding="utf-8")
#     yield custom_config
#     MOCK_BROKER_CONFIG_PATH.unlink()


# @pytest.mark.parametrize(
#     """
#     cluster_name,
#     cluster_namespace,
#     resource_group_name,
#     no_deploy,
#     no_preflight,
#     disable_rsync_rules,
#     """,
#     [
#         pytest.param(
#             generate_random_string(),  # cluster_name
#             None,  # cluster_namespace
#             generate_random_string(),  # resource_group_name
#             None,  # no_deploy
#             None,  # no_preflight
#             None,  # disable_rsync_rules
#         ),
#         pytest.param(
#             generate_random_string(),  # cluster_name
#             None,  # cluster_namespace
#             generate_random_string(),  # resource_group_name
#             None,  # no_deploy
#             None,  # no_preflight
#             None,  # disable_rsync_rules
#         ),
#         pytest.param(
#             generate_random_string(),  # cluster_name
#             generate_random_string(),  # cluster_namespace
#             generate_random_string(),  # resource_group_name
#             None,  # no_deploy
#             None,  # no_preflight
#             None,  # disable_rsync_rules
#         ),
#         pytest.param(
#             generate_random_string(),  # cluster_name
#             None,  # cluster_namespace
#             generate_random_string(),  # resource_group_name
#             None,  # no_deploy
#             None,  # no_preflight
#             None,  # disable_rsync_rules
#         ),
#         pytest.param(
#             generate_random_string(),  # cluster_name
#             None,  # cluster_namespace
#             generate_random_string(),  # resource_group_name
#             True,  # no_deploy
#             None,  # no_preflight
#             None,  # disable_rsync_rules
#         ),
#         pytest.param(
#             generate_random_string(),  # cluster_name
#             None,  # cluster_namespace
#             generate_random_string(),  # resource_group_name
#             True,  # no_deploy
#             None,  # no_preflight
#             None,  # disable_rsync_rules
#         ),
#         pytest.param(
#             generate_random_string(),  # cluster_name
#             None,  # cluster_namespace
#             generate_random_string(),  # resource_group_name
#             True,  # no_deploy
#             True,  # no_preflight
#             True,  # disable_rsync_rules
#         ),
#     ],
# )
# def test_work_order(
#     mocked_cmd: Mock,
#     mocked_config: Mock,
#     mocked_deploy_template: Mock,
#     mocked_register_providers: Mock,
#     mocked_verify_cli_client_connections: Mock,
#     mocked_edge_api_keyvault_api_v1: Mock,
#     mocked_verify_write_permission_against_rg: Mock,
#     mocked_wait_for_terminal_state: Mock,
#     mocked_connected_cluster_location: Mock,
#     mocked_connected_cluster_extensions: Mock,
#     mocked_verify_custom_locations_enabled: Mock,
#     mocked_verify_arc_cluster_config: Mock,
#     mocked_verify_custom_location_namespace: Mock,
#     spy_get_current_template_copy: Mock,
#     cluster_name,
#     cluster_namespace,
#     resource_group_name,
#     no_deploy,
#     no_preflight,
#     disable_rsync_rules,
#     spy_work_displays,
# ):
#     # TODO: Refactor for simplification

#     call_kwargs = {
#         "cmd": mocked_cmd,
#         "cluster_name": cluster_name,
#         "resource_group_name": resource_group_name,
#         "no_deploy": no_deploy,
#         "no_progress": True,
#         "disable_rsync_rules": disable_rsync_rules,
#         "wait_sec": 0.25,
#     }

#     if no_preflight:
#         environ[INIT_NO_PREFLIGHT_ENV_KEY] = "true"

#     for param_with_default in [
#         (cluster_namespace, "cluster_namespace"),
#     ]:
#         if param_with_default[0]:
#             call_kwargs[param_with_default[1]] = param_with_default[0]

#     result = init(**call_kwargs)
#     expected_template_copies = 0

#     # TODO - @digimaun
#     # nothing_to_do = all([not keyvault_resource_id, no_tls, no_deploy, no_preflight])
#     # if nothing_to_do:
#     #     assert not result
#     #     mocked_verify_cli_client_connections.assert_not_called()
#     #     mocked_edge_api_keyvault_api_v1.is_deployed.assert_not_called()
#     #     return

#     # if any([not no_preflight, not no_deploy, keyvault_resource_id]):
#     #     mocked_verify_cli_client_connections.assert_called_once()
#     #     mocked_connected_cluster_location.assert_called_once()

#     expected_cluster_namespace = cluster_namespace.lower() if cluster_namespace else DEFAULT_NAMESPACE

#     displays_to_eval = []
#     for category_tuple in [
#         (not no_preflight, WorkCategoryKey.PRE_FLIGHT),
#         # (keyvault_resource_id, WorkCategoryKey.CSI_DRIVER),
#         (not no_deploy, WorkCategoryKey.DEPLOY_AIO),
#     ]:
#         if category_tuple[0]:
#             displays_to_eval.append(category_tuple[1])
#     _assert_displays_for(set(displays_to_eval), spy_work_displays)

#     if not no_preflight:
#         expected_template_copies += 1
#         mocked_register_providers.assert_called_once()
#         mocked_verify_custom_locations_enabled.assert_called_once()
#         mocked_connected_cluster_extensions.assert_called_once()
#         mocked_verify_arc_cluster_config.assert_called_once()
#         mocked_verify_custom_location_namespace.assert_called_once()

#         if not disable_rsync_rules:
#             mocked_verify_write_permission_against_rg.assert_called_once()
#             mocked_verify_write_permission_against_rg.call_args.kwargs["subscription_id"]
#             mocked_verify_write_permission_against_rg.call_args.kwargs["resource_group_name"] == resource_group_name
#         else:
#             mocked_verify_write_permission_against_rg.assert_not_called()
#     else:
#         mocked_register_providers.assert_not_called()
#         mocked_verify_custom_locations_enabled.assert_not_called()
#         mocked_connected_cluster_extensions.assert_not_called()
#         mocked_verify_arc_cluster_config.assert_not_called()
#         mocked_verify_custom_location_namespace.assert_not_called()

#     if not no_deploy:
#         expected_template_copies += 1
#         assert result["deploymentName"]
#         assert result["resourceGroup"] == resource_group_name
#         assert result["clusterName"] == cluster_name
#         assert result["clusterNamespace"]
#         assert result["deploymentLink"]
#         assert result["deploymentState"]
#         assert result["deploymentState"]["status"]
#         assert result["deploymentState"]["correlationId"]
#         assert result["deploymentState"]["opsVersion"] == CURRENT_TEMPLATE.get_component_vers()
#         assert result["deploymentState"]["timestampUtc"]
#         assert result["deploymentState"]["timestampUtc"]["started"]
#         assert result["deploymentState"]["timestampUtc"]["ended"]
#         assert "resources" in result["deploymentState"]

#         assert mocked_deploy_template.call_count == 2
#         assert mocked_deploy_template.call_args.kwargs["template"]
#         assert mocked_deploy_template.call_args.kwargs["parameters"]
#         assert mocked_deploy_template.call_args.kwargs["subscription_id"]
#         assert mocked_deploy_template.call_args.kwargs["resource_group_name"] == resource_group_name
#         assert mocked_deploy_template.call_args.kwargs["deployment_name"]
#         assert mocked_deploy_template.call_args.kwargs["cluster_name"] == cluster_name
#         assert mocked_deploy_template.call_args.kwargs["cluster_namespace"] == expected_cluster_namespace
#     else:
#         pass
#         # if not nothing_to_do and result:
#         #     assert "deploymentName" not in result
#         #     assert "resourceGroup" not in result
#         #     assert "clusterName" not in result
#         #     assert "clusterNamespace" not in result
#         #     assert "deploymentLink" not in result
#         #     assert "deploymentState" not in result
#         # TODO
#         # mocked_deploy_template.assert_not_called()

#     # assert spy_get_current_template_copy.call_count == expected_template_copies


# def _assert_displays_for(work_category_set: FrozenSet[WorkCategoryKey], display_spys: Dict[str, Mock]):
#     render_display = display_spys["render_display"]
#     render_display_call_kwargs = [m.kwargs for m in render_display.mock_calls]

#     index = 0
#     if WorkCategoryKey.PRE_FLIGHT in work_category_set:
#         assert render_display_call_kwargs[index] == {
#             "category": WorkCategoryKey.PRE_FLIGHT,
#             "active_step": WorkStepKey.REG_RP,
#         }
#         index += 1
#         assert render_display_call_kwargs[index] == {"active_step": WorkStepKey.ENUMERATE_PRE_FLIGHT}
#         index += 1
#         assert render_display_call_kwargs[index] == {"active_step": WorkStepKey.WHAT_IF}
#         index += 1
#         assert render_display_call_kwargs[index] == {"active_step": -1}
#         index += 1

#     if WorkCategoryKey.DEPLOY_AIO in work_category_set:
#         assert render_display_call_kwargs[index] == {"category": WorkCategoryKey.DEPLOY_AIO}
#         index += 1
#         # DEPLOY_AIO gets rendered twice to dynamically expose deployment link
#         assert render_display_call_kwargs[index] == {"category": WorkCategoryKey.DEPLOY_AIO}
