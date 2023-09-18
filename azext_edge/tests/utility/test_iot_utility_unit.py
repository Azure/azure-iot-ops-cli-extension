# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------

import json
import os
import pytest
from knack.util import CLIError
from azure.cli.core.azclierror import CLIInternalError
from ...common.embedded_cli import EmbeddedCLI


class TestCliInit(object):
    def test_package_init(self):
        from azext_edge.constants import EXTENSION_ROOT

        tests_root = "tests"
        directory_structure = {}

        def _validate_directory(path):
            for entry in os.scandir(path):
                if entry.is_dir(follow_symlinks=False) and all(
                    [not entry.name.startswith("__"), tests_root not in entry.path]
                ):
                    directory_structure[entry.path] = None
                    _validate_directory(entry.path)
                else:
                    if entry.path.endswith("__init__.py"):
                        directory_structure[os.path.dirname(entry.path)] = entry.path

        _validate_directory(EXTENSION_ROOT)

        invalid_directories = []
        for directory in directory_structure:
            if directory_structure[directory] is None:
                invalid_directories.append("Directory: '{}' missing __init__.py".format(directory))

        if invalid_directories:
            pytest.fail(", ".join(invalid_directories))


class TestFileHeaders(object):
    def test_file_headers(self):
        from azext_edge.constants import EXTENSION_ROOT

        header = """# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Private distribution for NDA customers only. Governed by license terms at https://preview.e4k.dev/docs/use-terms/
# --------------------------------------------------------------------------------------------"""

        files_missing_header = []
        sdk_root = "sdk"

        def _validate_directory(path):
            for entry in os.scandir(path):
                if entry.is_dir(follow_symlinks=False) and sdk_root not in entry.path:
                    _validate_directory(entry.path)
                else:
                    if entry.is_file() and entry.path.endswith(".py"):
                        contents = None
                        with open(entry.path, "rt", encoding="utf-8") as f:
                            contents = f.read()
                        if contents and not contents.startswith(header):
                            files_missing_header.append(entry.path)

        _validate_directory(EXTENSION_ROOT)
        if files_missing_header:
            pytest.fail(
                "The following files are missing an encoding and license header, or it is improperly formatted:\n"
                "{}".format("\n".join(files_missing_header))
            )


class TestEmbeddedCli(object):
    @pytest.fixture(params=[0, 1, 2])
    def mocked_azclient(self, mocker, request):
        azclient = mocker.patch("azext_iot.common.embedded_cli.get_default_cli")

        def mock_invoke(args, out_file):
            azclient.return_value.exception_handler("Generic Issue")
            azclient.return_value.result.error = None
            if request.param == 0:
                out_file.write(json.dumps({"generickey": "genericvalue"}))
            else:
                out_file.write("Something not json")
                if request.param == 1:
                    azclient.return_value.result.error = CLIError("Generic Error")

            return request.param

        azclient.return_value.invoke.side_effect = mock_invoke
        azclient.test_meta.error_code = request.param
        return azclient

    @pytest.mark.parametrize("command", [
        "iot hub device-identity create -n abcd -d dcba",
        "iot hub device-twin show -n 'abcd' -d 'dcba'"
    ])
    @pytest.mark.parametrize("user_subscription", [None, "20a300e5-a444-4130-bb5a-1abd08ad930a"])
    @pytest.mark.parametrize("subscription", [None, "40a300e5-4130-a444-bb5a-1abd08ad930a"])
    @pytest.mark.parametrize("init_capture_stderr", [True, False])
    @pytest.mark.parametrize("capture_stderr", [None, True, False])
    def test_embedded_cli(
        self, mocker, mocked_azclient, command, user_subscription, subscription, init_capture_stderr, capture_stderr
    ):
        import shlex

        cli_ctx = mocker.MagicMock()
        cli_ctx.data = {}
        if user_subscription:
            cli_ctx.data["subscription_id"] = user_subscription

        expected_count = 0 if (capture_stderr is None and init_capture_stderr) or capture_stderr else 1
        cli = EmbeddedCLI(cli_ctx, capture_stderr=init_capture_stderr)

        if mocked_azclient.test_meta.error_code != 1 or expected_count == 1:
            cli.invoke(command=command, subscription=subscription, capture_stderr=capture_stderr)
        else:
            with pytest.raises(CLIError) as e:
                cli.invoke(command=command, subscription=subscription, capture_stderr=capture_stderr)
            assert "Generic Error" in str(e.value)

        assert cli.az_cli.exception_handler.call_count == expected_count

        # Due to forced json output
        command += " -o json"

        if subscription:
            command += " --subscription '{}'".format(subscription)
        elif user_subscription:
            command += " --subscription '{}'".format(user_subscription)

        expected_args = shlex.split(command)
        call = mocked_azclient().invoke.call_args_list[0]
        actual_args, _ = call
        assert expected_args == actual_args[0]
        assert cli.output
        success = cli.success()
        if mocked_azclient.test_meta.error_code > 0:
            assert not success
            if mocked_azclient.test_meta.error_code == 2:
                with pytest.raises(CLIInternalError) as e:
                    cli.as_json()
                assert "Issue parsing received payload" in str(e.value)
        elif mocked_azclient.test_meta.error_code == 0:
            assert success
            assert cli.as_json()
