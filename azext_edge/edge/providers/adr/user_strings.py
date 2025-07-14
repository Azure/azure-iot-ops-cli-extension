# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

# Base Strings
CUSTOM_LOCATION_DOES_NOT_EXIST_ERROR = "Cluster associated with custom location {0} does not exist."
CUSTOM_LOCATION_NOT_FOUND_MSG = "Custom location {0} not found. The command may fail."
CLUSTER_NOT_FOUND_MSG = "Cluster associated with the custom location {0} not found. "\
    "The command may fail."
CLUSTER_OFFLINE_MSG = "Cluster {0} is not connected. The cluster may not update correctly."
MISSING_CLUSTER_CUSTOM_LOCATION_ERROR = "Need to provide either cluster name or custom location"
MISSING_EXTENSION_ERROR = "Cluster {0} is missing the {1} extension."
MULTIPLE_CUSTOM_LOCATIONS_ERROR = "The following custom locations were found for cluster {0}: \n{1}. "\
    "Please specify which custom location to use."
MULTIPLE_POSSIBLE_ITEMS_ERROR = "Found {0} {1}s with the name {2}. Please provide the resource group "\
    "for the {1}."
NO_EXTENDED_LOCATION_TO_CHECK_MSG = "No extended location is associated. Cluster checks are skipped."


# Asset Strings
DUPLICATE_EVENT_ERROR = "An event with the name {0} is already present. Please use a different name for "\
    "your event or --replace."
DUPLICATE_POINT_ERROR = "A data-point with the name {0} is already present. Please use a different name for "\
    "your data-point or --replace."
ENDPOINT_NOT_FOUND_WARNING = "Endpoint {0} not found. The asset may fail provisioning."
INVALID_OBSERVABILITY_MODE_ERROR = "{0} has an invalid observability mode [{1}]."
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
