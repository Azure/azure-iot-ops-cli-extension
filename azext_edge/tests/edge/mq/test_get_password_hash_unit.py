# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

import re

from azext_edge.edge.commands_mq import get_password_hash

from ...generators import generate_random_string


def test_get_password_hash():
    passphrase = generate_random_string()
    hash_result = get_password_hash(cmd=None, passphrase=passphrase)
    assert_hash_map(hash_map=hash_result)

    passphrase = generate_random_string()
    iterations = 500000
    hash_result = get_password_hash(cmd=None, passphrase=passphrase, iterations=iterations)
    assert_hash_map(hash_map=hash_result, iterations=iterations)


def assert_hash_map(hash_map: dict, iterations: int = None):
    assert "hash" in hash_map
    i = iterations or 210000
    match = re.fullmatch(
        pattern=rf"\$pbkdf2-sha512\$i={i},l=64\$([a-zA-Z0-9+/]+)\$([a-zA-Z0-9+/]+)", string=hash_map["hash"]
    )
    assert match
