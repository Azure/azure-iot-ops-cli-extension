# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

class MockResponseRaw:
    def __init__(self, content: bytes):
        self.read_calls = 0
        self.content = content

    def read(self, chunk_size: int) -> bytes:
        _ = chunk_size
        if not self.read_calls:
            self.read_calls += 1
            return self.content
        return b""