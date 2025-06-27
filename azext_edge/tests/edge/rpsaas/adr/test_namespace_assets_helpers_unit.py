# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from random import choice
from typing import Callable, List, Optional
import json
import pytest
from azure.cli.core.azclierror import (
    InvalidArgumentValueError,
    MutuallyExclusiveArgumentError,
    RequiredArgumentMissingError,
)

from azext_edge.edge.providers.rpsaas.adr.namespace_devices import DeviceEndpointType
from azext_edge.edge.providers.rpsaas.adr.namespace_assets import (
    _build_destination,
    _create_datapoint,
    _get_event,
    _process_configs,
    _process_opcua_dataset_configurations,
    _process_opcua_event_configurations,
    _process_media_stream_configurations
)
from azext_edge.edge.util.common import parse_kvp_nargs
from ....generators import generate_random_string


@pytest.fixture()
def mocked_logger(mocker):
    yield mocker.patch("azext_edge.edge.providers.rpsaas.adr.namespace_assets.logger")


@pytest.mark.parametrize("test_case", [
    # BrokerStateStore
    {
        "args": ["key=test-key"],
        "expected_target": "BrokerStateStore",
    },
    # Storage
    {
        "args": ["path=/data/test"],
        "expected_target": "Storage",
    },
    # MQTT
    {
        "args": ["topic=/contoso/test", "retain=Never", "qos=Qos0", "ttl=3600"],
        "expected_target": "Mqtt",
    },
    {
        "args": None
    }
])
@pytest.mark.parametrize("allowed_types", [None, ["BrokerStateStore", "Storage", "Mqtt"]])
def test_build_destination(test_case: dict, allowed_types: Optional[List[str]]):
    expected_config = parse_kvp_nargs(test_case.get("args", []))
    if "ttl" in expected_config:
        expected_config["ttl"] = int(expected_config["ttl"])

    result = _build_destination(test_case["args"], allowed_types=allowed_types)

    if not test_case["args"]:
        assert not result and isinstance(result, list)
        return

    assert len(result) == 1
    assert result[0]["target"] == test_case["expected_target"]
    for key, value in expected_config.items():
        assert result[0]["configuration"][key] == value


@pytest.mark.parametrize("test_case", [
    # Missing required field for MQTT
    {
        "args": ["topic=/contoso/test", "retain=Never", "qos=Qos0"],  # Missing 'ttl'
        "expected_error": RequiredArgumentMissingError,
        "expected_msg": ["For MQTT destinations, 'topic', 'retain', 'qos', and 'ttl' must be provided"]
    },
    # Invalid destination type
    {
        "args": ["key=test-key"],
        "allowed_types": ["Storage", "Mqtt"],
        "expected_error": InvalidArgumentValueError,
        "expected_msg": ["Destination type 'BrokerStateStore' is not allowed", "Allowed types are: Storage, Mqtt"]
    },
    # Extra args for BrokerStateStore
    {
        "args": ["key=test-key", "topic=/test"],
        "expected_error": MutuallyExclusiveArgumentError,
        "expected_msg": [
            "Conflicting arguments for destination: key, topic", "For BrokerStateStore, only 'key' is allowed"
        ]
    },
    # Extra args for Storage
    {
        "args": ["path=/data/test", "retain=Never"],
        "expected_error": MutuallyExclusiveArgumentError,
        "expected_msg": ["Conflicting arguments for destination: path, retain", "For Storage, only 'path' is allowed"]
    },
    # Extra args for MQTT
    {
        "args": ["topic=/contoso/test", "retain=Never", "qos=Qos0", "ttl=3600", "extra=value"],
        "expected_error": MutuallyExclusiveArgumentError,
        "expected_msg": ["Conflicting arguments for destination: topic, retain, qos, ttl, extra"]
    }
])
def test_build_destination_error(test_case: dict):
    """Test error conditions when creating destinations."""
    with pytest.raises(test_case["expected_error"]) as excinfo:
        allowed_types = test_case.get("allowed_types")
        _build_destination(test_case["args"], allowed_types)

    for msg in test_case["expected_msg"]:
        assert msg in str(excinfo.value)


@pytest.mark.parametrize("test_case", [
    # Basic datapoint with only required parameters
    {
        "params": {
            "datapoint_name": "test_datapoint",
            "data_source": "nsu=test;s=Source1"
        },
        "expected": {
            "name": "test_datapoint",
            "dataSource": "nsu=test;s=Source1"
        }
    },
    # Datapoint with type reference
    {
        "params": {
            "datapoint_name": "test_datapoint",
            "data_source": "nsu=test;s=Source1",
            "type_ref": "dtmi:contoso:datatype:temperature;1"
        },
        "expected": {
            "name": "test_datapoint",
            "dataSource": "nsu=test;s=Source1",
            "typeRef": "dtmi:contoso:datatype:temperature;1"
        }
    },
    # Datapoint with custom configuration
    {
        "params": {
            "datapoint_name": "test_datapoint",
            "data_source": "nsu=test;s=Source1",
            "custom_configuration": '{"customSetting": "value"}'
        },
        "expected": {
            "name": "test_datapoint",
            "dataSource": "nsu=test;s=Source1",
            "dataPointConfiguration": '{"customSetting": "value"}'
        }
    },
    # Datapoint with OPC UA configuration (queue_size only)
    {
        "params": {
            "datapoint_name": "test_datapoint",
            "data_source": "nsu=test;s=Source1",
            "queue_size": 10
        },
        "expected": {
            "name": "test_datapoint",
            "dataSource": "nsu=test;s=Source1",
            "dataPointConfiguration": '{"queueSize": 10}'
        }
    },
    # Datapoint with OPC UA configuration (sampling_interval only)
    {
        "params": {
            "datapoint_name": "test_datapoint",
            "data_source": "nsu=test;s=Source1",
            "sampling_interval": 500
        },
        "expected": {
            "name": "test_datapoint",
            "dataSource": "nsu=test;s=Source1",
            "dataPointConfiguration": '{"samplingInterval": 500}'
        }
    },
    # Datapoint with OPC UA configuration (both queue_size and sampling_interval)
    {
        "params": {
            "datapoint_name": "test_datapoint",
            "data_source": "nsu=test;s=Source1",
            "queue_size": 10,
            "sampling_interval": 500
        },
        "expected": {
            "name": "test_datapoint",
            "dataSource": "nsu=test;s=Source1",
            "dataPointConfiguration": '{"queueSize": 10, "samplingInterval": 500}'
        }
    },
    # Datapoint with all parameters
    {
        "params": {
            "datapoint_name": "test_datapoint",
            "data_source": "nsu=test;s=Source1",
            "type_ref": "dtmi:contoso:datatype:temperature;1",
            "queue_size": 10,
            "sampling_interval": 500,
            "custom_configuration": "myconfig.json"
        },
        "expected": {
            "name": "test_datapoint",
            "dataSource": "nsu=test;s=Source1",
            "typeRef": "dtmi:contoso:datatype:temperature;1",
            "dataPointConfiguration": '{"customSetting": "value"}'
        }
    }
])
def test_create_datapoint(test_case, mocker):
    # Setup mocks if needed
    mocker.patch(
        "azext_edge.edge.providers.rpsaas.adr.namespace_assets.process_additional_configuration",
        return_value='{"customSetting": "value"}'
    )

    # Call the function under test
    result = _create_datapoint(**test_case["params"])

    # Verify expected results
    assert result["name"] == test_case["expected"]["name"]
    assert result["dataSource"] == test_case["expected"]["dataSource"]

    # Check optional fields
    if "typeRef" in test_case["expected"]:
        assert result["typeRef"] == test_case["expected"]["typeRef"]
    else:
        assert "typeRef" not in result

    if "dataPointConfiguration" in test_case["expected"]:
        # For dataPointConfiguration, we need to compare parsed JSON since the string order might be different
        test_config = json.loads(test_case["expected"]["dataPointConfiguration"])
        assert json.loads(result["dataPointConfiguration"]) == test_config
    else:
        assert "dataPointConfiguration" not in result or result["dataPointConfiguration"] == "{}"


@pytest.mark.parametrize(
    "asset_type, test_case",
    [
        # Test OPCUA
        (
            DeviceEndpointType.OPCUA.value,
            {
                "opcua_dataset_values": {"test": "dataset_value"},
                "opcua_event_values": {"test": "event_value"},
                "mgmt_custom_configuration": '{"test": "mgmt_value"}',
                "datasets_destinations": ["topic=/test/topic"],
                "events_destinations": ["topic=/test/event"]
            },
        ),
        # Test ONVIF
        (
            DeviceEndpointType.ONVIF.value,
            {
                "mgmt_custom_configuration": '{"test": "mgmt_value"}',
                "events_destinations": ["topic=/test/event"]
            },
        ),
        # Test MEDIA
        (
            DeviceEndpointType.MEDIA.value,
            {
                "media_stream_values": {"test": "stream_value"},
                "streams_destinations": ["topic=/test/stream", "path=/data/test"]
            },
        ),
        # Test Custom
        (
            "Custom",
            {
                "datasets_custom_configuration": '{"test": "dataset_value"}',
                "events_custom_configuration": '{"test": "event_value"}',
                "mgmt_custom_configuration": '{"test": "mgmt_value"}',
                "streams_custom_configuration": '{"test": "stream_value"}',
                "datasets_destinations": ["topic=/test/dataset"],
                "events_destinations": ["topic=/test/event"],
                "streams_destinations": ["path=/data/test"]
            },
        ),
        # Test Custom with no params
        (
            "Custom", {}
        ),
        # Test OPCUA with some params
        (
            DeviceEndpointType.OPCUA.value,
            {
                "opcua_dataset_values": {"test": "dataset_value"},
                "datasets_destinations": ["topic=/test/topic"],
            },
        ),
    ]
)
@pytest.mark.parametrize("default", [True, False])
@pytest.mark.parametrize("null_values", [True, False])
def test_process_configs(mocker, asset_type: str, test_case: dict, default: bool, null_values: bool):
    # Set up mocks for all the helper functions
    mocks = {}
    for func_name in [
        "_process_opcua_dataset_configurations",
        "_process_opcua_event_configurations",
        "_process_media_stream_configurations",
        "process_additional_configuration",
        "_build_destination"
    ]:
        # ensure we can test all possible null values
        return_value = choice(["", [], None]) if null_values else generate_random_string()
        mocks[func_name] = mocker.patch(
            f"azext_edge.edge.providers.rpsaas.adr.namespace_assets.{func_name}",
            return_value=return_value
        )

    # Call the function
    result = _process_configs(asset_type=asset_type, default=default, **test_case)

    # will build up expected_result as we check the mock calls
    expected_result = {}

    # Get all the expected arguments for the functions to be called
    # note that we use the arguments from the test case to determine which functions should be called
    asset_type_to_args = {
        DeviceEndpointType.OPCUA.value: [
            "opcua_dataset_values",
            "opcua_event_values",
            "mgmt_custom_configuration",
            "datasets_destinations",
            "events_destinations"
        ],
        DeviceEndpointType.ONVIF.value: [
            "mgmt_custom_configuration",
            "events_destinations"
        ],
        DeviceEndpointType.MEDIA.value: [
            "media_stream_values",
            "streams_destinations"
        ]
    }
    expected_args = asset_type_to_args.get(asset_type, [
        "datasets_custom_configuration",
        "events_custom_configuration",
        "mgmt_custom_configuration",
        "streams_custom_configuration",
        "datasets_destinations",
        "events_destinations",
        "streams_destinations"
    ])

    # map the test case args to the expected keys
    args_to_key = {
        # custom configurations
        "datasets_custom_configuration": "datasetsConfiguration",
        "events_custom_configuration": "eventsConfiguration",
        "mgmt_custom_configuration": "managementGroupsConfiguration",
        "streams_custom_configuration": "streamsConfiguration",
        # specific type configurations
        "opcua_dataset_values": "datasetsConfiguration",
        "opcua_event_values": "eventsConfiguration",
        "media_stream_values": "streamsConfiguration",
        # destinations
        "datasets_destinations": "datasetsDestinations",
        "events_destinations": "eventsDestinations",
        "streams_destinations": "streamsDestinations",
    }
    if default:
        # If default is True, we prefix the keys with 'default' + capatilize first letter
        args_to_key = {k: f"default{v[0].upper()}{v[1:]}" for k, v in args_to_key.items()}

    def _add_expected_key(func: Callable, arg: str):
        """Build up the expected result based on the function call."""
        expected_key = args_to_key[arg]
        if func.return_value:
            expected_result[expected_key] = func.return_value

    def _assert_any_call(mock_func, **kwargs):
        """Assert that the mock was called with any of the provided arguments."""
        assert any(
            mock_func.call_args_list[i].kwargs == kwargs for i in range(mock_func.call_count)
        ), f"Mock {mock_func} was not called with {kwargs}"

    # custom configurations
    custom_func = mocks["process_additional_configuration"]
    for arg, config_type in [
        ("datasets_custom_configuration", "dataset"),
        ("events_custom_configuration", "event"),
        ("mgmt_custom_configuration", "management group"),
        ("streams_custom_configuration", "stream")
    ]:
        if arg in expected_args:
            # check that the function was called with the right parameters
            _assert_any_call(
                custom_func,
                additional_configuration=test_case.get(arg),
                config_type=config_type
            )
            _add_expected_key(custom_func, arg)

    # specific configurations
    for arg, func in [
        ("opcua_dataset_values", "_process_opcua_dataset_configurations"),
        ("opcua_event_values", "_process_opcua_event_configurations"),
        ("media_stream_values", "_process_media_stream_configurations")
    ]:
        if arg in expected_args:
            # check that the function was called with the right parameters
            mock_func = mocks[func]
            # note that everything is passed as kwargs
            mock_func.assert_called_once_with(
                **test_case
            )

            _add_expected_key(mock_func, arg)

    # destinations
    dest_func = mocks["_build_destination"]
    # map asset type to another mapping of expected arguments (with corresponding allowed destination types)
    asset_to_dest_args = {
        DeviceEndpointType.OPCUA.value: {"datasets_destinations": ["Mqtt"], "events_destinations": ["Mqtt"]},
        DeviceEndpointType.ONVIF.value: {"events_destinations": ["Mqtt"]},
        DeviceEndpointType.MEDIA.value: {"streams_destinations": ["Storage", "Mqtt"]},
    }
    expected_dest_args = asset_to_dest_args.get(asset_type, {
        "datasets_destinations": None,
        "events_destinations": None,
        "streams_destinations": None
    })
    for arg, allowed_dest_types in expected_dest_args.items():
        if arg in expected_args:
            kwargs = {"destination_args": test_case.get(arg, [])}
            if allowed_dest_types:
                kwargs["allowed_types"] = allowed_dest_types
            _assert_any_call(dest_func, **kwargs)
            _add_expected_key(dest_func, arg)

    assert result == expected_result


@pytest.mark.parametrize("test_case", [
    # Empty configuration
    {
        "original": None,
        "params": {},
        "expected_values": {}
    },
    # Set all parameters
    {
        "original": None,
        "params": {
            "opcua_dataset_publishing_interval": 1000,
            "opcua_dataset_sampling_interval": 500,
            "opcua_dataset_queue_size": 50,
            "opcua_dataset_key_frame_count": 5,
            "opcua_dataset_start_instance": "test-instance"
        },
        "expected_values": {
            "publishingInterval": 1000,
            "samplingInterval": 500,
            "queueSize": 50,
            "keyFrameCount": 5,
            "startInstance": "test-instance"
        }
    },
    # Set some parameters
    {
        "original": None,
        "params": {
            "opcua_dataset_publishing_interval": 1000,
            "opcua_dataset_queue_size": 50
        },
        "expected_values": {
            "publishingInterval": 1000,
            "queueSize": 50
        }
    },
    # Update existing configuration
    {
        "original": json.dumps({"publishingInterval": 1000, "samplingInterval": 500}),
        "params": {"opcua_dataset_queue_size": 50, "opcua_dataset_key_frame_count": 5},
        "expected_values": {
            "publishingInterval": 1000,
            "samplingInterval": 500,
            "queueSize": 50,
            "keyFrameCount": 5
        }
    },
    # Override existing configuration
    {
        "original": json.dumps({"publishingInterval": 1000, "samplingInterval": 500}),
        "params": {"opcua_dataset_publishing_interval": 2000},
        "expected_values": {"publishingInterval": 2000, "samplingInterval": 500}
    }
])
def test_process_opcua_dataset_configurations(test_case):
    """Test processing OPC UA dataset configurations with various parameters."""
    result_json = _process_opcua_dataset_configurations(
        original_dataset_configuration=test_case["original"],
        **test_case["params"]
    )

    # Verify the result is a json
    result = json.loads(result_json)

    # Check that all expected values are correct
    for key, value in test_case["expected_values"].items():
        assert result[key] == value

    # Check that no unexpected keys are present
    assert len(result) == len(test_case["expected_values"])


@pytest.mark.parametrize("test_case", [
    # Empty configuration
    {
        "original": None,
        "params": {},
        "expected_values": {}
    },
    # Set filter clauses with path only
    {
        "original": None,
        "params": {"opcua_event_filter_clauses": [["path=/path/to/node"]]},
        "expected_values": {"eventFilter": {"selectClauses": [{"browsePath": "/path/to/node"}]}},
    },
    # Set filter clauses with path, type, and field
    {
        "original": None,
        "params": {"opcua_event_filter_clauses": [["path=/path/to/node", "type=TestType", "field=TestField"]]},
        "expected_values": {
            "eventFilter": {
                "selectClauses": [
                    {
                        "browsePath": "/path/to/node",
                        "typeDefinitionId": "TestType",
                        "fieldId": "TestField"
                    }
                ]
            }
        },
    },
    # Set filter clauses without path (should be skipped)
    {
        "original": None,
        "params": {"opcua_event_filter_clauses": [["type=TestType", "field=TestField"]]},
        "expected_values": {},
    },
    # Set both filter type and clauses
    {
        "original": None,
        "params": {
            "opcua_event_filter_type": "test-type",
            "opcua_event_filter_clauses": [["path=/path/to/node"]]
        },
        "expected_values": {
            "eventFilter": {
                "typeDefinitionId": "test-type",
                "selectClauses": [{"browsePath": "/path/to/node"}]
            }
        },
    },
    # Update existing configuration
    {
        "original": json.dumps({"publishingInterval": 1000}),
        "params": {"opcua_event_queue_size": 50},
        "expected_values": {"publishingInterval": 1000, "queueSize": 50}
    },
    # Update existing configuration with filter clauses
    {
        "original": json.dumps({"publishingInterval": 1000, "startInstance": "test-instance"}),
        "params": {
            "opcua_event_queue_size": 50,
            "opcua_event_start_instance": "new-instance",
            "opcua_event_filter_clauses": [["path=/new/path", "type=NewType", "field=NewField"]]
        },
        "expected_values": {
            "publishingInterval": 1000,
            "queueSize": 50,
            "startInstance": "new-instance",
            "eventFilter": {
                "selectClauses": [
                    {
                        "browsePath": "/new/path",
                        "typeDefinitionId": "NewType",
                        "fieldId": "NewField"
                    }
                ]
            }
        }
    },
    # Set all parameters
    {
        "original": None,
        "params": {
            "opcua_event_publishing_interval": 1000,
            "opcua_event_queue_size": 50,
            "opcua_event_start_instance": "test-instance",
            "opcua_event_filter_type": "test-type",
            "opcua_event_filter_clauses": [["path=/path/to/node", "type=TestType", "field=TestField"]]
        },
        "expected_values": {
            "publishingInterval": 1000,
            "queueSize": 50,
            "startInstance": "test-instance",
            "eventFilter": {
                "typeDefinitionId": "test-type",
                "selectClauses": [
                    {
                        "browsePath": "/path/to/node",
                        "typeDefinitionId": "TestType",
                        "fieldId": "TestField"
                    }
                ]
            }
        },
    }
])
def test_process_opcua_event_configurations(test_case, mocked_logger):
    result_json = _process_opcua_event_configurations(
        original_event_configuration=test_case.get("original"),
        **test_case.get("params", {})
    )

    # Verify the result
    result = json.loads(result_json)

    # Check eventFilter
    event_filter = test_case["expected_values"].get("eventFilter", {})
    if event_filter:
        assert "eventFilter" in result
        assert result["eventFilter"].get("typeDefinitionId") == event_filter.get("typeDefinitionId")
        assert result["eventFilter"].get("selectClauses") == event_filter.get("selectClauses")

    # Check that all expected values are correct
    for key, value in test_case["expected_values"].items():
        if isinstance(value, dict):
            for sub_key, sub_value in value.items():
                assert result[key][sub_key] == sub_value
        else:
            assert result[key] == value

    # Check for warning logs when path is missing
    len_param_filters = len(test_case["params"].get("event_filter_clauses", []))
    len_expected_select_clauses = len(test_case["expected_values"].get("eventFilter", {}).get("selectClauses", []))
    if len_param_filters > len_expected_select_clauses:
        mocked_logger.warning.assert_called()


@pytest.mark.parametrize("test_case", [
    # Empty configuration
    {
        "original": None,
        "params": {"task_type": "snapshot-to-mqtt"},
        "expected_values": {"taskType": "snapshot-to-mqtt"}
    },
    # Set parameters for snapshot-to-mqtt
    {
        "original": None,
        "params": {
            "task_type": "snapshot-to-mqtt",
            "task_format": "png",
            "snapshots_per_second": 0.01
        },
        "expected_values": {
            "taskType": "snapshot-to-mqtt",
            "format": "png",
            "snapshotsPerSecond": 0.01
        }
    },
    # Set parameters for snapshot-to-fs
    {
        "original": None,
        "params": {
            "task_type": "snapshot-to-fs",
            "task_format": "jpeg",
            "snapshots_per_second": 2,
            "path": "/data/snapshots"
        },
        "expected_values": {
            "taskType": "snapshot-to-fs",
            "format": "jpeg",
            "snapshotsPerSecond": 2,
            "path": "/data/snapshots"
        }
    },
    # Set parameters for clip-to-fs
    {
        "original": None,
        "params": {
            "task_type": "clip-to-fs",
            "task_format": "mp4",
            "duration": 60,
            "path": "/data/clips"
        },
        "expected_values": {
            "taskType": "clip-to-fs",
            "format": "mp4",
            "duration": 60,
            "path": "/data/clips"
        }
    },
    # Set parameters for stream-to-rtsp
    {
        "original": None,
        "params": {
            "task_type": "stream-to-rtsp",
            "media_server_address": "rtsp-server",
            "media_server_port": 554,
            "media_server_path": "/live/stream"
        },
        "expected_values": {
            "taskType": "stream-to-rtsp",
            "mediaServerAddress": "rtsp-server",
            "mediaServerPort": 554,
            "mediaServerPath": "/live/stream"
        }
    },
    # Set parameters for stream-to-rtsps with credentials
    {
        "original": None,
        "params": {
            "task_type": "stream-to-rtsps",
            "media_server_address": "rtsps-server",
            "media_server_port": 443,
            "media_server_path": "/secure/stream",
            "media_server_username": "username",
            "media_server_password": "password",
            "media_server_certificate": "certificate"
        },
        "expected_values": {
            "taskType": "stream-to-rtsps",
            "mediaServerAddress": "rtsps-server",
            "mediaServerPort": 443,
            "mediaServerPath": "/secure/stream",
            "mediaServerUsernameRef": "username",
            "mediaServerPasswordRef": "password",
            "mediaServerCertificateRef": "certificate"
        }
    },
    # Update existing configuration
    {
        "original": json.dumps({
            "taskType": "snapshot-to-mqtt",
            "format": "png",
            "snapshotsPerSecond": 1
        }),
        "params": {
            "task_type": "snapshot-to-mqtt",
            "snapshots_per_second": 2
        },
        "expected_values": {
            "taskType": "snapshot-to-mqtt",
            "format": "png",
            "snapshotsPerSecond": 2
        }
    },
    # Change task type for existing configuration
    {
        "original": json.dumps({
            "taskType": "snapshot-to-mqtt",
            "format": "png",
            "snapshotsPerSecond": 1
        }),
        "params": {
            "task_type": "snapshot-to-fs",
            "path": "/data/snapshots"
        },
        "expected_values": {
            "taskType": "snapshot-to-fs",
            "path": "/data/snapshots"
        }
    }
])
def test_process_media_stream_configurations(test_case):
    """Test processing media stream configurations with various parameters."""
    # Execute the function with the provided parameters
    result_json = _process_media_stream_configurations(
        original_stream_configuration=test_case["original"],
        **test_case["params"]
    )

    # Verify the result is valid JSON
    result = json.loads(result_json)

    # Check that all expected values are correct
    assert len(result) == len(test_case["expected_values"])
    for key, value in test_case["expected_values"].items():
        assert result[key] == value

    # Verify task_type is always present
    assert "taskType" in result

    # Verify all properties in the result are allowed for the task type
    from azext_edge.edge.providers.rpsaas.adr.specs import MediaTaskType
    task_type = result["taskType"]
    allowed_properties = MediaTaskType(task_type).allowed_properties

    # Check that all properties in the result are allowed for this task type
    for property_name in result:
        assert property_name in allowed_properties, f"Property {property_name} is not allowed for task type {task_type}"


@pytest.mark.parametrize("test_case", [
    # Missing task type with other parameters provided
    {
        "params": {"snapshots_per_second": 1, "task_format": "png"},
        "expected_error": RequiredArgumentMissingError,
        "expected_msg": "Task type via --task-type must be provided when configuring media stream properties."
    },
    # Invalid property for task type
    {
        "params": {"task_type": "snapshot-to-mqtt", "path": "/data/snapshots"},
        "expected_error": InvalidArgumentValueError,
        "expected_msg": "Property 'path' is not allowed for task type 'snapshot-to-mqtt'."
    },
    # Invalid format for clip tasks
    {
        "params": {"task_type": "clip-to-fs", "task_format": "png", "path": "/data/clips"},
        "expected_error": InvalidArgumentValueError,
        "expected_msg": "Invalid format for clip task:"
    },
    # Invalid format for snapshot tasks
    {
        "params": {"task_type": "snapshot-to-mqtt", "task_format": "mp4"},
        "expected_error": InvalidArgumentValueError,
        "expected_msg": "Invalid format for snapshot task:"
    },
    # Invalid numbers
    {
        "params": {
            "task_type": "snapshot-to-mqtt",
            "task_format": "png",
            "snapshots_per_second": -1
        },
        "expected_error": InvalidArgumentValueError,
        "expected_msg": "Invalid input data:"
    },
])
def test_process_media_stream_configurations_error(test_case):
    """Test error conditions when processing media stream configurations."""
    with pytest.raises(test_case["expected_error"]) as excinfo:
        _process_media_stream_configurations(
            original_stream_configuration=None,
            **test_case["params"]
        )

    assert test_case["expected_msg"] in str(excinfo.value)


@pytest.mark.parametrize("num_events", [1, 5, 10])
def test_get_event(num_events: int):
    from .test_namespace_asset_events_unit import generate_event
    test_event = generate_random_string()
    asset = {
        "name": "testAsset",
        "properties": {
            "events": []
        }
    }

    for i in range(num_events):
        asset["properties"]["events"].append(generate_event(f"testEvent{i}"))

    # Set up events in asset properties
    asset["properties"]["events"].append(generate_event(test_event))

    # Test success case
    result = _get_event(asset, test_event)
    assert result["name"] == test_event
    # lazy way cause the event is last
    assert result == asset["properties"]["events"][-1]


@pytest.mark.parametrize("test_case", [
    {
        "event_name": generate_random_string(),
        "events": [
            {
                "name": f"another{generate_random_string()}",
                "eventNotifier": "nsu=test;s=FastUInt456",
            }
        ],
    },
    {
        "event_name": generate_random_string(),
        "events": [],
    },
    {
        "event_name": generate_random_string(),
        "events": None,
    }
])
def test_get_event_error(test_case):
    """Test error handling when an event is not found in an asset."""
    asset = {
        "name": "testAsset",
        "properties": {}
    }

    # Set up events in asset properties if provided
    if test_case["events"] is not None:
        asset["properties"]["events"] = test_case["events"]

    # Test error cases
    with pytest.raises(InvalidArgumentValueError) as ex:
        _get_event(asset, test_case["event_name"])
    error_msg = f"Event '{test_case['event_name']}' not found in asset '{asset['name']}'."
    assert error_msg in str(ex.value)
