from typing import Optional

from azure.cli.core.azclierror import ValidationError

from azext_edge.edge.providers.check.base.deployment import check_pre_deployment
from azext_edge.edge.providers.check.common import NON_ERROR_STATUSES


def validate_cluster_prechecks(acs_config: Optional[dict] = None) -> None:
    pre_checks = check_pre_deployment(acs_config=acs_config)
    errors = []
    for check in pre_checks:
        if check["status"] not in NON_ERROR_STATUSES:
            for target in check["targets"]:
                # for all prechecks, namespace is currently _all_
                for namespace in check["targets"][target]:
                    # this is a specific target (e.g. "cluster/nodes/k3d-k3s-default-server-0")
                    for idx, check_eval in enumerate(check["targets"][target][namespace]["evaluations"]):
                        if check_eval["status"] not in NON_ERROR_STATUSES:
                            # TODO - relies on same order and count of conditions / evaluations
                            expected_condition = check["targets"][target][namespace]["conditions"][idx]
                            # TODO - formatting
                            errors.append(
                                f"Target '{target}' failed condition:\n"
                                f"\tExpected: '{expected_condition}', Actual: '{check_eval['value']}'"
                            )

    if errors:
        raise ValidationError("Cluster readiness pre-checks failed:\n\n" + "\n".join(errors))
