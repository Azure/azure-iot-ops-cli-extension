# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from typing import Any, Dict, List, Optional, Union

from .base import (
    CheckManager,
    add_display_and_eval,
    check_post_deployment,
    check_pre_deployment,
    evaluate_pod_health,
    process_as_list,
    process_properties,
)

from rich.console import Console
from rich.padding import Padding

from ...common import CheckTaskStatus

from .common import (
    AIO_LNM_PREFIX,
    LNM_ALLOWLIST_PROPERTIES,
    LNM_IMAGE_PROPERTIES,
    LNM_REST_PROPERTIES,
    ResourceOutputDetailLevel,
)

from ..edge_api import (
    LNM_API_V1,
    LnmResourceKinds,
)


def check_lnm_deployment(
    console: Console,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    namespace: Optional[str] = None,
    pre_deployment: bool = True,
    post_deployment: bool = True,
    as_list: bool = False,
    resource_kinds: List[str] = None,
    result: Dict[str, Any] = None,
) -> Union[Dict[str, Any], None]:
    if pre_deployment:
        check_pre_deployment(result, as_list)

    if post_deployment:
        if not namespace:
            from ..base import DEFAULT_NAMESPACE

            namespace = DEFAULT_NAMESPACE
        result["postDeployment"] = []

        # check post deployment according to edge_service type
        check_lnm_post_deployment(detail_level=detail_level, namespace=namespace, result=result, as_list=as_list, resource_kinds=resource_kinds)

    if not as_list:
        return result

    return process_as_list(console=console, result=result, namespace=namespace)


def check_lnm_post_deployment(
    namespace: str,
    result: Dict[str, Any],
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
    resource_kinds: List[str] = None
) -> None:
    evaluate_funcs = {
        LnmResourceKinds.LNM: evaluate_lnms,
    }

    return check_post_deployment(
        api_info=LNM_API_V1,
        check_name="enumerateLnmApi",
        check_desc="Enumerate Lnm API resources",
        namespace=namespace,
        result=result,
        resource_kinds_enum=LnmResourceKinds,
        evaluate_funcs=evaluate_funcs,
        as_list=as_list,
        detail_level=detail_level,
        resource_kinds=resource_kinds
    )


def evaluate_lnms(
    namespace: str,
    as_list: bool = False,
    detail_level: int = ResourceOutputDetailLevel.summary.value,
) -> Dict[str, Any]:
    check_manager = CheckManager(check_name="evalLnms", check_desc="Evaluate Lnm instance", namespace=namespace)

    target_lnms = "lnmz.aio.com"
    lnm_conditions = ["len(lnms)>=1", "status.configStatusLevel", "spec.allowList", "spec.image"]
    check_manager.add_target(target_name=target_lnms, conditions=lnm_conditions)

    lnm_list: dict = LNM_API_V1.get_resources(LnmResourceKinds.LNM, namespace=namespace)
    if not lnm_list:
        fetch_lnms_error_text = f"Unable to fetch namespace {LnmResourceKinds.LNM.value}s."
        check_manager.add_target_eval(
            target_name=target_lnms, status=CheckTaskStatus.error.value, value=fetch_lnms_error_text
        )
        check_manager.add_display(target_name=target_lnms, display=Padding(fetch_lnms_error_text, (0, 0, 0, 8)))
        return check_manager.as_dict(as_list)

    lnms: List[dict] = lnm_list.get("items", [])
    lnms_count = len(lnms)
    lnms_count_text = "- Expecting [bright_blue]>=1[/bright_blue] instance resource per namespace. {}."

    if lnms_count >= 1:
        lnms_count_text = lnms_count_text.format(f"[green]Detected {lnms_count}[/green]")
    else:
        lnms_count_text = lnms_count_text.format(f"[red]Detected {lnms_count}[/red]")
        check_manager.set_target_status(target_name=target_lnms, status=CheckTaskStatus.error.value)
    check_manager.add_display(target_name=target_lnms, display=Padding(lnms_count_text, (0, 0, 0, 8)))

    lnm_names = []

    for lnm in lnms:
        lnm_name = lnm["metadata"]["name"]
        lnm_names.append(lnm_name)
        status = lnm.get("status", {}).get("configStatusLevel", "undefined")

        lnm_status_eval_value = {"status.configStatusLevel": status}
        lnm_status_eval_status = CheckTaskStatus.success.value

        lnm_status_text = (
            f"- Lnm instance {{[bright_blue]{lnm_name}[/bright_blue]}} detected. Configuration status "
        )

        if lnm_name == "level6":
            import pdb; pdb.set_trace()

        if status == "ok":
            lnm_status_text = lnm_status_text + f"{{[green]{status}[/green]}}."
        else:
            lnm_status_eval_status = CheckTaskStatus.warning.value
            status_description = lnm.get("status", {}).get("configStatusDescription", "")
            lnm_status_text = lnm_status_text + f"{{[yellow]{status}[/yellow]}}. [yellow]{status_description}[/yellow]"

        add_display_and_eval(
            check_manager=check_manager,
            target_name=target_lnms,
            display_text=lnm_status_text,
            eval_status=lnm_status_eval_status,
            eval_value=lnm_status_eval_value,
            resource_name=lnm_name,
            padding=(0, 0, 0, 12)
        )

        lnm_allowlist = lnm["spec"].get("allowList", None)

        if detail_level > ResourceOutputDetailLevel.summary.value:

            lnm_allowlist_text = (
                "- Allow List property [green]detected[/green]."
            )

            lnm_allowlist_eval_value = {"spec.allowlist": lnm_allowlist}
            lnm_allowlist_eval_status = CheckTaskStatus.success.value

            if lnm_allowlist is None:
                lnm_allowlist_text = (
                    "- Allow List property [red]not detected[/red]."
                )

            add_display_and_eval(
                check_manager=check_manager,
                target_name=target_lnms,
                display_text=lnm_allowlist_text,
                eval_status=lnm_allowlist_eval_status,
                eval_value=lnm_allowlist_eval_value,
                resource_name=lnm_name,
                padding=(0, 0, 0, 16)
            )

            process_properties(
                check_manager=check_manager,
                detail_level=detail_level,
                target_name=target_lnms,
                prop_value=lnm_allowlist,
                properties=LNM_ALLOWLIST_PROPERTIES,
                padding=(0, 0, 0, 18)
            )

            process_properties(
                check_manager=check_manager,
                detail_level=detail_level,
                target_name=target_lnms,
                prop_value=lnm["spec"],
                properties=LNM_REST_PROPERTIES,
                padding=(0, 0, 0, 16)
            )

        if detail_level == ResourceOutputDetailLevel.verbose.value:
            # image
            lnm_image = lnm["spec"].get("image", None)
            lnm_image_text = (
                "- Image property [green]detected[/green]."
            )

            lnm_image_eval_value = {"spec.image": lnm_image}
            lnm_image_eval_status = CheckTaskStatus.success.value

            if lnm_image is None:
                lnm_image_text = (
                    "- Image property [red]not detected[/red]."
                )

            add_display_and_eval(
                check_manager=check_manager,
                target_name=target_lnms,
                display_text=lnm_image_text,
                eval_status=lnm_image_eval_status,
                eval_value=lnm_image_eval_value,
                resource_name=lnm_name,
                padding=(0, 0, 0, 16)
            )

            process_properties(
                check_manager=check_manager,
                detail_level=detail_level,
                target_name=target_lnms,
                prop_value=lnm_image,
                properties=LNM_IMAGE_PROPERTIES,
                padding=(0, 0, 0, 18)
            )

    if lnms_count > 0:
        check_manager.add_display(
            target_name=target_lnms,
            display=Padding(
                "\nRuntime Health",
                (0, 0, 0, 8),
            ),
        )

        from ..support.lnm import LNM_APP_LABELS

        # append all lnm_names in LNM_LABEL
        lnm_app_lables = LNM_APP_LABELS
        for lnm_name in lnm_names:
            LNM_APP_LABELS.append(f"aio-lnm-{lnm_name}")

        lnm_label = f"app in ({','.join(lnm_app_lables)})"

        for pod in [
            AIO_LNM_PREFIX
        ]:
            evaluate_pod_health(
                check_manager=check_manager,
                namespace=namespace,
                pod=pod,
                display_padding=12,
                service_label=lnm_label
            )

    return check_manager.as_dict(as_list)
