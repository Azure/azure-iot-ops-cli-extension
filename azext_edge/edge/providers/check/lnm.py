# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from typing import Any, Dict, List, Optional, Tuple, Union

from azext_edge.edge.providers.edge_api.lnm import LNM_API_V1, LnmResourceKinds
from .base import (
    CheckManager,
    decorate_resource_status,
    check_post_deployment,
    check_pre_deployment,
    evaluate_pod_health,
    process_as_list,
)

from rich.console import Console
from rich.padding import Padding
from rich.table import Table

from ...common import (
    CheckTaskStatus,
    ProvisioningState,
)

from .common import (
    AIO_LNM_PREFIX,
    ResourceOutputDetailLevel,
)

from ..edge_api import (
    BLUEFIN_API_V1,
    BluefinResourceKinds,
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
    lnm_conditions = ["len(lnms)>=1", "spec.allowList", "spec.image"]
    check_manager.add_target(target_name=target_lnms, conditions=lnm_conditions)

    lnm_list: dict = LNM_API_V1.get_resources(LnmResourceKinds.LNM, namespace=namespace, plural="lnmz")
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
    lnm_allowlist_table = Table(show_lines=True, expand=True)
    lnm_allowlist_table.add_column("Lnm name", justify="center", style="cyan", no_wrap=True, min_width=10)
    lnm_allowlist_table.add_column("Domains", justify="center", style="cyan", no_wrap=True, min_width=10)
    lnm_allowlist_table.add_column("EnableArcDomains", justify="center", style="cyan", no_wrap=True, min_width=10)
    lnm_allowlist_table.add_column("SourceIpRange", justify="center", style="cyan", no_wrap=True, min_width=10)

    lnm_image_table = Table(show_lines=True, expand=True)
    lnm_image_table.add_column("Lnm name", justify="center", style="cyan", no_wrap=True)
    lnm_image_table.add_column("PullPolicy", justify="center", style="cyan", no_wrap=True)
    lnm_image_table.add_column("pullSecrets", justify="center", style="cyan", no_wrap=True)
    lnm_image_table.add_column("repository", justify="center", style="cyan", no_wrap=True, width=20)
    lnm_image_table.add_column("tag", justify="center", style="cyan", no_wrap=True)

    for l in lnms:

        lnm_name = l["metadata"]["name"]
        lnm_names.append(lnm_name)

        if detail_level == ResourceOutputDetailLevel.summary.value:
            check_manager.add_display(
                target_name=target_lnms,
                display=Padding(
                    f"- Lnm instance {{[bright_blue]{lnm_name}[/bright_blue]}} detected",
                    (0, 0, 0, 12),
                ),
            )
        
        lnm_allowlist = l["spec"].get("allowList", None)

        # if detail_level == ResourceOutputDetailLevel.detail.value:
        #     is_allowlist_detected = True

        #     lnm_allowlist_eval_value = {"spec.allowList": lnm_allowlist}
        #     lnm_allowlist_eval_status = CheckTaskStatus.success.value

        #     if lnm_allowlist is None:
        #         is_allowlist_detected = False

        #     if is_allowlist_detected:
        #         domains_length = len(lnm_allowlist.get("domains", []))
        #         enableArcDomains = lnm_allowlist.get("enableArcDomains", "--")
        #         sourceIpRange_length = len(lnm_allowlist.get("sourceIpRange", []))

        #         lnm_allowlist_table.add_row(
        #             lnm_name,
        #             f"{domains_length} domain detected",
        #             str(enableArcDomains),
        #             f"{sourceIpRange_length} sourceIpRange detected"
        #         )
        #     # check_manager.add_display(
        #     #     target_name=target_lnms,
        #     #     display=Padding(
        #     #         lnm_allow_list_text,
        #     #         (0, 0, 0, 16),
        #     #     ),
        #     # )
        #     check_manager.add_target_eval(
        #         target_name=target_lnms, status=lnm_allowlist_eval_status, value=lnm_allowlist_eval_value, resource_name=lnm_name
        #     )

        #     lnm_image = l["spec"].get("image", None)
        #     is_image_detected = True

        #     lnm_image_eval_value = {"spec.image": lnm_image}
        #     lnm_image_eval_status = CheckTaskStatus.success.value

        #     if lnm_image is None:
        #         is_image_detected = False

        #     if is_image_detected:
        #         pullPolicy = lnm_image.get("pullPolicy", "--")
        #         pullSecrets = lnm_image.get("pullSecrets", "--")
        #         repository = lnm_image.get("repository", None)
        #         tag = lnm_image.get("tag", None)

        #         # if repository is None:
        #         # if tag is None:

        #         lnm_image_table.add_row(
        #             lnm_name,
        #             pullPolicy,
        #             pullSecrets,
        #             repository,
        #             tag
        #         )
            
        #     check_manager.add_target_eval(
        #         target_name=target_lnms, status=lnm_image_eval_status, value=lnm_image_eval_value, resource_name=lnm_name
        #     )

        if detail_level > ResourceOutputDetailLevel.summary.value:
            check_manager.add_display(
                target_name=target_lnms,
                display=Padding(
                    f"- Lnm instance {{[bright_blue]{lnm_name}[/bright_blue]}} detected",
                    (0, 0, 0, 12),
                ),
            )

            lnm_allowlist_text = (
                "- Allow List property [green]detected[/green]."
            )

            lnm_allowlist_eval_value = {"spec.allowlist": lnm_allowlist}
            lnm_allowlist_eval_status = CheckTaskStatus.success.value

            if lnm_allowlist is None:
                lnm_allowlist_text = (
                    "- Allow List property [red]not detected[/red]."
                )

            check_manager.add_display(
                target_name=target_lnms,
                display=Padding(
                    lnm_allowlist_text,
                    (0, 0, 0, 16),
                ),
            )
            check_manager.add_target_eval(
                target_name=target_lnms, status=lnm_allowlist_eval_status, value=lnm_allowlist_eval_value, resource_name=lnm_name
            )

            # domains
            lnm_allowlist_domains = lnm_allowlist.get("domains", None)
            if lnm_allowlist_domains:
                lnm_allowlist_domains_text = (
                    "[bright_blue]Domains[/bright_blue]"
                )

                check_manager.add_display(
                    target_name=target_lnms,
                    display=Padding(
                        lnm_allowlist_domains_text,
                        (0, 0, 0, 18),
                    ),
                )
                
                for domain in lnm_allowlist_domains:
                    destination_type = domain.get("destinationType", None)
                    destination_url = domain.get("destinationUrl", None)

                    lnm_domain_eval_value = {"spec.allowList.domains.item": domain}
                    lnm_domain_eval_status = CheckTaskStatus.success.value

                    if destination_type and destination_url:
                        check_manager.add_display(
                            target_name=target_lnms,
                            display=Padding(
                                f"- Destination type {{[bright_blue]{destination_type}[/bright_blue]}} with url {{[bright_blue]{destination_url}[/bright_blue]}}",
                                (0, 0, 0, 20),
                            ),
                        )
                    else:
                        lnm_domain_eval_status = CheckTaskStatus.error.value
                        check_manager.add_display(
                            target_name=target_lnms,
                            display=Padding(
                                "- Destination type or url [red]not detected[/red]",
                                (0, 0, 0, 20),
                            ),
                        )
                    check_manager.add_target_eval(
                        target_name=target_lnms, status=lnm_domain_eval_status, value=lnm_domain_eval_value, resource_name=lnm_name
                    )

            # enableArcDomains
            lnm_allowlist_enableArcDomains = lnm_allowlist.get("enableArcDomains", None)

            if lnm_allowlist_enableArcDomains:
                check_manager.add_display(
                    target_name=target_lnms,
                    display=Padding(
                        f"[bright_blue]Enable Arc Domains[/bright_blue]: {{[bright_blue]{lnm_allowlist_enableArcDomains}[/bright_blue]}}",
                        (0, 0, 0, 18),
                    ),
                )
            
            # source IP range
            lnm_allowlist_ip_range = lnm_allowlist.get("sourceIpRange", None)
            if lnm_allowlist_ip_range:
                lnm_allowlist_ip_range_text = (
                    "[bright_blue]Source IP Range[/bright_blue]"
                )

                check_manager.add_display(
                    target_name=target_lnms,
                    display=Padding(
                        lnm_allowlist_ip_range_text,
                        (0, 0, 0, 18),
                    ),
                )
                
                for ip_range in lnm_allowlist_ip_range:
                    address_prefix = ip_range.get("addressPrefix", None)
                    prefix_len = ip_range.get("prefixLen", None)

                    lnm_ip_range_eval_value = {"spec.allowList.sourceIpRange.item": domain}
                    lnm_ip_range_eval_status = CheckTaskStatus.success.value

                    if address_prefix != None and prefix_len != None:
                        check_manager.add_display(
                            target_name=target_lnms,
                            display=Padding(
                                f"- Address prefix {{[bright_blue]{address_prefix}[/bright_blue]}} with length {{[bright_blue]{prefix_len}[/bright_blue]}}",
                                (0, 0, 0, 20),
                            ),
                        )
                    else:
                        lnm_ip_range_eval_status = CheckTaskStatus.error.value
                        check_manager.add_display(
                            target_name=target_lnms,
                            display=Padding(
                                "- Address prefix or length [red]not detected[/red]",
                                (0, 0, 0, 20),
                            ),
                        )
                    check_manager.add_target_eval(
                        target_name=target_lnms, status=lnm_ip_range_eval_status, value=lnm_ip_range_eval_value, resource_name=lnm_name
                    )

        if detail_level == ResourceOutputDetailLevel.verbose.value:
            # image
            lnm_image = l["spec"].get("image", None)
            lnm_image_text = (
                "- Image property [green]detected[/green]."
            )

            lnm_image_eval_value = {"spec.image": lnm_image}
            lnm_image_eval_status = CheckTaskStatus.success.value

            if lnm_image is None:
                lnm_image_text = (
                    "- Image property [red]not detected[/red]."
                )

            check_manager.add_display(
                target_name=target_lnms,
                display=Padding(
                    lnm_image_text,
                    (0, 0, 0, 16),
                ),
            )
            check_manager.add_target_eval(
                target_name=target_lnms, status=lnm_image_eval_status, value=lnm_image_eval_value, resource_name=lnm_name
            )

            # pullPolicy
            lnm_image_pullPolicy = lnm_image.get("pullPolicy", None)

            if lnm_image_pullPolicy:
                check_manager.add_display(
                    target_name=target_lnms,
                    display=Padding(
                        f"[bright_blue]Pull Policy[/bright_blue]: {{[bright_blue]{lnm_image_pullPolicy}[/bright_blue]}}",
                        (0, 0, 0, 18),
                    ),
                )
            
            # pullSecrets
            lnm_image_pullSecrets = lnm_image.get("pullSecrets", None)

            if lnm_image_pullSecrets:
                check_manager.add_display(
                    target_name=target_lnms,
                    display=Padding(
                        f"[bright_blue]Pull Secrets[/bright_blue]: {{[bright_blue]{lnm_image_pullSecrets}[/bright_blue]}}",
                        (0, 0, 0, 18),
                    ),
                )
            
            # repository
            lnm_image_repository = lnm_image.get("repository", None)

            if lnm_image_repository:
                check_manager.add_display(
                    target_name=target_lnms,
                    display=Padding(
                        f"[bright_blue]Repository[/bright_blue]: {{[bright_blue]{lnm_image_repository}[/bright_blue]}}",
                        (0, 0, 0, 18),
                    ),
                )
            
            # tag
            lnm_image_tag = lnm_image.get("tag", None)

            if lnm_image_tag:
                check_manager.add_display(
                    target_name=target_lnms,
                    display=Padding(
                        f"[bright_blue]Tag[/bright_blue]: {{[bright_blue]{lnm_image_tag}[/bright_blue]}}",
                        (0, 0, 0, 18),
                    ),
                )

    
    # if detail_level == ResourceOutputDetailLevel.detail.value:
    #     check_manager.add_display(
    #         target_name=target_lnms,
    #         display=Padding(
    #             "\nAllowList:",
    #             (0, 0, 0, 10),
    #         ),
    #     )
    #     check_manager.add_display(
    #         target_name=target_lnms,
    #         display=Padding(
    #             lnm_allowlist_table,
    #             (0, 0, 0, 12),
    #         ),
    #     )

    #     check_manager.add_display(
    #         target_name=target_lnms,
    #         display=Padding(
    #             "\nImage:",
    #             (0, 0, 0, 10),
    #         ),
    #     )
    #     check_manager.add_display(
    #         target_name=target_lnms,
    #         display=Padding(
    #             lnm_image_table,
    #             (0, 0, 0, 12),
    #         ),
    #     )

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
