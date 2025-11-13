# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------
import os
from json import dumps
from yaml import safe_load

# Known fields in test scenario object
KNOWN_FIELDS = {
    "name",
    "description",
    "tox_env",
    "needs_trust",
    "init_args",
    "create_args",
    "test_redeploy",
    "env",
}


def process_scenarios(scenarios: list[dict], user_selected: str) -> list[dict]:
    custom_scenarios = [item.strip() for item in user_selected.split(",") if item.strip()]

    processed_scenarios: list[dict] = []
    for scenario in scenarios:
        name = scenario["name"]

        # If user provided test selection, match on those
        if custom_scenarios:
            include = name in custom_scenarios
        # By default, do not include `custom` scenario
        else:
            include = name != "custom"

        # Skip scenario if not included
        if not include:
            continue

        # Warn if unknown fields present
        unknown = set(scenario.keys()) - KNOWN_FIELDS
        if unknown:
            fields = ", ".join(sorted(unknown))
            print(
                "::warning file=.github/test-scenarios.yml::"
                f"Scenario '{name}' contains unknown fields: {fields}",
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
        }

        processed_scenarios.append(normalized)

    return processed_scenarios


def main() -> None:
    config_path = os.getenv("TEST_SCENARIO_FILE", ".github/test-scenarios.yml")
    custom_scenarios = os.getenv("TEST_SCENARIOS", "")

    # Load TEST_SCENARIO_FILE
    with open(config_path, "r", encoding="utf-8") as f:
        config = safe_load(f) or {}

    # Filter based on user input
    test_scenarios = process_scenarios(config.get("scenarios", []), custom_scenarios)

    # Convert to JSON
    matrix_json = dumps(test_scenarios)
    print(f"Matrix: {matrix_json}")

    # Write to github action output
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        raise RuntimeError("GITHUB_OUTPUT environment variable is not set")

    with open(output_path, "a", encoding="utf-8") as out:
        out.write(f"scenarios={matrix_json}\n")


if __name__ == "__main__":
    main()
