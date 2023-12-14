# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

# Asset Strings
ENDPOINT_NOT_FOUND_WARNING = "Endpoint {0} not found. The asset may fail provisioning."
MISSING_DATA_EVENT_ERROR = "At least one data point or event is required to create the asset."


# Asset Endpoint Strings
AUTH_REF_MISMATCH_ERROR = "Please choose to use a certificate reference or username and password references for "\
    "authentication."
CERT_AUTH_NOT_SUPPORTED = "Certificate authentication for user authentication is not supported yet."
GENERAL_AUTH_REF_MISMATCH_ERROR = "Invalid combination of authentication mode and parameters."
MISSING_TRANS_AUTH_PROP_ERROR = "Transport authentication ({0}) needs to have both thumbprint and secret."
MISSING_USERPASS_REF_ERROR = "Please provide username and password reference for Username-Password authentication."
REMOVED_CERT_REF_MSG = "Previously used certificate reference was removed."
REMOVED_USERPASS_REF_MSG = "Previously used username and password references were removed."
UNRECOGNIZED_TRANS_AUTH_PROP_ERROR = "Transport authentication ({0}) has unrecognized inputs. Accepted inputs are "\
    "`thumbprint`, `secret`, and `password`."
