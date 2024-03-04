# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import sys
import json


def process_template(input_template_path: str, output_template_path: str = None):
    if not output_template_path:
        output_template_path = "./optimized.json"

    with open(input_template_path, "r") as content:
        data = json.load(content)

    for parameter in data["parameters"]:
        if "metadata" in data["parameters"][parameter]:
            if "description" in data["parameters"][parameter]["metadata"] and len(data["parameters"][parameter]["metadata"]) == 1:
                del data["parameters"][parameter]["metadata"]

    with open(output_template_path, "w") as write_file:
        json.dump(data, write_file, indent=2)


if __name__ == "__main__":
    len_argv = len(sys.argv)
    if len_argv < 2 or len_argv > 3:
        print("Usage: python template_optimizer.py <path to input template.json> [output directory]")
        raise sys.exit(1)

    process_template(*sys.argv[1:])
    sys.exit(0)
