# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from ...common import DeployableAioVersions, ListableEnum


class EdgeServiceMoniker(ListableEnum):
    adr = "adr"
    akri = "akri"
    bluefin = "bluefin"
    e4k = "e4k"
    e4in = "e4in"
    obs = "obs"
    opcua = "opcua"
    symphony = "symphony"


class EdgeExtensionName(ListableEnum):
    iotoperations = "iotoperations"
    mq = "mq"
    processor = "processor"
    assets = "assets"


class AioVersionDef:
    def __init__(self, version: str, ext_to_rp_map: dict, ext_to_vers_map: dict, moniker_to_vers_map: dict):
        self._version = version
        self._ext_to_rp_map = ext_to_rp_map
        self._ext_to_vers_map = ext_to_vers_map
        self._moniker_to_vers_map = moniker_to_vers_map

    @property
    def version(self):
        return self._version

    @property
    def extension_to_rp_map(self):
        return self._ext_to_rp_map

    @property
    def extension_to_vers_map(self):
        return self._ext_to_vers_map

    @property
    def moniker_to_version_map(self):
        return self._moniker_to_vers_map

    def set_moniker_to_version_map(self, moniker_map: dict, refresh_mappings: bool = False):
        self._version = "custom"
        if not refresh_mappings:
            self._moniker_to_vers_map.update(moniker_map)
            return

        self._moniker_to_vers_map = moniker_map
        ext_to_vers_map = {}
        ext_to_rp_map = {}
        for key in self._moniker_to_vers_map:
            moniker_to_extension_key = moniker_to_extension_type_map.get(key)
            if moniker_to_extension_key:
                ext_to_vers_map[moniker_to_extension_type_map[key]] = self._moniker_to_vers_map[key]
                ext_to_rp_map[moniker_to_extension_type_map[key]] = self._ext_to_rp_map[
                    moniker_to_extension_type_map[key]
                ]
        self._ext_to_vers_map = ext_to_vers_map
        self._ext_to_rp_map = ext_to_rp_map


def get_aio_version_def(version: str) -> AioVersionDef:
    if version == DeployableAioVersions.v011.value:
        return AioVersionDef(
            version=version,
            ext_to_rp_map=v011_extension_to_rp_map,
            ext_to_vers_map=v011_extension_to_version_map,
            moniker_to_vers_map=v011_moniker_to_version_map,
        )


v011_moniker_to_version_map = {
    EdgeServiceMoniker.adr.value: "0.9.0",
    EdgeServiceMoniker.akri.value: "0.1.0",
    EdgeServiceMoniker.bluefin.value: "0.2.4",
    EdgeServiceMoniker.e4k.value: "0.5.1",
    EdgeServiceMoniker.e4in.value: "0.1.1",
    EdgeServiceMoniker.obs.value: "0.62.3",
    EdgeServiceMoniker.opcua.value: "0.7.0",
    EdgeServiceMoniker.symphony.value: "0.44.9",
}

v011_extension_to_rp_map = {
    "microsoft.alicesprings": "microsoft.symphony",
    "microsoft.alicesprings.dataplane": "microsoft.alicespringsdataplane",
    "microsoft.alicesprings.processor": "microsoft.bluefin",
    "microsoft.deviceregistry.assets": "microsoft.deviceregistry",
}

v011_extension_to_version_map = {
    "microsoft.alicesprings": v011_moniker_to_version_map[EdgeServiceMoniker.symphony.value],
    "microsoft.alicesprings.dataplane": v011_moniker_to_version_map[EdgeServiceMoniker.e4k.value],
    "microsoft.alicesprings.processor": v011_moniker_to_version_map[EdgeServiceMoniker.bluefin.value],
    "microsoft.deviceregistry.assets": v011_moniker_to_version_map[EdgeServiceMoniker.adr.value],
}

moniker_to_extension_type_map = {
    EdgeServiceMoniker.symphony.value: "microsoft.alicesprings",
    EdgeServiceMoniker.e4k.value: "microsoft.alicesprings.dataplane",
    EdgeServiceMoniker.bluefin.value: "microsoft.alicesprings.processor",
    EdgeServiceMoniker.adr.value: "microsoft.deviceregistry.assets",
}

extension_name_to_type_map = {
    EdgeExtensionName.iotoperations.value: "microsoft.alicesprings",
    EdgeExtensionName.mq.value: "microsoft.alicesprings.dataplane",
    EdgeExtensionName.processor.value: "microsoft.alicesprings.processor",
    EdgeExtensionName.assets.value: "microsoft.deviceregistry.assets",
}
