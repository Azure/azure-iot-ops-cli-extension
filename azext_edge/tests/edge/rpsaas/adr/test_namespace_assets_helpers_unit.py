# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import List, Optional
import json
import pytest
from azure.cli.core.azclierror import (
    InvalidArgumentValueError,
    MutuallyExclusiveArgumentError,
    RequiredArgumentMissingError,
)

from azext_edge.edge.providers.rpsaas.adr.namespace_assets import (
    _build_destination,
    _process_opcua_dataset_configurations,
    _process_opcua_event_configurations,
    _process_media_stream_configurations
)
from azext_edge.edge.util.common import parse_kvp_nargs


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
            "snapshots_per_second": 1
        },
        "expected_values": {
            "taskType": "snapshot-to-mqtt",
            "format": "png",
            "snapshotsPerSecond": 1
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
            "media_server_password": "password"
        },
        "expected_values": {
            "taskType": "stream-to-rtsps",
            "mediaServerAddress": "rtsps-server",
            "mediaServerPort": 443,
            "mediaServerPath": "/secure/stream",
            "mediaServerUsernameRef": "username",
            "mediaServerPasswordRef": "password"
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
