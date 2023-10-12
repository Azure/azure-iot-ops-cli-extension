# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from enum import Enum
from typing import Dict, FrozenSet, Iterable, List, Union, Optional
from kubernetes.client.models import V1APIResourceList
from ...providers.base import get_cluster_custom_api, get_custom_objects

from azure.cli.core.azclierror import ResourceNotFoundError


class EdgeResourceApi:
    def __init__(self, group: str, version: str, moniker: str):
        self.group: str = group
        self.version: str = version
        self.moniker: str = moniker
        self._api: V1APIResourceList = None
        self._kinds: Dict[str, str] = None

    def as_str(self) -> str:
        return f"{self.group}/{self.version}"

    def is_deployed(self, raise_on_404: bool = False) -> bool:
        return self._get_api(raise_on_404) is not None

    def _get_api(self, raise_on_404: bool = False):
        self._api = get_cluster_custom_api(group=self.group, version=self.version, raise_on_404=raise_on_404)
        return self._api

    @property
    def kinds(self) -> Union[FrozenSet[str], None]:
        if self._kinds:
            return frozenset(self._kinds.keys())

        if not self._api:
            self._get_api()

        if self._api:
            self._kinds = {}
            for resource in self._api.resources:
                rn: str = resource.name
                if "/" in rn:
                    rn = rn[: rn.index("/")]
                self._kinds[resource.kind.lower()] = rn
            return frozenset(self._kinds.keys())

    def get_resources(self, kind: Union[str, Enum], namespace: Optional[str] = None):
        if isinstance(kind, Enum):
            kind = kind.value

        if self.kinds and kind in self.kinds:
            return get_custom_objects(
                group=self.group, version=self.version, plural=self._kinds[kind], namespace=namespace
            )


class EdgeApiManager:
    def __init__(self, resource_apis: Iterable[EdgeResourceApi]):
        self.resource_apis: FrozenSet[EdgeResourceApi] = frozenset(resource_apis)
        self.api_group_map: Dict[str, List[str]] = {}
        for api in self.resource_apis:
            if api.group not in self.api_group_map:
                self.api_group_map[api.group] = []
            self.api_group_map[api.group].append(api.version)

    def as_str(self):
        apis_str = ""
        sep = "\n" if len(self.api_group_map) > 1 else ""
        for group in self.api_group_map:
            apis_str += f"{group}/[{','.join(self.api_group_map[group])}]{sep}"
        return apis_str

    def get_deployed(self, raise_on_404: bool = False) -> Iterable[EdgeResourceApi]:
        result = []
        for api in self.resource_apis:
            if api.is_deployed():
                result.append(api)
        if not result and raise_on_404:
            error_msg = f"The following APIs are not detected on the cluster:\n{self.as_str()}"
            raise ResourceNotFoundError(error_msg)

        return result

    @property
    def apis(self) -> FrozenSet[EdgeResourceApi]:
        return self.resource_apis
