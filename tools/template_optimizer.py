# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------
import sys
import json
from subprocess import run


def process_template(input_template_path: str, output_format: str = "json"):
    if output_format not in ["json", "python"]:
        raise ValueError(f"Unsupported output format: {output_format}")

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

    output_ext = "json" if output_format == "json" else "py"
    output_template_path = f"./optimized.{output_ext}"
    with open(output_template_path, "w") as write_file:
        if output_format == "json":
            write_file.write(json.dumps(data, indent=2))
        elif output_format == "python":
            write_file.write(str(data))
            write_file.close()
            run(f"black {output_template_path} --line-length=119 --target-version=py38", check=True)
        else:
            raise ValueError("Unsupported output format.")


if __name__ == "__main__":
    len_argv = len(sys.argv)
    if len_argv < 2 or len_argv > 3:
        print("Usage: python template_optimizer.py <input path to template.json> [output file format (json,python)]")
        raise sys.exit(1)
    process_template(*sys.argv[1:])
    sys.exit(0)
