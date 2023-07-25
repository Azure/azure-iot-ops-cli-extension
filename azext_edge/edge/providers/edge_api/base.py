# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from enum import Enum
from typing import Dict, FrozenSet, Iterable, List, NamedTuple, Union

from azure.cli.core.azclierror import ResourceNotFoundError


class EdgeResourceApi(NamedTuple):
    group: str
    version: str
    moniker: str
    kinds: FrozenSet[str]

    def as_str(self) -> str:
        return f"{self.group}/{self.version}"

    def get_resource(self, kind: Union[str, Enum]) -> Union["EdgeResource", None]:
        if isinstance(kind, Enum):
            kind = kind.value
        if kind in self.kinds:
            return EdgeResource(api=self, kind=kind)

    def is_deployed(self, raise_on_404: bool = False) -> bool:
        from ...providers.base import get_cluster_custom_api

        return get_cluster_custom_api(resource_api=self, raise_on_404=raise_on_404) is not None


class EdgeResource(NamedTuple):
    api: EdgeResourceApi
    kind: str

    @property
    def plural(self) -> str:
        return f"{self.kind}s"


class EdgeApiManager:
    def __init__(self, ResourceApis: Iterable[EdgeResourceApi]):
        self.resource_apis: FrozenSet[EdgeResourceApi] = frozenset(ResourceApis)
        self.api_group_map: Dict[str, List[str]] = {}
        for api in self.resource_apis:
            if api.group not in self.api_group_map:
                self.api_group_map[api.group] = []
            self.api_group_map[api.group].append(api.version)

    def as_str(self):
        apis_str = ""
        sep = "\n" if len(self.api_group_map) > 1 else ""
        for group in self.api_group_map:
            apis_str += f" {group}/[{','.join(self.api_group_map[group])}]{sep}"
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
