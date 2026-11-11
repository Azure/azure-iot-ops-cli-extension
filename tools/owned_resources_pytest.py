# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Apply attempt ownership to released test helpers, not installed product bytes."""

import hashlib
import importlib
import os
import random
import string
import sys
from uuid import uuid4


class NamePhase:
    def __init__(self):
        self.collecting = True

    def pytest_collection_finish(self):
        self.collecting = False


def pytest_configure(config):
    owned = importlib.import_module("azext_edge.tests._owned_resources")
    journal = owned.activate(os.environ[owned.ENV])
    observer = owned.Observer(journal, owned.Arm(journal))
    observer.install()
    config.add_cleanup(observer.uninstall)
    generators = importlib.import_module("azext_edge.tests.generators")
    original = generators.generate_random_string
    collection = random.Random(int(journal.owner, 16))
    phase = NamePhase()
    config.pluginmanager.register(phase, "owned-resource-name-phase")

    def generate_name(size=36, force_lower=False):
        alphabet = string.ascii_lowercase + string.digits
        if not force_lower:
            alphabet += string.ascii_uppercase
        if phase.collecting:
            return "".join(collection.choice(alphabet) for _ in range(size))
        entropy = hashlib.shake_256(f"{journal.owner}:{uuid4().hex}".encode()).digest(max(0, size))
        return "".join(alphabet[value % len(alphabet)] for value in entropy)

    # Initial conftests can import aliases before pytest_configure runs.
    for name, module in tuple(sys.modules.items()):
        if name.startswith("azext_edge.tests") and module is not None:
            for attribute, value in tuple(vars(module).items()):
                if value is original:
                    setattr(module, attribute, generate_name)

    def restore():
        for name, module in tuple(sys.modules.items()):
            if name.startswith("azext_edge.tests") and module is not None:
                for attribute, value in tuple(vars(module).items()):
                    if value is generate_name:
                        setattr(module, attribute, original)

    config.add_cleanup(restore)
