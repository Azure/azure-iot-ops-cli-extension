# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------
import json
import sys
from ast import literal_eval
from subprocess import run
from unittest import TestCase


def process_template(input_template_path: str, output_format: str = "json"):
    if output_format not in ["json", "python"]:
        raise ValueError(f"Unsupported output format: {output_format}")

    with open(input_template_path, "r") as content:
        data = json.load(content)

    if "parameters" in data:
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

    # TODO - @digimaun
    # if "outputs" in data:
    #     del data["outputs"]

    output_ext = "json" if output_format == "json" else "py"
    output_template_path = f"./optimized.{output_ext}"
    with open(output_template_path, "w") as write_file:
        if output_format == "json":
            write_file.write(json.dumps(data, indent=2))
        elif output_format == "python":
            write_file.write(str(data))
            write_file.close()
            run(f"black {output_template_path} --line-length=119 --target-version=py38", check=True)

    # Test serialized content
    with open(output_template_path, "r") as read_file:
        content = read_file.read()
        if output_format == "json":
            payload_to_integrate = json.loads(content)
        elif output_format == "python":
            payload_to_integrate = literal_eval(content)

    assert payload_to_integrate == data
    TestCase().assertDictEqual(data, payload_to_integrate)
    print("Expected data assertions passed!")


if __name__ == "__main__":
    len_argv = len(sys.argv)
    if len_argv < 2 or len_argv > 3:
        print("Usage: python template_optimizer.py <input path to template.json> [output file format (json,python)]")
        raise sys.exit(1)
    process_template(*sys.argv[1:])
    sys.exit(0)
