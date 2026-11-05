# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Resolve older GA lines from hash-verified published provisioning wheels."""

import ast
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, build_opener
from zipfile import ZipFile


INDEX_URL = "https://aka.ms/azure-cli-extension-index-v1"
TEMPLATE_PATH = "azext_edge/edge/providers/orchestration/template.py"


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d+\.\d+\.\d+", value):
        raise ValueError(f"Expected a stable semantic version, got {value!r}.")
    return tuple(int(part) for part in value.split("."))


def validate_url(value):
    url = urlsplit(value)
    if (
        url.scheme != "https" or not url.hostname or url.username is not None
        or url.password is not None or url.query or url.fragment
    ):
        raise ValueError("Release artifacts must use credential-free HTTPS.")


class ReleaseRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def download(url):
    validate_url(url)
    with build_opener(ReleaseRedirectHandler()).open(url, timeout=60) as response:
        validate_url(response.url)
        return response.read()


def template_identity(source):
    """Read literal release metadata without importing or executing a wheel."""
    for node in ast.parse(source).body:
        if not isinstance(node, ast.Assign) or not any(
            isinstance(target, ast.Name) and target.id == "TEMPLATE_BLUEPRINT_INSTANCE" for target in node.targets
        ):
            continue
        if not isinstance(node.value, ast.Call):
            break
        for keyword in node.value.keywords:
            if keyword.arg == "content":
                variables = ast.literal_eval(keyword.value)["variables"]
                version = variables["VERSIONS"]["iotOperations"]
                train = variables["TRAINS"]["iotOperations"]
                version_tuple(version)
                return version, train
    raise ValueError("Provisioning template does not expose a literal AIO runtime identity.")


def resolve_previous(current_version, generations, entries, fetch=download):
    current_line = version_tuple(current_version)[:2]
    definitions = {}
    releases = [
        entry for entry in entries
        if re.fullmatch(r"\d+\.\d+\.\d+", entry["metadata"]["version"])
    ]
    releases.sort(key=lambda entry: version_tuple(entry["metadata"]["version"]), reverse=True)
    for entry in releases:
        content = fetch(entry["downloadUrl"])
        if hashlib.sha256(content).hexdigest() != entry["sha256Digest"].lower():
            raise ValueError(f"Provisioning wheel SHA256 mismatch: {entry['metadata']['version']}.")
        with ZipFile(BytesIO(content)) as archive:
            version, train = template_identity(archive.read(TEMPLATE_PATH))
        line = version_tuple(version)[:2]
        if train.lower() != "stable" or line >= current_line:
            continue
        if line not in definitions:
            definitions[line] = {
                "wheel_url": entry["downloadUrl"], "sha256": entry["sha256Digest"],
                "version": version, "train": "stable", "create_args": "",
            }
        # Published CLI releases are inspected newest first; stop once the requested
        # previous GA lines have provisioning artifacts.
        if len(definitions) >= max(generations):
            break
    lines = sorted(definitions, reverse=True)
    if len(lines) < max(generations):
        raise ValueError(f"Cannot resolve {max(generations)} previous GA lines before {current_version}.")
    return {f"n-{number}": definitions[lines[number - 1]] for number in generations}


def discover_previous(generations):
    root = Path(__file__).resolve().parents[3]
    current_version, train = template_identity((root / TEMPLATE_PATH).read_text(encoding="utf-8"))
    if train.lower() != "stable":
        raise ValueError("Current GA blueprint must use the stable release train.")
    entries = json.loads(download(INDEX_URL))["extensions"]["azure-iot-ops"]
    return resolve_previous(current_version, generations, entries)
