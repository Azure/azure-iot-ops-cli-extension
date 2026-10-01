# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------
import os
import sys
import json
import re
import shlex
from copy import deepcopy
from json import dumps
from urllib.parse import urlsplit

from yaml import safe_load

# These are fields we expect in test scenario object, used for warnings if unknown fields are added
KNOWN_FIELDS = {
    "name",  # Scenario name key
    "description",  # Test description, title for workflow job
    "tox_env",  # Tox environment to run
    "needs_trust",  # Whether the scenario requires workload identity trust setup
    "init_args",  # Extra args for 'ops init' command
    "create_args",  # Extra args for 'ops create' command
    "test_redeploy",  # Whether to test redeployment in the scenario
    "env",  # Custom environment variable dict for the scenario
    "parallel",  # Controls parallel execution in pytest-xdist
    "requires_baseline",  # Opt-in real upgrade, rather than same-version reconciliation
}


def process_scenarios(scenarios: list[dict], user_selected: str) -> list[dict]:
    """
    Process and normalize test scenarios from configuration.
    Args:
        scenarios: List of raw scenario dictionaries from configuration.
        user_selected: Comma-separated string of user-selected scenario names to include.
    Returns:
        List of processed and normalized scenario dictionaries.
    """
    selected_scenarios = [item.strip() for item in user_selected.split(",") if item.strip()]

    # Validate provided scenarios exist in configuration
    if selected_scenarios:
        available_scenarios = {scenario["name"] for scenario in scenarios}
        invalid_scenarios = set(selected_scenarios) - available_scenarios
        if invalid_scenarios:
            invalid_list = ", ".join(sorted(invalid_scenarios))
            available_list = ", ".join(sorted(available_scenarios))
            print(
                "::warning file=.github/test-scenarios.yml::"
                f"Invalid scenario names specified: {invalid_list}. "
                f"Available scenarios: {available_list}",
            )

    processed_scenarios: list[dict] = []
    for scenario in scenarios:
        name = scenario["name"]

        # If user provided test selection, only include matching scenarios
        if selected_scenarios and name not in selected_scenarios:
            continue
        if not selected_scenarios and scenario.get("requires_baseline"):
            continue

        # Warn if unknown fields present
        unknown = set(scenario.keys()) - KNOWN_FIELDS
        if unknown:
            fields = ", ".join(sorted(unknown))
            print(
                "::warning file=.github/test-scenarios.yml::"
                f"Scenario '{name}' contains unknown fields that not be used: {fields}",
            )

        # Parse scenario custom environment variables
        raw_env = scenario.get("env", [])
        formatted_env = []
        for entry in raw_env:
            key, value = next(iter(entry.items()))
            formatted_env.append({"name": str(key), "value": str(value)})

        # Create full scenario object
        normalized = {
            "name": name,
            "description": scenario.get("description") or name,
            "tox_env": scenario.get("tox_env", ""),
            "needs_trust": bool(scenario.get("needs_trust", False)),
            "init_args": scenario.get("init_args", ""),
            "create_args": scenario.get("create_args", ""),
            "test_redeploy": bool(scenario.get("test_redeploy", False)),
            "env": formatted_env,
            "parallel": bool(scenario.get("parallel", True)),
            "requires_baseline": bool(scenario.get("requires_baseline", False)),
        }

        processed_scenarios.append(normalized)

    return processed_scenarios


def validate_baseline(baseline: dict) -> None:
    required = {"wheel_url", "sha256", "version", "train", "create_args"}
    if not isinstance(baseline, dict) or set(baseline) != required:
        raise ValueError(f"Upgrade baseline must contain exactly: {', '.join(sorted(required))}.")
    if any(not isinstance(value, str) for value in baseline.values()):
        raise ValueError("Upgrade baseline values must be strings.")
    url = urlsplit(baseline["wheel_url"])
    if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError("Baseline wheel URL must be credential-free HTTPS (no query string or fragment).")
    if not url.path.endswith(".whl") or not re.fullmatch(r"[a-fA-F0-9]{64}", baseline["sha256"]):
        raise ValueError("Baseline must identify a wheel and its SHA256 digest.")
    if not baseline["version"] or baseline["train"] not in {"stable", "preview", "integration"}:
        raise ValueError("Baseline requires an explicit version and deployment train.")


def expand_channels(scenarios, channels="stable,preview", baselines=None, init_args="", create_args=""):
    """Each row is an independent cluster; never convert an existing runtime's channel."""
    selected = list(dict.fromkeys(channel.strip() for channel in channels.split(",") if channel.strip()))
    if not selected or set(selected) - {"stable", "preview"}:
        raise ValueError("runtime-channels must contain stable and/or preview.")
    baselines = baselines or {}
    if not isinstance(baselines, dict) or set(baselines) - {"stable", "preview"}:
        raise ValueError("upgrade-baselines must be an object keyed by stable and/or preview.")
    rows = []
    for scenario in scenarios:
        # The channel matrix owns these flags. Arbitrary overrides would make a
        # labelled GA job silently deploy preview, or test a different target.
        for arguments in (scenario["init_args"], scenario["create_args"], init_args, create_args):
            options = {arg.split("=", 1)[0] for arg in shlex.split(arguments)}
            if options & {"--use-preview", "--ops-version", "--ops-train"}:
                raise ValueError("Runtime selection belongs to runtime-channels / upgrade-baselines, not extra args.")
        for channel in selected:
            row = deepcopy(scenario)
            row["name"] = f"{scenario['name']}-{channel}"
            row["description"] = f"{scenario['description']} [{channel}]"
            row["channel"] = channel
            row["init_args"] = f"{scenario['init_args']} {init_args}".strip()
            selector = "--use-preview --yes" if channel == "preview" else ""
            row["create_args"] = f"{scenario['create_args']} {create_args} {selector}".strip()
            row["baseline"] = None
            if row["requires_baseline"]:
                if channel not in baselines:
                    raise ValueError(f"Scenario {scenario['name']} requires an explicit {channel} upgrade baseline.")
                validate_baseline(baselines[channel])
                row["baseline"] = baselines[channel]
            rows.append(row)
    return rows


def main() -> None:
    """
    Helper utility to build test scenario matrix for GitHub Actions.
    Uses the following environment variables:
    - TEST_SCENARIO_FILE: Path to YAML file with test scenarios (default: .github/test-scenarios.yml)
    - TEST_SCENARIOS: Comma-separated override string of scenario names to run (default: empty/all)
    Outputs the resulting matrix as JSON to GITHUB_OUTPUT for pipeline use or stdout for local testing.
    """
    config_path = os.getenv("TEST_SCENARIO_FILE", ".github/test-scenarios.yml")
    custom_scenarios = os.getenv("TEST_SCENARIOS", "")

    # Load TEST_SCENARIO_FILE
    with open(config_path, "r", encoding="utf-8") as f:
        config = safe_load(f) or {}
    config_scenarios = config.get("scenarios", [])

    # Filter based on user input
    test_scenarios = expand_channels(
        process_scenarios(config_scenarios, custom_scenarios),
        channels=os.getenv("RUNTIME_CHANNELS", "stable,preview"),
        baselines=json.loads(os.getenv("UPGRADE_BASELINES", "{}")),
        init_args=os.getenv("RUNTIME_INIT_ARGS", ""),
        create_args=os.getenv("RUNTIME_CREATE_ARGS", ""),
    )

    # Exit if no valid scenarios
    if not test_scenarios:
        print("::error::No valid scenarios to run. Validate scenario input and configuration file.")
        print(f"Config file path: {config_path}")
        print(f"Available scenarios: {[s.get('name') for s in config_scenarios]}")
        print(f"Provided scenarios: {custom_scenarios}")
        sys.exit(1)

    # Convert to JSON
    print(f"Matrix:\n{dumps(test_scenarios, indent=2)}")
    matrix_json = dumps(test_scenarios)

    # Write to github action output or stdout
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as out:
            out.write(f"scenarios={matrix_json}\n")
    else:
        sys.stdout.write(f"scenarios={matrix_json}\n")


if __name__ == "__main__":
    main()
