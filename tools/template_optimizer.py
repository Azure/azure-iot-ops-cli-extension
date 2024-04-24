# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------
import sys
import json
from subprocess import run


def process_template(input_template_path: str, output_template_path: str = None):
    if not output_template_path:
        output_template_path = "./optimized.py"

    with open(input_template_path, "r") as content:
        data = json.load(content)

    for parameter in data["parameters"]:
        if "metadata" in data["parameters"][parameter]:
            if (
                "description" in data["parameters"][parameter]["metadata"]
                and len(data["parameters"][parameter]["metadata"]) == 1
            ):
                del data["parameters"][parameter]["metadata"]

        if parameter in ["clusterLocation", "location"]:
            if "allowedValues" in data["parameters"][parameter]:
                del data["parameters"][parameter]["allowedValues"]

    with open(output_template_path, "w") as write_file:
        write_file.write(str(data))

    run(f"black {output_template_path} --line-length=119 --target-version=py38", check=True)


if __name__ == "__main__":
    len_argv = len(sys.argv)
    if len_argv < 2 or len_argv > 3:
        print("Usage: python template_optimizer.py <path to input template.json> [output directory]")
        raise sys.exit(1)
    process_template(*sys.argv[1:])
    sys.exit(0)
