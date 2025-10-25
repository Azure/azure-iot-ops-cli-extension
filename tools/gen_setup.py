# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        print("Error: For Python < 3.11, install 'tomli' package: pip install tomli")
        sys.exit(1)


def generate_setup_py():
    """Generate a minimal setup.py from pyproject.toml for SBOM generation."""

    project_root = Path(__file__).parent.parent
    pyproject_path = project_root / "pyproject.toml"

    if not pyproject_path.exists():
        print(f"Error: Could not find pyproject.toml at {pyproject_path}")
        sys.exit(1)

    with open(pyproject_path, "rb") as f:
        pyproject = tomllib.load(f)

    project = pyproject.get("project", {})
    dependencies = project.get("dependencies", [])

    # Create minimal setup.py content
    setup_content = """# AUTO-GENERATED FILE FOR SBOM TOOL - DO NOT COMMIT
from setuptools import setup, find_packages

setup(
    name="azure-iot-ops",
    packages=find_packages(include=["azext_edge", "azext_edge.*"]),
    install_requires=[
"""

    for dep in dependencies:
        setup_content += f'        "{dep}",\n'

    setup_content += """    ],
)
"""

    setup_path = project_root / "setup.py"
    with open(setup_path, "w") as f:
        f.write(setup_content)

    print(f"✓ Generated temporary setup.py at {setup_path}")

    return setup_path


if __name__ == "__main__":
    generate_setup_py()
