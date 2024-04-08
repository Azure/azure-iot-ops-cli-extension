# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Any, Dict, List, Optional

from knack.log import get_logger

from .common import ALL_NAMESPACES_TARGET
from ...common import CheckTaskStatus

logger = get_logger(__name__)


class CheckManager:
    """
    {
        "name":"evaluateBrokerListeners",
        "description": "Evaluate MQ broker listeners",
        "status": "warning",
        "targets": {
            "mq.iotoperations.azure.com/v1beta1": {
                "_all_": {
                    "conditions": null,
                    "evaluations": [
                        {
                            "status": "success"
                            ...
                        }
                    ],
                }
            },
            "brokerlisteners.mq.iotoperations.azure.com": {
                "default": {
                    "displays": [],
                    "conditions": [
                        "len(brokerlisteners)>=1",
                        "spec",
                        "valid(spec.brokerRef)"
                        ...
                    ],
                    "evaluations": [
                        {
                            "name": "listener",
                            "kind": "brokerListener",
                            "value": {
                                "spec": { ... },
                                "valid(spec.brokerRef)": true
                            },
                            "status": "warning"
                        }
                    ],
                    "status": "warning"
                },
                "other-namespace": {
                    "displays": [],
                    "conditions": []
                    ...
                }
            }
        }
    }
    """

    def __init__(self, check_name: str, check_desc: str):
        self.check_name = check_name
        self.check_desc = check_desc
        self.targets = {}
        self.target_displays = {}
        self.worst_status = CheckTaskStatus.success.value

    def add_target(self, target_name: str, namespace: str = ALL_NAMESPACES_TARGET, conditions: List[str] = None, description: str = None) -> None:
        # TODO: maybe make a singular taget into a class for consistent structure?
        if target_name not in self.targets:
            # Create a default `None` namespace target for targets with no namespace
            self.targets[target_name] = {}
        if namespace and namespace not in self.targets[target_name]:
            self.targets[target_name][namespace] = {}
        self.targets[target_name][namespace]["conditions"] = conditions
        self.targets[target_name][namespace]["evaluations"] = []
        self.targets[target_name][namespace]["status"] = CheckTaskStatus.success.value
        if description:
            self.targets[target_name][namespace]["description"] = description

    def set_target_conditions(self, target_name: str, conditions: List[str], namespace: str = ALL_NAMESPACES_TARGET) -> None:
        self.targets[target_name][namespace]["conditions"] = conditions

    def add_target_conditions(self, target_name: str, conditions: List[str], namespace: str = ALL_NAMESPACES_TARGET) -> None:
        if self.targets[target_name][namespace]["conditions"] is None:
            self.targets[target_name][namespace]["conditions"] = []
        self.targets[target_name][namespace]["conditions"].extend(conditions)

    def set_target_status(self, target_name: str, status: str, namespace: str = ALL_NAMESPACES_TARGET) -> None:
        self._process_status(target_name=target_name, namespace=namespace, status=status)

    def add_target_eval(
        self,
        target_name: str,
        status: str,
        value: Optional[Any] = None,
        namespace: str = ALL_NAMESPACES_TARGET,
        resource_name: Optional[str] = None,
        resource_kind: Optional[str] = None,
    ) -> None:
        eval_dict = {"status": status}
        if resource_name:
            eval_dict["name"] = resource_name
        if value:
            eval_dict["value"] = value
        if resource_kind:
            eval_dict["kind"] = resource_kind
        self.targets[target_name][namespace]["evaluations"].append(eval_dict)
        self._process_status(target_name, status, namespace)

    def _process_status(self, target_name: str, status: str, namespace: str = ALL_NAMESPACES_TARGET) -> None:
        existing_status = self.targets[target_name].get("status", CheckTaskStatus.success.value)
        if existing_status != status:
            if existing_status == CheckTaskStatus.success.value and status in [
                CheckTaskStatus.warning.value,
                CheckTaskStatus.error.value,
                CheckTaskStatus.skipped.value,
            ]:
                self.targets[target_name][namespace]["status"] = status
                self.worst_status = status
            elif (
                existing_status == CheckTaskStatus.warning.value or existing_status == CheckTaskStatus.skipped.value
            ) and status in [CheckTaskStatus.error.value]:
                self.targets[target_name][namespace]["status"] = status
                self.worst_status = status

    def add_display(self, target_name: str, display: Any, namespace: str = ALL_NAMESPACES_TARGET) -> None:
        if target_name not in self.target_displays:
            self.target_displays[target_name] = {}
        if namespace not in self.target_displays[target_name]:
            self.target_displays[target_name][namespace] = []
        self.target_displays[target_name][namespace].append(display)

    def as_dict(self, as_list: bool = False) -> Dict[str, Any]:
        from copy import deepcopy

        result = {
            "name": self.check_name,
            "description": self.check_desc,
            "targets": {},
            "status": self.worst_status,
        }
        result["targets"] = deepcopy(self.targets)
        if as_list:
            for type in self.target_displays:
                for namespace in self.target_displays[type]:
                    result["targets"][type][namespace]["displays"] = deepcopy(self.target_displays[type][namespace])

        return result
