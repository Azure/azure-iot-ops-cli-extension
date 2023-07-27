# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

from datetime import datetime
from time import sleep
from typing import Optional

from azure.cli.core.azclierror import ResourceNotFoundError
from knack.log import get_logger
from rich.console import Console

from ..common import METRICS_SERVICE_API_PORT, AZEDGE_DIAGNOSTICS_SERVICE
from .base import get_namespaced_pods_by_prefix, portforward_http

logger = get_logger(__name__)

console = Console(highlight=True)


def get_stats(
    namespace: Optional[str] = None,
    diag_service_pod_prefix: str = AZEDGE_DIAGNOSTICS_SERVICE,
    pod_port: int = METRICS_SERVICE_API_PORT,
    raw_response=False,
    raw_response_print=False,
    refresh_in_seconds: int = 10,
    watch: bool = False,
):
    if not namespace:
        from .base import DEFAULT_NAMESPACE

        namespace = DEFAULT_NAMESPACE

    target_pods = get_namespaced_pods_by_prefix(prefix=diag_service_pod_prefix, namespace=namespace)
    if not target_pods:
        raise ResourceNotFoundError(f"Diagnostics service does not exist in namespace {namespace}.")
    diagnostic_pod = target_pods[0]
    target_pod_port = pod_port

    from rich import box
    from rich.live import Live
    from rich.table import Table

    table = Table(box=box.MINIMAL_DOUBLE_HEAD)
    table.add_column("Stat")
    table.add_column("Value")
    table.add_column("Description")

    with portforward_http(
        namespace=namespace,
        pod_name=diagnostic_pod.metadata.name,
        pod_port=target_pod_port,
    ) as pf:
        try:
            raw_metrics = pf.get("/metrics")
            if raw_response:
                return raw_metrics
            elif raw_response_print:
                console.print(raw_metrics)
                return
            stats = dict(sorted(_clean_stats(raw_metrics).items()))
            if not watch:
                return stats
            logger.warning(f"Refreshing every {refresh_in_seconds} seconds. Use ctrl-c to terminate stats watch.\n")
            with Live(table, refresh_per_second=4, auto_refresh=False) as live:
                while True:
                    stats = dict(sorted(_clean_stats(raw_metrics).items()))
                    table = Table(
                        box=box.ROUNDED,
                        caption=f"Last refresh {datetime.now().isoformat()}",
                        highlight=True,
                        expand=False,
                        min_width=100,
                    )
                    table.add_column("Stat")
                    table.add_column("Value", min_width=10)
                    table.add_column("Description")
                    for s in stats:
                        table.add_row(
                            stats[s]["displayName"],
                            "[green]Pass[/green]"
                            if str(stats[s]["value"]) == "Pass"
                            else "[red]Fail[/red]"
                            if str(stats[s]["value"]) == "Fail"
                            else str(stats[s]["value"]),
                            stats[s]["description"],
                        )
                    live.update(table)
                    live.refresh()
                    sleep(refresh_in_seconds)
                    raw_metrics = pf.get("/metrics")
        except KeyboardInterrupt:
            return
        except Exception as e:
            if str(e).startswith("HTTPConnectionPool"):
                return
            logger.warning(f"Failure in stats processing\n\n{str(e)}")


def _clean_stats(raw_stats: str) -> dict:
    def _get_pass_fail(value: float) -> str:
        if value >= 1.0:
            return "Pass"
        else:
            return "Fail"

    result = {}
    test = raw_stats.split("\n")
    for line in test:
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        key = None
        value = None
        if "{" in line:
            t = line.split("{")
            key = t[0]
            if len(t) > 1:
                value = line.split("}")[-1]
                value = float(value.strip())
        else:
            t = line.split(" ")
            key = t[0]
            value = float(t[1].strip())

        if key not in result:
            result[key] = value
        else:
            if key == "publishes_received_per_second" or key == "publishes_sent_per_second":
                result[key] = result[key] + value
            elif key == "publish_route_replication_correctness":
                result[key] = result[key] * value
            else:
                result[key] = value

    if result:
        normalized = {}
        if "publish_route_replication_correctness" in result:
            normalized["publish_route_replication_correctness"] = {
                "displayName": "Replication Correctness",
                "description": "Replication correctness.",
                "value": _get_pass_fail(result["publish_route_replication_correctness"]),
            }
        if "publish_latency_mu_ms" in result:
            normalized["publish_latency_mu_ms"] = {
                "displayName": "P99 Average",
                "description": "Average 99th percentile of publish message latency (ms).",
                "value": round(result["publish_latency_mu_ms"], 5),
            }
        if "publish_latency_sigma_ms" in result:
            normalized["publish_latency_sigma_ms"] = {
                "displayName": "P99 Standard Deviation",
                "description": "Standard deviation of the 99th percentile publish message latency (ms).",
                "value": round(result["publish_latency_sigma_ms"], 5),
            }
        if "publishes_received_per_second" in result:
            normalized["publishes_received_per_second"] = {
                "displayName": "Inbound Message Rate",
                "description": "Rate of inbound messages per second.",
                "value": round(result["publishes_received_per_second"], 5),
            }
        if "publishes_sent_per_second" in result:
            normalized["publishes_sent_per_second"] = {
                "displayName": "Outbound Message Rate",
                "description": "Rate of outgoing messages per second.",
                "value": round(result["publishes_sent_per_second"], 5),
            }
        if "connected_sessions" in result:
            normalized["connected_sessions"] = {
                "displayName": "Connected Sessions",
                "description": "Total number of connected sessions.",
                "value": result["connected_sessions"],
            }
        if "total_subscriptions" in result:
            normalized["total_subscriptions"] = {
                "displayName": "Total Subscriptions",
                "description": "Total number of topic subscriptions.",
                "value": result["total_subscriptions"],
            }

        return normalized

    return result
