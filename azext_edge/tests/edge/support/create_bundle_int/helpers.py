# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from knack.log import get_logger
from typing import Dict, Iterable, List, Optional, Tuple, TypedDict, Union
from os import path
from zipfile import ZipFile
import pytest
from azure.cli.core.azclierror import CLIInternalError
from azext_edge.edge.common import OpsServiceType
from azext_edge.edge.providers.edge_api.base import EdgeApiManager, EdgeResourceApi
from azext_edge.edge.providers.support.arcagents import ARC_AGENTS
from ....helpers import (
    PLURAL_KEY,
    find_extra_or_missing_names,
    get_kubectl_custom_items,
    get_kubectl_workload_items,
    run,
)
from ....generators import generate_random_string


logger = get_logger(__name__)
BASE_ZIP_PATH = "__root__"
WORKLOAD_TYPES = [
    "clusterrole",
    "configmap",
    "crb",
    "cronjob",
    "daemonset",
    "deployment",
    "job",
    "mwc",
    "pod",
    "podmetric",
    "pvc",
    "replicaset",
    "service",
    "statefulset",
    "vwc",
]


class Namespaces(TypedDict):
    """Dictionary for namespaces determined from the support bundle."""
    arc: Optional[str] = None
    aio: Optional[str] = None
    acs: Optional[str] = None
    acstor: Optional[str] = None
    ssc: Optional[str] = None
    usage_system: Optional[str] = None
    certmanager: Optional[str] = None


class DeconstructedFileName(TypedDict):
    """
    Deconstructed file name object.

    The name should reflect the same name as that when fetched from kubectl.
    Other fields are used to help with the file name "conventions".
    """
    name: str
    extension: str
    full_name: str
    # only for custom types
    version: Optional[str]
    # when there are extra parts in the name, like "msi-adapter", "init-runner"
    # but these are not part of the name fetched from kubectl
    descriptor: Optional[str]
    # when there are even more parts, like "previous", "init"
    # but these are not part of the name fetched from kubectl
    sub_descriptor: Optional[str]


def assert_file_names(files: List[str]):
    """
    Simple asserts for file names.

    Ensures trace file conventions, extension conventions, etc
    """
    for full_name in files:
        name = split_name(full_name)
        file_type = name.pop(0)
        extension = name.pop(-1)
        # trace files
        if extension == "pb":
            assert name[-1] == "otlp"
            continue
        if extension == "json":
            assert name[-1] == "tempo"
            continue

        assert extension in ["log", "txt", "yaml"]
        if file_type not in WORKLOAD_TYPES:
            if extension == "txt":
                continue
            assert name.pop(0).startswith("v")

        short_name = name.pop(0)
        if short_name == "aio-opc-opc":
            short_name += f".{name.pop(0)}"
        if "metric" in name and extension == "yaml":
            short_name += f".{name.pop(0)}"

        # Handle webhook configurations that include extra '.'-separated elements
        if file_type in ["vwc", "mwc"] and extension == "yaml" and name:
            # For webhook configurations, consume any remaining API group parts
            while name:
                name.pop(0)

        assert bool(name) == (extension != "yaml")


def convert_file_names(files: List[str]) -> Dict[str, List[Dict[str, str]]]:
    """
    Maps deployment/pod/etc to list of disassembled file names

    Please see comments for examples/conventions.
    """
    file_name_objs = {}
    for full_name in files:
        name_parts = split_name(full_name)
        file_type = name_parts.pop(0)
        name_obj = DeconstructedFileName({"extension": name_parts.pop(-1), "full_name": full_name})

        if file_type == "pod" and name_parts[-1] == "metric":
            # note: not a real type
            file_type = "podmetric"

        if name_obj["extension"] in ["pb", "json"]:
            if "trace" not in file_name_objs:
                file_name_objs["trace"] = []
            # trace file
            # aio-broker-dmqtt-frontend-1.Publish.b9c3173d9c2b97b75edfb6cf7cb482f2.otlp.pb
            # aio-broker-dmqtt-frontend-1.Publish.b9c3173d9c2b97b75edfb6cf7cb482f2.tempo.json
            name_obj["name"] = file_type
            name_obj["action"] = name_parts.pop(0).lower()
            name_obj["identifier"] = name_parts.pop(0)
            file_name_objs["trace"].append(name_obj)
            continue

        if file_type not in file_name_objs:
            file_name_objs[file_type] = []

        assert name_obj["extension"] in ["log", "txt", "yaml"]

        # custom types should have a v
        if file_type not in WORKLOAD_TYPES:
            if name_obj["extension"] != "yaml":
                # check diagnositcs.txt later
                file_name_objs[file_type].append(name_obj)
                continue
            name_obj["version"] = name_parts.pop(0)
            assert name_obj["version"].startswith("v")
        name_obj["name"] = name_parts.pop(0)

        # custom re-adding
        if name_obj["name"] == "aio-opc-opc":
            name_obj["name"] += f".{name_parts.pop(0)}"
        if name_obj["name"] == "kube-root-ca":
            name_obj["name"] += f".{name_parts.pop(0)}"

        # for webhooks, we want the "url"
        # ex: aio-akri-admission-webhook.akri.com
        if file_type in ["vwc", "mwc"]:
            # Assume the rest of the name is supposed to be in the name
            while name_parts:
                name_obj["name"] += f".{name_parts.pop(0)}"

        # something like "msi-adapter", "init-runner"
        if name_parts:
            name_obj["descriptor"] = name_parts.pop(0)
        # something like "previous", "init"
        if name_parts:
            name_obj["sub_descriptor"] = name_parts.pop(0)

        file_name_objs[file_type].append(name_obj)

    return file_name_objs


def check_cluster_label_coverage(
    prefixes: Union[str, List[str]],
    expected_label: Tuple[str, str],
    workload_types: Optional[List[str]] = None,
    known_exclusions: Optional[List[str]] = None,
    accepted_labels: Optional[List[str]] = None,
):
    """
    Inverse label check: finds all cluster resources whose names match the given prefixes
    (without any label filter) and asserts each one carries the expected label.

    This catches resources that exist on the cluster but are missing the label, which means
    the support bundle CLI would silently skip them. The forward-direction tests (label → bundle)
    cannot catch these because kubectl returns nothing for unlabeled resources.

    Args:
        prefixes: Name prefix(es) used to identify resources belonging to this service.
        expected_label: Tuple of (label_key, label_value) e.g.
            ("app.kubernetes.io/name", "microsoft-iotoperations-dataflows").
        workload_types: Resource types to scan. Defaults to WORKLOAD_TYPES.
        known_exclusions: List of "namespace/name" strings to skip (intentionally unlabeled resources).
        accepted_labels: Additional label values (for the same key) that are considered valid,
            e.g. sub-component labels that the support provider captures via a separate label selector.
    """
    if isinstance(prefixes, str):
        prefixes = [prefixes]
    if workload_types is None:
        workload_types = WORKLOAD_TYPES
    if known_exclusions is None:
        known_exclusions = []
    if accepted_labels is None:
        accepted_labels = []

    label_key, label_value = expected_label
    missing_label_resources = []

    key_to_full_map = {
        "pvc": "persistentvolumeclaim",
        "vwc": "validatingwebhookconfiguration",
        "mwc": "mutatingwebhookconfiguration",
        "crb": "clusterrolebinding",
    }

    for resource_type in workload_types:
        full_type = key_to_full_map.get(resource_type, resource_type)
        try:
            kubectl_items = run(f"kubectl get {full_type} -A -o json")
        except CLIInternalError as e:
            logger.warning("kubectl get %s failed, skipping label coverage check for this type: %s", full_type, e)
            continue

        for item in kubectl_items.get("items", []):
            name = item["metadata"]["name"]
            namespace = item["metadata"].get("namespace", "")
            exclusion_key = f"{namespace}/{name}"

            if not any(name.startswith(p) for p in prefixes):
                continue
            if exclusion_key in known_exclusions:
                continue

            actual_label = item["metadata"].get("labels", {}).get(label_key)
            if actual_label == label_value or actual_label in accepted_labels:
                continue
            missing_label_resources.append(
                f"{full_type} {exclusion_key}: expected {label_key}={label_value}, got {actual_label}"
            )

    assert not missing_label_resources, (
        "Resources found on cluster with matching name prefix but missing/wrong label "
        "(would be silently skipped by support bundle):\n"
        + "\n".join(missing_label_resources)
    )


def check_custom_resource_files(
    file_objs: Dict[str, List[Dict[str, str]]],
    resource_apis: Union[EdgeResourceApi, Iterable[EdgeResourceApi]],
    namespace: Optional[str] = None,
    exclude_kinds: Optional[List[str]] = None,
):
    """
    Helper function to check custom resource files against cluster resources.

    Will check by version, kind, and name and ensure the kinds match up.

    Args:
        file_obs (Dict[str, List[Dict[str, str]]]): Dictionary of file objects, where key is
            the kind and value is a list of dicts with file info.
        resource_apis (Union[EdgeResourceApi, Iterable[EdgeResourceApi]]): EdgeResourceApi or
            iterable of EdgeResourceApi to check against cluster resources.
        namespace (Optional[str]): Namespace to check resources in, if applicable.
        exclude_kinds (Optional[List[str]]): List of kinds to exclude from the check.
    """
    # Note: we use the resoource api over EdgeApiManager due to some resources having multiple resource
    # apis with respective files being in different folders, see how this function is called in certmanager
    # and arccontainerstorage tests.

    # make sure we are dealing with an iterable of EdgeResourceApi
    if isinstance(resource_apis, EdgeResourceApi):
        resource_apis = [resource_apis]

    # first get all the cluster resources
    # since there are mutliple apis now, key is (kind, version) and value is set of resource names
    cluster_resource_names: Dict[Tuple[str, str], set] = {}
    for api in resource_apis:
        # skip validation if resource is not deployed
        if not api.is_deployed():
            continue

        resource_map = get_kubectl_custom_items(resource_api=api, namespace=namespace, include_plural=True)
        resource_kinds = set(api.kinds) - set(exclude_kinds or [])
        for kind in resource_kinds:
            cluster_resources = resource_map[kind]
            resources = {r for r in cluster_resources if r != "_plural_"}
            # only add if there is a plural key and resources found
            # subresources like scale will not have a plural
            if cluster_resources.get(PLURAL_KEY) and resources:
                kind_version_key = (kind, api.version)
                cluster_resource_names.setdefault(kind_version_key, set()).update(resources)

    # second, build up the file resource names in the same manor
    file_resource_names: Dict[Tuple[str, str], set] = {}
    for kind, objs in file_objs.items():
        for obj in objs:
            kind_version_key = (kind, obj.get("version", "v1"))
            file_resource_names.setdefault(kind_version_key, set()).add(obj["name"])

    # this will only check the custom crds so if there are workload types, will need to have an extra check
    # outside of this function
    assert set(cluster_resource_names.keys()).issubset(set(file_resource_names.keys())), (
        f"Expected cluster resources types not found in files:\n"
        f"{file_resource_names.keys()=}\n{cluster_resource_names.keys()=}"
    )
    for key, resource_names in cluster_resource_names.items():
        find_extra_or_missing_names(
            result_names=file_resource_names[key],
            pre_expected_names=resource_names,
            post_expected_names=resource_names
        )


def check_workload_resource_files(
    file_objs: Dict[str, List[Dict[str, str]]],
    pre_bundle_items: dict,
    prefixes: Union[str, List[str]],
    bundle_path: str,
    expected_label: Optional[str] = None,
    pre_bundle_optional_items: Optional[Dict[str, List[str]]] = None,
):
    """
    Helper function to check workload resource files against cluster resources.

    See WORKLOAD_TYPES for checked types here.
    """
    # TODO: improve docstring to describe how pods are handled, etc
    # pod
    file_pods = {}
    for file in file_objs.get("pod", []):
        if file["name"] not in file_pods:
            file_pods[file["name"]] = {"yaml": False}
        converted_file = file_pods[file["name"]]

        # for all of these files, make sure that it was not seen before
        # in the end, there should be one yaml
        # if sub_descriptor file present, descriptor file should be there too (has exceptions)
        if file["extension"] == "yaml":
            # only one yaml per pod
            assert not converted_file["yaml"]
            converted_file["yaml"] = True
        elif file.get("sub_descriptor") in ["init", None]:
            assert f"{file['descriptor']}.{file.get('sub_descriptor')}" not in converted_file
            converted_file[file["descriptor"]] = True
        else:
            assert file["sub_descriptor"] == "previous", f"Full file name: {file['full_name']}, file_obj {file}"
            sub_key = f"{file['descriptor']}.{file['sub_descriptor']}"
            assert sub_key not in converted_file, f"Full file name: {file['full_name']}, file_obj {file}"
            converted_file[sub_key] = True
            # if msi-adapter.previous present, msi-adapter must present too
            # for some reason does not apply to xxx.init
            if file["descriptor"] not in converted_file:
                converted_file[file["descriptor"]] = False
            # TODO - verify, safety hatch for mtls failures?
            if file["descriptor"] == "mtls" and file["sub_descriptor"] == "previous":
                converted_file[file["descriptor"]] = True

    post_pods = get_kubectl_workload_items(prefixes, service_type="pod", label_match=expected_label)
    check_log_for_evicted_pods(bundle_path, file_objs.get("pod", []))
    _compare_support_bundle_names(
        prefixes=prefixes,
        resource_type="pod",
        bundle_names=file_pods.keys(),
        pre_bundle_resources=pre_bundle_items.pop("pod", {}),
        post_bundle_resources=post_pods,
    )

    for name, files in file_pods.items():
        for extension, value in files.items():
            assert value, f"Pod {name} is missing {extension}."

    # other
    def _check_non_pod_files(
        pre_bundle_items: Dict[str, List[str]], required: bool = False, expected_label: Optional[str] = None
    ):
        for key, names in pre_bundle_items.items():
            try:
                post_bundle_items = get_kubectl_workload_items(prefixes, service_type=key, label_match=expected_label)
                for file in file_objs.get(key, []):
                    assert file["extension"] == "yaml"

                file_prefix = key
                if key == "clusterrolebinding":
                    # file prefix would be crb
                    file_prefix = "crb"
                present_names = [file["name"] for file in file_objs.get(file_prefix, [])]
                # kube-root-ca.crt gets split configmap.kube-root-ca.crt.yaml
                # maybe add in a way to compare full names? or limit splitting for certain types?
                _compare_support_bundle_names(
                    prefixes=prefixes,
                    resource_type=key,
                    bundle_names=present_names,
                    pre_bundle_resources=names,
                    post_bundle_resources=post_bundle_items,
                )
            except CLIInternalError as e:
                if required:
                    raise e

    _check_non_pod_files(pre_bundle_items, expected_label=expected_label)
    if pre_bundle_optional_items:
        _check_non_pod_files(pre_bundle_optional_items, required=False, expected_label=expected_label)


def check_log_for_evicted_pods(bundle_dir: str, file_pods: List[Dict[str, str]]):
    # TODO: docstring
    # open the file using bundle_dir and check for evicted pods
    name_extension_pair = list(set([(file["name"], file["extension"]) for file in file_pods]))
    # TODO: upcoming fix will get file content earlier
    with ZipFile(bundle_dir, "r") as zip:
        file_names = zip.namelist()
        for name, extension in name_extension_pair:
            if extension == "log":
                # find file path in file_names that has name and extension
                file_path = next((file for file in file_names if file.endswith(name + ".yaml")), None)
                if not file_path:
                    continue
                with zip.open(file_path) as pod_content:
                    log_content = pod_content.read().decode("utf-8")
                    assert "Evicted" not in log_content, f"Evicted pod {name} log found in bundle."


def get_all_kinds_from_manager(
    manager: EdgeApiManager,
    exclude_kinds: Optional[List[str]] = None,
) -> set:
    """
    Get all kinds from EdgeApiManager, excluding specified kinds.

    Args:
        manager (EdgeApiManager): EdgeApiManager instance to get kinds from.
        exclude_kinds (Optional[List[str]]): List of kinds to exclude from the result.

    Returns:
        set: Set of kinds excluding the specified ones.
    """
    exclude_kinds = exclude_kinds or []
    result = set()
    for api in manager.resource_apis:
        if api.kinds:
            result.update(api.kinds)
    return result - set(exclude_kinds)


def get_file_map(  # noqa: C901
    walk_result: Dict[str, Dict[str, List[str]]],
    ops_service: str,
    mq_traces: bool = False,
) -> Dict[str, Dict[str, List[Dict[str, str]]]]:
    """
    Converts the walk result into a file map for the support bundle.

    The number of expected folders will be checked here
    based on the ops_service and the namespaces found in the walk result.
    """
    # Remove all files that will not be checked
    namespaces = process_top_levels(walk_result, ops_service)

    # get the namespaces
    arc_namespace = namespaces.get("arc")
    aio_namespace = namespaces.get("aio")
    acs_namespace = namespaces.get("acs")
    acstor_namespace = namespaces.get("acstor")
    ssc_namespace = namespaces.get("ssc")
    c_namespace = namespaces.get("usage_system")
    certmanager_namespace = namespaces.get("certmanager")
    ops_path = None

    if aio_namespace:
        walk_result.pop(path.join(BASE_ZIP_PATH, aio_namespace))
        ops_path = path.join(BASE_ZIP_PATH, aio_namespace, ops_service)

    # separate namespaces
    file_map = {"__namespaces__": {}}

    # by default, there will be arc agents, meta and meso in every bundle
    num_additional_services = len(ARC_AGENTS)
    meta_path = path.join(BASE_ZIP_PATH, aio_namespace, "meta")
    meso_path = path.join(BASE_ZIP_PATH, aio_namespace, "meso")
    if meta_path in walk_result:
        num_additional_services += 1
    if meso_path in walk_result and ops_service != OpsServiceType.meso.value:
        num_additional_services += 1

    if arc_namespace:
        file_map["arc"] = {}
        file_map["__namespaces__"]["arc"] = arc_namespace
        for agent, _ in ARC_AGENTS:
            agent_path = path.join(BASE_ZIP_PATH, arc_namespace, "arcagents", agent)
            file_map["arc"][agent] = convert_file_names(walk_result[agent_path]["files"])

    # TODO: explain the magic numbers (1, 2 better). Might need some refactoring too
    if mq_traces and path.join(ops_path, "traces") in walk_result:
        # still possible for no traces if cluster is too new
        # adding two folders - one for aio and one for traces
        assert len(walk_result) == 2 + num_additional_services, f"walk result keys: {walk_result.keys()}"
        assert walk_result[ops_path]["folders"]
        assert not walk_result[path.join(ops_path, "traces")]["folders"]
        file_map["traces"] = convert_file_names(walk_result[path.join(ops_path, "traces")]["files"])

    elif ops_service == "billing":
        assert len(walk_result) == 2 + num_additional_services, f"walk result keys: {walk_result.keys()}"
        ops_path = path.join(BASE_ZIP_PATH, aio_namespace, ops_service)
        c_path = path.join(BASE_ZIP_PATH, c_namespace, "clusterconfig", ops_service)
        file_map["usage"] = convert_file_names(walk_result[c_path]["files"])
        file_map["__namespaces__"]["usage"] = c_namespace

    elif ops_service == "acs":
        if acstor_namespace:
            # resources in both acstor_namespace and acs_namespace
            assert len(walk_result) == 1 + num_additional_services, f"walk result keys: {walk_result.keys()}"
            acstor_path = path.join(BASE_ZIP_PATH, acstor_namespace, "containerstorage")
            file_map["acstor"] = convert_file_names(walk_result[acstor_path]["files"])
            file_map["__namespaces__"]["acstor"] = acstor_namespace
        elif acs_namespace:
            # resources only in acs_namespace
            assert len(walk_result) == 1 + num_additional_services, f"walk result keys: {walk_result.keys()}"
        else:
            # TODO: should probably have a better way of determining something is not there (as in rely on something
            # beyond folder structure)
            pytest.skip(f"No bundles created for {ops_service}.")
        if acs_namespace:
            acs_path = path.join(BASE_ZIP_PATH, acs_namespace, "arccontainerstorage")
            file_map["acs"] = convert_file_names(walk_result[acs_path]["files"])
            file_map["__namespaces__"]["acs"] = acs_namespace

        # no files for aio, skip the rest assertions
        return file_map

    elif ops_service == OpsServiceType.secretstore.value:
        ops_path = path.join(BASE_ZIP_PATH, aio_namespace, OpsServiceType.secretstore.value)
        ssc_path = path.join(BASE_ZIP_PATH, ssc_namespace, OpsServiceType.secretstore.value)
        if ops_path not in walk_result:
            # no CR created in aio namespace
            # since CR is the only resource type under aio, skip the rest assertions
            assert len(walk_result) == 1 + num_additional_services, f"walk result keys: {walk_result.keys()}"
            pytest.skip(f"No bundles created for {ops_service}.")
        else:
            assert len(walk_result) == 2 + num_additional_services, f"walk result keys: {walk_result.keys()}"
        file_map[OpsServiceType.secretstore.value] = convert_file_names(walk_result[ssc_path]["files"])
        file_map["__namespaces__"][OpsServiceType.secretstore.value] = ssc_namespace

    elif ops_service == OpsServiceType.azuremonitor.value:
        monitor_path = path.join(BASE_ZIP_PATH, arc_namespace, OpsServiceType.azuremonitor.value)
        assert len(walk_result) == 1 + num_additional_services, f"walk result keys: {walk_result.keys()}"
        file_map[OpsServiceType.azuremonitor.value] = convert_file_names(walk_result[monitor_path]["files"])
        file_map["__namespaces__"][OpsServiceType.azuremonitor.value] = arc_namespace

        # no files for aio, skip the rest assertions
        return file_map

    elif ops_service == "certmanager":
        if acstor_namespace:
            num_additional_services += 1
            certmanager_acstor_path = path.join(BASE_ZIP_PATH, acstor_namespace, "certmanager")
            file_map["certmanager_acstor"] = convert_file_names(walk_result[certmanager_acstor_path]["files"])
            file_map["__namespaces__"]["acstor"] = acstor_namespace

        if ssc_namespace:
            num_additional_services += 1
            certmanager_ssc_path = path.join(BASE_ZIP_PATH, ssc_namespace, "certmanager")
            file_map["certmanager_ssc"] = convert_file_names(walk_result[certmanager_ssc_path]["files"])
            file_map["__namespaces__"]["ssc"] = ssc_namespace

        certmanager_path = path.join(BASE_ZIP_PATH, certmanager_namespace, "certmanager")
        file_map["certmanager"] = convert_file_names(walk_result[certmanager_path]["files"])
        certmanager_aio_path = path.join(BASE_ZIP_PATH, aio_namespace, "certmanager")
        file_map["certmanager_aio"] = convert_file_names(walk_result[certmanager_aio_path]["files"])
        certmanager_arc_path = path.join(BASE_ZIP_PATH, arc_namespace, "certmanager")
        file_map["certmanager_arc"] = convert_file_names(walk_result[certmanager_arc_path]["files"])
        file_map["__namespaces__"]["certmanager"] = certmanager_namespace
        assert len(walk_result) == 3 + num_additional_services, f"walk result keys: {walk_result.keys()}"

    elif ops_service == "deviceregistry":
        if ops_path not in walk_result:
            assert len(walk_result) == num_additional_services, f"walk result keys: {walk_result.keys()}"
            pytest.skip(f"No bundles created for {ops_service}.")
        else:
            assert len(walk_result) == 1 + num_additional_services, f"walk result keys: {walk_result.keys()}"

    # remove ops_service that are not selectable by --svc
    elif ops_service not in ["otel", "meta"]:
        assert len(walk_result) == 1 + num_additional_services, f"walk result keys: {walk_result.keys()}"
        assert not walk_result[ops_path]["folders"]

    file_map["aio"] = convert_file_names(walk_result[ops_path]["files"])
    file_map["__namespaces__"]["aio"] = aio_namespace
    return file_map


# TODO: rename this to something more appropriate
def process_top_levels(
    walk_result: Dict[str, Dict[str, List[str]]],
    ops_service: str,
) -> Dict[str, Union[str, None]]:
    """
    Mostly used to determine namespaces from the top level of the support bundle.
    """
    level_0 = walk_result.pop(BASE_ZIP_PATH)
    for file in ["events.yaml", "nodes.yaml", "storage-classes.yaml", "azure-clusterconfig.yaml"]:
        assert file in level_0["files"]
    if not level_0["folders"]:
        pytest.skip(f"No bundles created for {ops_service}.")
    namespace_folders = level_0["folders"]
    namespaces = Namespaces()

    def _get_namespace_determinating_files(name: str, folder: str, file_prefix: str) -> List[str]:
        level1 = walk_result.get(path.join(BASE_ZIP_PATH, name, folder), {})
        return [f for f in level1.get("files", []) if f.startswith(file_prefix)]

    cert_resource_namespaces = []
    containerstorage_service = ""

    # TODO: most of the namespace determination logic can be removed to hardcoded namespace values
    # AIO is the one that needs to be kept (will need to double check for other namespaces)
    for name in namespace_folders:
        # determine which namespace belongs to aio vs billing
        if _get_namespace_determinating_files(
            name=name, folder=path.join("clusterconfig", "billing"), file_prefix="deployment"
        ):
            # if there is a deployment, should be azure-extensions-usage-system
            namespaces["usage_system"] = name
        elif _get_namespace_determinating_files(
            name=name, folder=path.join("arcagents", ARC_AGENTS[0][0]), file_prefix="pod"
        ):
            namespaces["arc"] = name
        elif _get_namespace_determinating_files(
            name=name, folder="arccontainerstorage", file_prefix="edgestorageconfiguration"
        ):
            namespaces["acs"] = name
        elif _get_namespace_determinating_files(
            name=name, folder="containerstorage", file_prefix="configmap"
        ):
            containerstorage_service = "containerstorage"
            namespaces["acstor"] = name
        elif _get_namespace_determinating_files(
            name=name, folder=OpsServiceType.secretstore.value, file_prefix="deployment"
        ):
            namespaces["ssc"] = name
        elif _get_namespace_determinating_files(name=name, folder="certmanager", file_prefix="deployment"):
            namespaces["certmanager"] = name
        elif _get_namespace_determinating_files(name=name, folder="meta", file_prefix="instance"):
            namespaces["aio"] = name

        if _get_namespace_determinating_files(name=name, folder="certmanager", file_prefix="configmap"):
            cert_resource_namespaces.append(name)

    # find the acstor namespace if fault tolerance is enabled,
    # but support bundle only getting certmanager resources
    if not namespaces.get("acstor"):
        # acstor_namespace should be the namespace besides certmanager, arc, and aio namespace
        namespaces["acstor"] = next(
            (
                name
                for name in cert_resource_namespaces
                if name not in [
                    namespaces.get("certmanager"),
                    namespaces.get("arc"),
                    namespaces.get("aio"),
                    namespaces.get("ssc")
                ]
            ),
            None,
        )

    if not namespaces.get("ssc"):
        # ssc_namespace should be the namespace besides certmanager, arc, and aio namespace
        namespaces["ssc"] = next(
            (
                name
                for name in cert_resource_namespaces
                if name not in [
                    namespaces.get("certmanager"),
                    namespaces.get("arc"),
                    namespaces.get("aio"),
                    namespaces.get("acstor")
                ]
            ),
            None,
        )

    _clean_up_folders(
        walk_result=walk_result,
        namespaces=namespaces,
        containerstorage_service=containerstorage_service,
    )

    logger.debug("Determined the following namespaces:")
    logger.debug(f"AIO namespace: {namespaces.get('aio')}")
    logger.debug(f"Usage system namespace: {namespaces.get('usage_system')}")
    logger.debug(f"ARC namespace: {namespaces.get('arc')}")
    logger.debug(f"ACS namespace: {namespaces.get('acs')}")
    logger.debug(f"ACSTOR namespace: {namespaces.get('acstor')}")
    logger.debug(f"SSC namespace: {namespaces.get('ssc')}")
    logger.debug(f"Certmanager namespace: {namespaces.get('certmanager')}")

    return namespaces


def run_bundle_command(
    command: str,
    tracked_files: List[str],
) -> Tuple[Dict[str, Dict[str, List[str]]], str]:
    """
    Runs the support bundle command and returns the walk result.

    The walk result is a dictionary representing the structure of the support bundle,
    in which every key is a path and the value is a dictionary with 'folders' and 'files'.

    Args:
        command (str): The command to run for creating the support bundle.
        tracked_files (List[str]): List to track files created by the command.
    Returns:
        Tuple[Dict[str, Dict[str, List[str]]], str]: A tuple containing the walk result and the bundle path.
    """
    # add in a name for more uniqueness
    command += f" --bundle-name test_bundle_{generate_random_string(size=8)}"
    result = run(command)
    if not result:
        pytest.skip("No bundle was created.")
    assert result["bundlePath"]
    tracked_files.append(result["bundlePath"])
    # transform this into a walk result of an extracted zip file
    # TODO: add in a class for this (maybe typed dict?)
    walk_result = {}
    with ZipFile(result["bundlePath"], "r") as zip:
        file_names = zip.namelist()
        for name in file_names:
            name = path.join(BASE_ZIP_PATH, name)
            directory, file_name = path.split(name)

            # decompose incase seperator from zipfile is different from os sep. Example:
            # windows sep is \\
            # zipfile returns azure-extensions-usage-system/clusterconfig/billing
            decomposed_folders = []
            while path.split(directory)[0]:
                directory, sub = path.split(directory)
                decomposed_folders.append(sub)
            decomposed_folders.append(directory)

            built_path = ""
            while decomposed_folders:
                folder = decomposed_folders.pop(-1)
                # make sure to add in directory to parent folder if it exists
                if built_path and folder not in walk_result[built_path]["folders"]:
                    walk_result[built_path]["folders"].append(folder)

                built_path = path.join(built_path, folder)
                # add in the current built directory in
                if built_path not in walk_result:
                    walk_result[built_path] = {"folders": [], "files": []}

            # lastly add in the file (with the correct seperators)
            walk_result[built_path]["files"].append(file_name)

    return walk_result, result["bundlePath"]


def split_name(name: str) -> List[str]:
    """
    Splits a name by the .'s.

    If a number is present (ex: versioning like 1.0.0-preview), do not split that portion.
    Make sure the extension is split out (last . for the extension).
    """
    first_pass = name.split(".")
    second_pass = []
    for i in range(len(first_pass)):
        # we should not need to worry about trying to access too early
        # since the first part should be the workload type (ex: pod)
        if all([i != (len(first_pass) - 1), first_pass[i].isnumeric() or first_pass[i - 1].isnumeric()]):
            second_pass[-1] = f"{second_pass[-1]}.{first_pass[i]}"
        else:
            second_pass.append(first_pass[i])

    return second_pass


def _clean_up_folders(
    walk_result: Dict[str, Dict[str, List[str]]],
    namespaces: Dict[str, str],
    containerstorage_service: str,
):
    """
    Clean up folders from walk_result that are not needed for following
    IoT operation namespace assertion.
    """
    # TODO: add in more information as to why certain folders are removed to the docstring.
    arc_namespace = namespaces.get("arc")
    acs_namespace = namespaces.get("acs")
    acstor_namespace = namespaces.get("acstor")
    certmanager_namespace = namespaces.get("certmanager")
    clusterconfig_namespace = namespaces.get("usage_system")
    ssc_namespace = namespaces.get("ssc")

    monitor_path = path.join(BASE_ZIP_PATH, arc_namespace, OpsServiceType.azuremonitor.value)

    services = [OpsServiceType.certmanager.value] if certmanager_namespace else []
    for namespace_folder, monikers in [
        (clusterconfig_namespace, ["clusterconfig"]),
        (arc_namespace, services + ["arcagents"]),
        (certmanager_namespace, services),
    ]:
        if namespace_folder and path.join(BASE_ZIP_PATH, namespace_folder) in walk_result:
            # remove empty folders in level 1
            level_1 = walk_result.pop(path.join(BASE_ZIP_PATH, namespace_folder))

            if namespace_folder == arc_namespace and monitor_path in walk_result:
                monikers.append(OpsServiceType.azuremonitor.value)
            assert set(level_1["folders"]) == set(monikers), (
                f"Mismatch; folders: [{level_1['folders']}],"
                f"monikers: [{monikers}]"
            )
            assert not level_1["files"]

    if ssc_namespace:
        services = [OpsServiceType.certmanager.value] if certmanager_namespace else []
        if path.join(BASE_ZIP_PATH, ssc_namespace, OpsServiceType.secretstore.value) in walk_result:
            services += [OpsServiceType.secretstore.value]
        level_1 = walk_result.pop(path.join(BASE_ZIP_PATH, ssc_namespace))

        if certmanager_namespace:
            assert set(level_1["folders"]) == set(services), (
                f"Mismatch; folders: [{level_1['folders']}], "
                f"monikers: [{services}]"
            )
        else:
            assert level_1["folders"] == [OpsServiceType.secretstore.value], (
                f"Mismatch; folders: [{level_1['folders']}], "
                f"monikers: [{OpsServiceType.secretstore.value}]"
            )

    # note that the acstor and acs namespace should be the same value
    if (
        acstor_namespace
        or acs_namespace
        and path.join(BASE_ZIP_PATH, acstor_namespace or acs_namespace) in walk_result
    ):
        services = []
        level_1 = walk_result.pop(path.join(BASE_ZIP_PATH, acstor_namespace or acs_namespace))

        # Only add certmanager if the folder actually exists
        if certmanager_namespace and OpsServiceType.certmanager.value in level_1["folders"]:
            services.append(OpsServiceType.certmanager.value)
        if acs_namespace:
            services.append("arccontainerstorage")
        if (
            containerstorage_service
            and path.join(BASE_ZIP_PATH, acstor_namespace, containerstorage_service) in walk_result
        ):
            services.append(containerstorage_service)
        assert set(level_1["folders"]) == set(services), (
            f"Mismatch; folders: [{level_1['folders']}], "
            f"services [{services}]"
        )
        assert not level_1["files"]

    # remove empty folders in level 2
    if clusterconfig_namespace:
        level_2 = walk_result.pop(path.join(BASE_ZIP_PATH, clusterconfig_namespace, "clusterconfig"))
        assert level_2["folders"] == ["billing"], f"Mismatch; folders: [{level_2['folders']}]"
        assert not level_2["files"]
    if arc_namespace:
        level_2 = walk_result.pop(path.join(BASE_ZIP_PATH, arc_namespace, "arcagents"))
        assert level_2["folders"] == [agent[0] for agent in ARC_AGENTS], f"Mismatch; folders: [{level_2['folders']}]"
        assert not level_2["files"]


def _compare_support_bundle_names(
    prefixes: Union[str, List[str]],
    resource_type: str,
    bundle_names: str,
    pre_bundle_resources: dict,
    post_bundle_resources: dict,
):
    """
    Do the name comparison with some extra debug information.

    For extra names, will split into two groups:
    1. "accepted" names - has the correct prefix so will just log. In this case, we assume that the resource
    just got created and deleted in the timespan of pre - support - post
    2. "unaccepted" names - does NOT have the correct prefix so will error. In this case, the prefix is not valid
    so more investigation as to why this got captured will be needed.

    For missing names, try to get labels to help determine if labels are the reason.
    """
    if isinstance(prefixes, str):
        prefixes = [prefixes]

    extra_names, missing_names = find_extra_or_missing_names(
        result_names=bundle_names,
        pre_expected_names=pre_bundle_resources.keys(),
        post_expected_names=post_bundle_resources.keys(),
    )

    error_msg = []
    if extra_names:
        # split the extra names into accepted (has a valid prefix) vs unaccepted (does not have valid prefix)
        accepted_names = []
        unaccepted_names = []
        for name in extra_names:
            if any(name.startswith(prefix) for prefix in prefixes):
                accepted_names.append(name)
            else:
                unaccepted_names.append(name)

        if accepted_names:
            logger.warning(
                f"Extra {resource_type} names in the support bundle with the correct prefixes {prefixes}: "
                f"{', '.join(accepted_names)}"
            )
        if unaccepted_names:
            error_msg.append(f"Extra {resource_type} names in the support bundle: {', '.join(unaccepted_names)}")

    if missing_names:
        error_msg.append(f"Missing {resource_type} names in the support bundle: {', '.join(missing_names)}")
        # get the labels for the missing resource
        for name in missing_names:
            bundle_to_use = pre_bundle_resources
            if name not in bundle_to_use:
                bundle_to_use = post_bundle_resources
            labels = bundle_to_use[name]["metadata"]["labels"]
            label_txt = " \n\t".join([f"{ln}: {labels[ln]}" for ln in labels])
            error_msg.append(f"{name} has the following labels:\n\t{label_txt}")

    if error_msg:
        raise AssertionError("\n".join(error_msg))
