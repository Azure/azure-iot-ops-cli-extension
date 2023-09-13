# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import json
import pytest

from azext_edge.common.utility import assemble_nargs_to_dict

from ....edge.commands_assets import process_data_points, process_events

from ...generators import generate_generic_id


# TODO: add error testing

@pytest.mark.parametrize("data_points", [
    None,
    [[f"data_source={generate_generic_id()}"]],
    [
        [f"data_source={generate_generic_id()}"],
        [f"data_source={generate_generic_id()}"]
    ],
    [
        [
            f"data_source={generate_generic_id()}",
            "sampling_interval=10",
            "queue_size=1000",
            f"capability_id={generate_generic_id()}",
            f"name={generate_generic_id()}",
            f"observability_mode={generate_generic_id()}",
        ]
    ],
    [
        [
            f"data_source={generate_generic_id()}",
            f"name={generate_generic_id()}",
            f"observability_mode={generate_generic_id()}",
        ]
    ],
    [
        [
            f"data_source={generate_generic_id()}",
            "sampling_interval=10",
            f"capability_id={generate_generic_id()}",
            f"name={generate_generic_id()}",
            f"observability_mode={generate_generic_id()}",
        ],
        [
            f"data_source={generate_generic_id()}",
            "sampling_interval=10",
            "queue_size=1000",
            f"capability_id={generate_generic_id()}",
            f"name={generate_generic_id()}",
            f"observability_mode={generate_generic_id()}",
        ],
        [
            f"data_source={generate_generic_id()}",
            "sampling_interval=10",
            "queue_size=1000",
            f"capability_id={generate_generic_id()}",
            f"name={generate_generic_id()}",
            f"observability_mode={generate_generic_id()}",
        ]
    ],
])
def test_process_data_points(data_points):
    expected_result = []
    if data_points:
        for item in data_points:
            parsed_item = assemble_nargs_to_dict(item)

            custom_configuration = {}
            if parsed_item.get("sampling_interval"):
                custom_configuration["samplingInterval"] = int(parsed_item.get("sampling_interval"))
            if parsed_item.get("queue_size"):
                custom_configuration["queueSize"] = int(parsed_item.get("queue_size"))

            if not parsed_item.get("capability_id"):
                parsed_item["capability_id"] = parsed_item.get("name")

            final_item = {
                "capabilityId": parsed_item.get("capability_id"),
                "dataPointConfiguration": json.dumps(custom_configuration),
                "dataSource": parsed_item.get("data_source"),
                "name": parsed_item.get("name"),
                "observabilityMode": parsed_item.get("observability_mode")
            }
            expected_result.append(final_item)

    result = process_data_points(data_points)

    assert result == expected_result


@pytest.mark.parametrize("events", [
    None,
    [[f"event_notifier={generate_generic_id()}"]],
    [
        [f"event_notifier={generate_generic_id()}"],
        [f"event_notifier={generate_generic_id()}"]
    ],
    [
        [
            f"event_notifier={generate_generic_id()}",
            "sampling_interval=10",
            "queue_size=1000",
            f"capability_id={generate_generic_id()}",
            f"name={generate_generic_id()}",
            f"observability_mode={generate_generic_id()}",
        ]
    ],
    [
        [
            f"event_notifier={generate_generic_id()}",
            f"name={generate_generic_id()}",
            f"observability_mode={generate_generic_id()}",
        ]
    ],
    [
        [
            f"event_notifier={generate_generic_id()}",
            "sampling_interval=10",
            f"capability_id={generate_generic_id()}",
            f"name={generate_generic_id()}",
            f"observability_mode={generate_generic_id()}",
        ],
        [
            f"event_notifier={generate_generic_id()}",
            "sampling_interval=10",
            "queue_size=1000",
            f"capability_id={generate_generic_id()}",
            f"name={generate_generic_id()}",
            f"observability_mode={generate_generic_id()}",
        ],
        [
            f"event_notifier={generate_generic_id()}",
            "sampling_interval=10",
            "queue_size=1000",
            f"capability_id={generate_generic_id()}",
            f"name={generate_generic_id()}",
            f"observability_mode={generate_generic_id()}",
        ]
    ],
])
def test_process_events(events):
    expected_result = []
    if events:
        for item in events:
            parsed_item = assemble_nargs_to_dict(item)

            custom_configuration = {}
            if parsed_item.get("sampling_interval"):
                custom_configuration["samplingInterval"] = int(parsed_item.get("sampling_interval"))
            if parsed_item.get("queue_size"):
                custom_configuration["queueSize"] = int(parsed_item.get("queue_size"))

            if not parsed_item.get("capability_id"):
                parsed_item["capability_id"] = parsed_item.get("name")

            final_item = {
                "capabilityId": parsed_item.get("capability_id"),
                "eventConfiguration": json.dumps(custom_configuration),
                "eventNotifier": parsed_item.get("event_notifier"),
                "name": parsed_item.get("name"),
                "observabilityMode": parsed_item.get("observability_mode")
            }
            expected_result.append(final_item)

    result = process_events(events)

    assert result == expected_result

