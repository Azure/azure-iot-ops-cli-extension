# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

# Description is the cli arguments for better error handing
OPCUA_SCHEMA = {
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://azure-iot-operations/schemas/assetendpointprofile/additionalconfiguration/opcua/1.0.0.json",
  "title": "AIO OPC UA Asset Endpoint Profile Additional Configuration Schema",
  "description": "Schema for the additional configuration of OPC UA asset endpoint profile in Azure Industrial Operations",
  "type": "object",
  "properties": {
    "applicationName": {
      "type": "string",
      "default": "OPC UA Broker",
      "description": "--application/--app"
    },
    "keepAliveMilliseconds": {
      "type": "integer",
      "minimum": 0,
      "default": 10000,
      "description": "--keep-alive/--ka"
    },
    "defaults": {
      "type": "object",
      "properties": {
        "publishingIntervalMilliseconds": {
          "type": "integer",
          "minimum": -1,
          "default": 1000,
          "description": "--default-publishing-int/--dpi"
        },
        "samplingIntervalMilliseconds": {
          "type": "integer",
          "minimum": -1,
          "default": 1000,
          "description": "--default-sampling-int/--dsi"
        },
        "queueSize": {
          "type": "integer",
          "minimum": 0,
          "default": 1,
          "description": "--default-queue-size/--dqs"
        }
      }
    },
    "session": {
      "type": "object",
      "properties": {
        "timeoutMilliseconds": {
          "type": "integer",
          "minimum": 0,
          "default": 60000,
          "description": "--session-timeout/--st"
        },
        "keepAliveIntervalMilliseconds": {
          "type": "integer",
          "minimum": 0,
          "default": 10000,
          "description": "--session-keep-alive/--ska"
        },
        "reconnectPeriodMilliseconds": {
          "type": "integer",
          "minimum": 0,
          "default": 2000,
          "description": "--session-reconnect-period/--srp"
        },
        "reconnectExponentialBackOffMilliseconds": {
          "type": "integer",
          "minimum": -1,
          "default": 10000,
          "description": "--session-reconnect-backoff/--srb"
        }
      }
    },
    "subscription": {
      "type": "object",
      "properties": {
        "maxItems": {
          "type": "integer",
          "minimum": 1,
          "default": 1000,
          "description": "--subscription-max-items/--smi"
        },
        "lifeTimeMilliseconds": {
          "type": "integer",
          "minimum": 0,
          "default": 60000,
          "description": "--subscription-life-time/--slt"
        }
      }
    },
    "security": {
      "type": "object",
      "properties": {
        "autoAcceptUntrustedServerCertificates": {
          "type": "boolean",
          "default": False,
          "description": "--accept-untrusted-certs/--auc"
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
          "default": None,
          "description": "--security-policy/--sp"
        },
        "securityMode": {
          "type": ["string", "null"],
          "enum": [
            "none",
            "sign",
            "signAndEncrypt",
            None
          ],
          "default": None,
          "description": "--security-mode/--sm"
        }
      }
    },
    "runAssetDiscovery": {
      "type": "boolean",
      "default": False,
      "description": "--run-asset-discovery/--rad"
    }
  }
}