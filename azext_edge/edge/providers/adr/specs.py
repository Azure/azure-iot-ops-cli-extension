# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from enum import Enum
import json
import os
from ...common import ListableEnum


def _load_schema(filename):
    schema_path = os.path.join(os.path.dirname(__file__), "schemas", filename)
    with open(schema_path, "r", encoding="utf-8") as f:
        return json.load(f)


# Device Schemas
NAMESPACE_DEVICE_OPCUA_ENDPOINT_SCHEMA = _load_schema("opcua_endpoint.json")
NAMESPACE_DEVICE_ONVIF_ENDPOINT_SCHEMA = _load_schema("onvif_endpoint.json")


class SecurityPolicy(Enum):
    """
    Security policies for the OPC UA connector as defined in NAMESPACE_DEVICE_OPCUA_ENDPOINT_SCHEMA.
    Values correspond to the part after the "#" in the security policy URLs.
    """
    none = "None"
    basic128 = "Basic128Rsa15"
    basic256 = "Basic256"
    basic256sha256 = "Basic256Sha256"
    aes128 = "Aes128_Sha256_RsaOaep"
    aes256 = "Aes256_Sha256_RsaPss"

    @property
    def full_value(self):
        """Returns the full security policy URL."""
        return f"http://opcfoundation.org/UA/SecurityPolicy#{self.value}"


class SecurityMode(Enum):
    """Security modes for the OPC UA connector."""
    none = "none"
    sign = "sign"
    signandencrypt = "signAndEncrypt"


# Asset Schemas - OPC UA
NAMESPACE_ASSET_OPCUA_DATASET_CONFIGURATION_SCHEMA_V1 = _load_schema("opcua_dataset_config_v1.json")
NAMESPACE_ASSET_OPCUA_DATASET_CONFIGURATION_SCHEMA_V2 = _load_schema("opcua_dataset_config_v2.json")
NAMESPACE_ASSET_OPCUA_EVENT_CONFIGURATION_SCHEMA_V1 = _load_schema("opcua_event_config_v1.json")
NAMESPACE_ASSET_OPCUA_EVENT_CONFIGURATION_SCHEMA_V2 = _load_schema("opcua_event_config_v2.json")
NAMESPACE_ASSET_OPCUA_DATAPOINT_CONFIGURATION_SCHEMA = _load_schema("opcua_datapoint_config.json")

# Asset Schemas - Media
NAMESPACE_ASSET_MEDIA_STREAM_CONFIGURATION_SCHEMA = _load_schema("media_stream_config.json")

# Asset Schemas - REST
NAMESPACE_ASSET_REST_DATASET_CONFIGURATION_SCHEMA = _load_schema("rest_dataset_config.json")


class MediaTaskType(Enum):
    """
    Enum for media task types in NAMESPACE_ASSET_MEDIA_STREAM_CONFIGURATION_SCHEMA.
    """
    snapshot_to_mqtt = "snapshot-to-mqtt"
    snapshot_to_fs = "snapshot-to-fs"
    clip_to_fs = "clip-to-fs"
    stream_to_rtsp = "stream-to-rtsp"
    stream_to_rtsps = "stream-to-rtsps"

    @property
    def allowed_properties(self):
        mapping = {
            MediaTaskType.snapshot_to_mqtt.value: ["taskType", "autostart", "format", "snapshotsPerSecond"],
            MediaTaskType.snapshot_to_fs.value: ["taskType", "autostart", "format", "snapshotsPerSecond", "path"],
            MediaTaskType.clip_to_fs.value: ["taskType", "autostart", "format", "duration", "path"],
            MediaTaskType.stream_to_rtsp.value: [
                "taskType", "autostart", "mediaServerAddress", "mediaServerPort", "mediaServerPath",
                "mediaServerUsernameRef", "mediaServerPasswordRef"
            ],
            MediaTaskType.stream_to_rtsps.value: [
                "taskType", "autostart", "mediaServerAddress", "mediaServerPort", "mediaServerPath",
                "mediaServerUsernameRef", "mediaServerPasswordRef", "mediaServerCertificateRef"
            ],
        }
        return mapping[self.value]


class MediaFormat(ListableEnum):
    """
    Enum for all media formats specified in NAMESPACE_ASSET_MEDIA_STREAM_CONFIGURATION_SCHEMA.
    """
    png = "png"
    bmp = "bmp"
    jpg = "jpg"
    jpeg = "jpeg"
    tif = "tif"
    tiff = "tiff"
    avi = "avi"
    mp4 = "mp4"
    mkv = "mkv"
    mts = "mts"
    mjpeg = "mjpeg"
    mpg = "mpg"
    mpeg = "mpeg"
    flv = "flv"
    webm = "webm"

    @property
    def allowed_for_snapshot(self):
        """
        Returns True if the format is allowed for snapshot tasks.
        """
        return self in {
            MediaFormat.png, MediaFormat.bmp, MediaFormat.jpg, MediaFormat.jpeg, MediaFormat.tif, MediaFormat.tiff
        }

    @property
    def allowed_for_clip(self):
        """
        Returns True if the format is allowed for clip tasks.
        """
        return self in {
            MediaFormat.avi, MediaFormat.mp4, MediaFormat.mkv, MediaFormat.mts, MediaFormat.mjpeg,
            MediaFormat.mpg, MediaFormat.mpeg, MediaFormat.flv, MediaFormat.webm
        }
