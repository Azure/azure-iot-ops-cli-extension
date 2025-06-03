# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from enum import Enum
from ....common import ListableEnum


# DEVICE
NAMESPACE_DEVICE_OPCUA_ENDPOINT_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "$id": "https://azure-iot-operations/schemas/assetendpointprofile/additionalconfiguration/opcua/1.1.0.json",
    "title": "AIO OPC UA Asset Endpoint Profile Additional Configuration Schema",
    "description": "Schema for the additional configuration of OPC UA asset endpoint profile "
    "in Azure Industrial Operations",
    "type": "object",
    "properties": {
        "applicationName": {
            "type": "string",
            "default": "OPC UA Broker"
        },
        "keepAliveMilliseconds": {
            "type": "integer",
            "minimum": 0,
            "default": 10000
        },
        "defaults": {
            "type": "object",
            "properties": {
                "publishingIntervalMilliseconds": {
                    "type": "integer",
                    "minimum": -1,
                    "default": 1000
                },
                "samplingIntervalMilliseconds": {
                    "type": "integer",
                    "minimum": -1,
                    "default": 1000
                },
                "queueSize": {
                    "type": "integer",
                    "minimum": 0,
                    "default": 1
                },
                "keyFrameCount": {
                    "type": "integer",
                    "minimum": 0,
                    "default": 0
                }
            }
        },
        "session": {
            "type": "object",
            "properties": {
                "timeoutMilliseconds": {
                    "type": "integer",
                    "minimum": 0,
                    "default": 60000
                },
                "keepAliveIntervalMilliseconds": {
                    "type": "integer",
                    "minimum": 0,
                    "default": 10000
                },
                "reconnectPeriodMilliseconds": {
                    "type": "integer",
                    "minimum": 0,
                    "default": 2000
                },
                "reconnectExponentialBackOffMilliseconds": {
                    "type": "integer",
                    "minimum": -1,
                    "default": 10000
                },
                "enableTracingHeaders": {
                    "type": "boolean",
                    "default": False
                }
            }
        },
        "subscription": {
            "type": "object",
            "properties": {
                "maxItems": {
                    "type": "integer",
                    "minimum": 1,
                    "default": 1000
                },
                "lifeTimeMilliseconds": {
                    "type": "integer",
                    "minimum": 0,
                    "default": 60000
                }
            }
        },
        "security": {
            "type": "object",
            "properties": {
                "autoAcceptUntrustedServerCertificates": {
                    "type": "boolean",
                    "default": False
                },
                "securityPolicy": {
                    "type": ["string", "null"],
                    "enum": [
                        "http://opcfoundation.org/UA/SecurityPolicy#None",
                        "http://opcfoundation.org/UA/SecurityPolicy#Basic128Rsa15",
                        "http://opcfoundation.org/UA/SecurityPolicy#Basic256",
                        "http://opcfoundation.org/UA/SecurityPolicy#Basic256Sha256",
                        "http://opcfoundation.org/UA/SecurityPolicy#Aes128_Sha256_RsaOaep",
                        "http://opcfoundation.org/UA/SecurityPolicy#Aes256_Sha256_RsaPss",
                        None
                    ],
                    "default": None
                },
                "securityMode": {
                    "type": ["string", "null"],
                    "enum": [
                        "none",
                        "sign",
                        "signAndEncrypt",
                        None
                    ],
                    "default": None
                }
            }
        },
        "runAssetDiscovery": {
            "type": "boolean",
            "default": False
        }
    }
}


NAMESPACE_DEVICE_ONVIF_ENDPOINT_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "$id": "https://azure-iot-operations/schemas/assetendpointprofile/additionalconfiguration/onvif/1.2.0.json",
    "title": "AIO ONVIF Asset Endpoint Profile Additional Configuration Schema",
    "description": "Schema for the additional configuration of ONVIF asset endpoint profile in Azure Industrial "
    "Operations",
    "type": "object",
    "properties": {
        "acceptInvalidHostnames": {
            "type": "boolean",
            "default": False
        },
        "acceptInvalidCertificates": {
            "type": "boolean",
            "default": False
        }
    }
}


class SecurityPolicy(Enum):
    """
    Security policies for the OPC UA connector as defined in NAMESPACE_DEVICE_OPCUA_ENDPOINT_SCHEMA.
    Values correspond to the part after the "#" in the security policy URLs.
    """
    # TODO: (nice to have) more user friendly names
    none = "None"
    basic128 = "Basic128Rsa15"
    basic256 = "Basic256"
    basic256sha256 = "Basic256Sha256"
    aes128 = "Aes128_Sha256_RsaOaep"
    aes256 = "Aes256_Sha256_RsaPss"

    @property
    def full_value(self):
        """
        Returns the full value of the security policy, including the URL prefix.
        """
        return f"http://opcfoundation.org/UA/SecurityPolicy#{self.value}"


class SecurityMode(Enum):
    """
    Security modes for the OPC UA connector as defined in NAMESPACE_DEVICE_OPCUA_ENDPOINT_SCHEMA.
    """
    none = "none"
    sign = "sign"
    signandencrypt = "signAndEncrypt"


# ASSETS
NAMESPACE_ASSET_OPCUA_DATASET_CONFIGURATION_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "$id": "https://azure-iot-operations/schemas/asset/defaultdatasetsconfiguration/opcua/1.2.0.json",
    "title": "AIO OPC UA Asset Default Datasets Additional Configuration Schema",
    "description": "Schema for the additional configuration of OPC UA asset default datasets in Azure Industrial "
    "Operations",
    "type": "object",
    "properties": {
        "publishingInterval": {
            "type": "integer",
            "minimum" : -1,
            "default": 1000
        },
        "samplingInterval": {
            "type": "integer",
            "minimum" : -1,
            "default": 1000
        },
        "queueSize": {
            "type": "integer",
            "minimum" : 0,
            "default": 1
        },
        "keyFrameCount": {
            "type": "integer",
            "minimum" : 0,
            "default": 0
        },
        "startInstance": {
            "type": "string",
            "default": None
        }
    }
}


NAMESPACE_ASSET_OPCUA_EVENT_CONFIGURATION_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "$id": "https://azure-iot-operations/schemas/asset/defaulteventsconfiguration/opcua/1.2.0.json",
    "title": "AIO OPC UA Asset Default Events Additional Configuration Schema",
    "description": "Schema for the additional configuration of OPC UA asset default events in Azure Industrial "
    "Operations",
    "type": "object",
    "properties": {
        "publishingInterval": {
            "type": "integer",
            "minimum" : -1,
            "default": 1000
        },
        "queueSize": {
            "type": "integer",
            "minimum" : 0,
            "default": 1
        },
        "startInstance": {
            "type": "string",
            "default": None
        },
        "eventFilter": {
            "type": "object",
            "properties": {
                "typeDefinitionId": {
                    "type": "string"
                },
                "selectClauses": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "browsePath": {
                                "type": "string"
                            },
                            "typeDefinitionId": {
                                "type": "string"
                            },
                            "fieldId": {
                                "type": "string"
                            }
                        },
                        "required": ["browsePath"]
                    }
                }
            }
        }
    }
}


NAMESPACE_ASSET_MEDIA_STREAM_CONFIGURATION_SCHEMA = {
    "$id": "https://azure.com/aio/media-connector/datapoint.schema.json",
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "description": "Asset.dataPoint.dataPointConfiguration schema",
    "type": "object",
    "properties": {
        "taskType": {
            "type": "string"
        }
    },
    "required": ["taskType"],
    "oneOf": [
        {
            "properties": {
                "taskType": {
                    "const": "snapshot-to-mqtt"
                },
                "format": {
                    "type": "string",
                    "enum": ["png", "bmp", "jpg", "jpeg", "tif", "tiff"],
                    "description": "The image format for the snapshot. The default is jpeg.",
                    "default": "jpeg"
                },
                "snapshotsPerSecond": {
                    "type": "number",
                    "minimum": 0,
                    "description": "The number of snapshots per second to capture. Default is 1. If empty or 0, the "
                    "source frame rate will be used. Example: 30 for a 30 snapshots per second; 1/60 for one snapshot "
                    "per minutes.",
                    "default": 1
                }
            }
        },
        {
            "properties": {
                "taskType": {
                    "const": "snapshot-to-fs"
                },
                "format": {
                    "type": "string",
                    "enum": ["png", "bmp", "jpg", "jpeg", "tif", "tiff"],
                    "description": "The image format for the snapshot. Default is png.",
                    "default": "png"
                },
                "snapshotsPerSecond": {
                    "type": "number",
                    "minimum": 0,
                    "description": "The number of snapshots per second to capture. Default is 1. If empty or 0, the "
                    "source frame rate will be used. Example: 30 for a 30 snapshots per second; 1/60 for one snapshot "
                    "per minutes.",
                    "default": 1
                },
                "path": {
                    "type": "string",
                    "description": "The path where snapshot will be written, by default set by the broker as "
                    "/tmp/<namespace>/data/<asset>.",
                    "default": ""
                }
            }
        },
        {
            "properties": {
                "taskType": {
                    "const": "clip-to-fs"
                },
                "format": {
                    "type": "string",
                    "enum": ["avi", "mp4", "mkv", "mts", "mjpeg", "mpg", "mpeg", "flv", "webm"],
                    "description": "The video clip format. The default is mkv.",
                    "default": "mkv"
                },
                "duration": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "The duration of each clip segment, in seconds. The default is 60 seconds.",
                    "default": 60
                },
                "path": {
                    "type": "string",
                    "description": "The path where clips will be written, by default set by the connector as "
                    "/tmp/<namespace>/data/<asset>.",
                    "default": ""
                }
            }
        },
        {
            "properties": {
                "taskType": {
                    "const": "stream-to-rtsp"
                },
                "mediaServerAddress": {
                    "type": "string",
                    "description": "The media server address or IP. The default is "
                    "media-server.media-server.svc.cluster.local",
                    "default": "media-server.media-server.svc.cluster.local"
                },
                "mediaServerPort": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "The media server port. The default is 8554.",
                    "default": 8554
                },
                "mediaServerPath": {
                    "type": "string",
                    "description": "The media server path. by default set by the by default set by the connector as "
                    "<namespace>/data/<asset>.",
                    "default": ""
                },
                "mediaServerUsernameRef": {
                    "type": "string",
                    "description": "The media server username reference. The default is empty.",
                    "default": ""
                },
                "mediaServerPasswordRef": {
                    "type": "string",
                    "description": "The media server password reference. The default is empty.",
                    "default": ""
                }
            }
        },
        {
            "properties": {
                "taskType": {
                    "const": "stream-to-rtsps"
                },
                "mediaServerAddress": {
                    "type": "string",
                    "description": "The media server address or IP. The default is "
                    "media-server.media-server.svc.cluster.local",
                    "default": "media-server.media-server.svc.cluster.local"
                },
                "mediaServerPort": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "The media server port. The default is 8554.",
                    "default": 8554
                },
                "mediaServerPath": {
                    "type": "string",
                    "description": "The media server path. by default set by the by default set by the connector as "
                    "<namespace>/data/<asset>.",
                    "default": ""
                },
                "mediaServerUsernameRef": {
                    "type": "string",
                    "description": "The media server username reference. The default is empty.",
                    "default": ""
                },
                "mediaServerPasswordRef": {
                    "type": "string",
                    "description": "The media server password reference. The default is empty.",
                    "default": ""
                },
                "mediaServerCertificateRef": {
                    "type": "string",
                    "description": "The media server certificate reference. The default is empty.",
                    "default": ""
                }
            }
        }
    ]
}


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
            MediaTaskType.snapshot_to_mqtt.value: ["taskType", "format", "snapshotsPerSecond"],
            MediaTaskType.snapshot_to_fs.value: ["taskType", "format", "snapshotsPerSecond", "path"],
            MediaTaskType.clip_to_fs.value: ["taskType", "format", "duration", "path"],
            MediaTaskType.stream_to_rtsp.value: [
                "taskType", "mediaServerAddress", "mediaServerPort", "mediaServerPath",
                "mediaServerUsernameRef", "mediaServerPasswordRef"
            ],
            MediaTaskType.stream_to_rtsps.value: [
                "taskType", "mediaServerAddress", "mediaServerPort", "mediaServerPath",
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
