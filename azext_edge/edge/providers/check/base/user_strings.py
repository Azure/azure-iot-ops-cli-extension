# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

CONNECTIVITY_ERROR = "{0} Is there connectivity to the cluster?"
MULTINODE_CLUSTER_MSG = "Currently, only single-node clusters are officially supported for AIO deployments"
NO_NODES_MSG = "No nodes detected."
UNABLE_TO_DETERMINE_VERSION_MSG = CONNECTIVITY_ERROR.format("Unable to determine kubernetes version.")
UNABLE_TO_FETCH_NODES_MSG = CONNECTIVITY_ERROR.format("Unable to fetch nodes.")
