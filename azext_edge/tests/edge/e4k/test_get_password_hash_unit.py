# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# PRIVATE DISTRIBUTION FOR NDA CUSTOMERS ONLY
# --------------------------------------------------------------------------------------------

import re

from azext_edge.edge.commands_e4k import get_password_hash

from ...generators import generate_generic_id


def test_get_password_hash():
    passphrase = generate_generic_id()
    hash_result = get_password_hash(cmd=None, passphrase=passphrase)
    assert_hash_map(hash_map=hash_result)

    passphrase = generate_generic_id()
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
