# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from enum import Enum


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
