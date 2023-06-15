# coding=utf-8
# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
utility: Defines common utility functions and components.

"""

import ast
import base64
import isodate
import json
import os
import sys
import re
import hmac
import hashlib
from typing import Any, Optional, List, Dict
from threading import Event, Thread
from datetime import datetime
from knack.log import get_logger
from azure.cli.core.azclierror import (
    CLIInternalError,
    FileOperationError,
    InvalidArgumentValueError,
)

logger = get_logger(__name__)



def validate_key_value_pairs(string):
    """
    Funtion to validate key-value pairs in the format: a=b;c=d

    Args:
        string (str): semicolon delimited string of key/value pairs.

    Returns (dict, None): a dictionary of key value pairs.
    """
    result = None
    if string:
        kv_list = [x for x in string.split(";") if "=" in x]  # key-value pairs
        result = dict(x.split("=", 1) for x in kv_list)
    return result


def process_json_arg(
    content: str, argument_name: str = "content", preserve_order=False
):
    """Primary processor of json input"""
    json_from_file = None

    if os.path.exists(content):
        json_from_file = content
        content = read_file_content(content)

    try:
        return shell_safe_json_parse(content, preserve_order)
    except CLIInternalError as ex:
        if looks_like_file(content):
            logger.warning(
                "The json payload for argument '%s' looks like its intended from a file. "
                "Please ensure the file path is correct.",
                argument_name,
            )

        file_content_error = "from file: '{}' ".format(json_from_file)
        raise CLIInternalError(
            "Failed to parse json {}for argument '{}' with exception:\n    {}".format(
                file_content_error if json_from_file else "", argument_name, ex
            )
        )


_file_location_error = "{0} file not found - Please ensure the path '{1}' is correct."
_file_parse_error = "Failed to parse {0} file located at '{1}' with exception:\n{2}"


def process_yaml_arg(path: str) -> Dict[str, Any]:
    """Primary processor of yaml file input"""

    if not os.path.exists(path):
        raise FileOperationError(
            _file_location_error.format("YAML", path)
        )

    try:
        import yaml

        with open(path, "rb") as f:
            return yaml.load(f, Loader=yaml.SafeLoader)
    except Exception as ex:
        raise InvalidArgumentValueError(
            _file_parse_error.format("YAML", path, ex)
        )


def process_toml_arg(path: str) -> Dict[str, Any]:
    """Primary processor of TOML file input"""

    if not os.path.exists(path):
        raise FileOperationError(
            _file_location_error.format("TOML", path)
        )

    try:
        import tomli

        with open(path, "rb") as f:
            return tomli.load(f)
    except Exception as ex:
        raise InvalidArgumentValueError(
            _file_parse_error.format("TOML", path, ex)
        )


def shell_safe_json_parse(json_or_dict_string, preserve_order=False):
    """Allows the passing of JSON or Python dictionary strings. This is needed because certain
    JSON strings in CMD shell are not received in main's argv. This allows the user to specify
    the alternative notation, which does not have this problem (but is technically not JSON)."""
    try:
        if not preserve_order:
            return json.loads(json_or_dict_string)
        from collections import OrderedDict

        return json.loads(json_or_dict_string, object_pairs_hook=OrderedDict)
    except ValueError as json_ex:
        try:
            return ast.literal_eval(json_or_dict_string)
        except SyntaxError:
            raise CLIInternalError(json_ex)
        except ValueError as ex:
            logger.debug(
                ex
            )  # log the exception which could be a python dict parsing error.
            raise CLIInternalError(
                json_ex
            )  # raise json_ex error which is more readable and likely.


def read_file_content(file_path, allow_binary=False):
    from codecs import open as codecs_open

    # Note, always put 'utf-8-sig' first, so that BOM in WinOS won't cause trouble.
    for encoding in ["utf-8-sig", "utf-8", "utf-16", "utf-16le", "utf-16be"]:
        try:
            with codecs_open(file_path, encoding=encoding) as f:
                logger.debug("Attempting to read file %s as %s", file_path, encoding)
                return f.read()
        except (UnicodeError, UnicodeDecodeError):
            pass

    if allow_binary:
        try:
            with open(file_path, "rb") as input_file:
                logger.debug("Attempting to read file %s as binary", file_path)
                return base64.b64encode(input_file.read()).decode("utf-8")
        except Exception:  # pylint: disable=broad-except
            pass
    raise FileOperationError(
        "Failed to decode file {} - unknown decoding".format(file_path)
    )


def trim_from_start(s, substring):
    """Trims a substring from the target string (if it exists) returning the trimmed string.
    Otherwise returns original target string."""
    if s.startswith(substring):
        s = s[len(substring) :]
    return s


def validate_min_python_version(major, minor, error_msg=None, exit_on_fail=True):
    """If python version does not match AT LEAST requested values, will throw non 0 exit code."""
    version = sys.version_info
    result = False
    if version.major > major:
        return True
    if major == version.major:
        result = version.minor >= minor

    if not result:
        if exit_on_fail:
            msg = (
                error_msg
                if error_msg
                else "Python version {}.{} or higher required for this functionality.".format(
                    major, minor
                )
            )
            sys.exit(msg)

    return result


def url_encode_dict(d):
    try:
        from urllib import urlencode
    except ImportError:
        from urllib.parse import urlencode

    return urlencode(d)


def url_encode_str(s, plus=False):
    try:
        if plus:
            from urllib import quote_plus
        else:
            from urllib import quote
    except ImportError:
        if plus:
            from urllib.parse import quote_plus
        else:
            from urllib.parse import quote

    return quote_plus(s) if plus else quote(s)


def test_import_and_version(package, expected_version):
    """
    Used to determine if a package dependency, installed with metadata,
    is at least the expected version. This utility will not work for packages
    that are installed without metadata.
    """

    from importlib import metadata

    try:
        return metadata.version(package) >= expected_version
    except metadata.PackageNotFoundError:
        return False


def unpack_msrest_error(e):
    """Obtains full response text from an msrest error"""
    from typing import Callable

    op_err = None
    try:
        err_txt = ""
        if isinstance(e.response.text, Callable):
            err_txt = e.response.text()
        else:
            err_txt = e.response.text
        op_err = json.loads(err_txt)
    except (ValueError, TypeError):
        op_err = err_txt
    if not op_err:
        return str(e)
    return op_err


def handle_service_exception(e):
    """
    Used to unpack service error messages and status codes,
    and raise the correct azclierror class.
    For more info on CLI error handling guidelines, see
    https://github.com/Azure/azure-cli/blob/dev/doc/error_handling_guidelines.md
    """
    from azure.cli.core.azclierror import (
        AzureInternalError,
        AzureResponseError,
        BadRequestError,
        ForbiddenError,
        ResourceNotFoundError,
        UnauthorizedError,
    )

    err = unpack_msrest_error(e)
    op_status = getattr(e.response, "status_code", -1)

    # Generic error if the status_code is explicitly None
    if not op_status:
        raise AzureResponseError(err)
    if op_status == 400:
        raise BadRequestError(err)
    if op_status == 401:
        raise UnauthorizedError(err)
    if op_status == 403:
        raise ForbiddenError(err)
    if op_status == 404:
        raise ResourceNotFoundError(err)
    # Any 5xx error should throw an AzureInternalError
    if 500 <= op_status < 600:
        raise AzureInternalError(err)
    # Otherwise, fail with generic service error
    raise AzureResponseError(err)


def dict_transform_lower_case_key(d):
    """Converts a dictionary to an identical one with all lower case keys"""
    return {k.lower(): v for k, v in d.items()}


def calculate_millisec_since_unix_epoch_utc(offset_seconds: int = 0):
    now = datetime.utcnow()
    epoch = datetime.utcfromtimestamp(0)
    return int(1000 * ((now - epoch).total_seconds() + offset_seconds))


def dict_clean(d):
    """Remove None from dictionary"""
    if not isinstance(d, dict):
        return d
    return dict((k, dict_clean(v)) for k, v in d.items() if v is not None)


def looks_like_file(element):
    element = element.lower()
    return element.endswith(
        (
            ".log",
            ".rtf",
            ".txt",
            ".json",
            ".yaml",
            ".yml",
            ".md",
            ".rst",
            ".doc",
            ".docx",
            ".html",
            ".htm",
            ".py",
            ".java",
            ".ts",
            ".js",
            ".cs",
        )
    )


class ISO8601Validator:
    def is_iso8601_date(self, to_validate) -> bool:
        try:
            return bool(isodate.parse_date(to_validate))
        except Exception:
            return False

    def is_iso8601_datetime(self, to_validate: str) -> bool:
        try:
            return bool(isodate.parse_datetime(to_validate))
        except Exception:
            return False

    def is_iso8601_duration(self, to_validate: str) -> bool:
        try:
            return bool(isodate.parse_duration(to_validate))
        except Exception:
            return False

    def is_iso8601_time(self, to_validate: str) -> bool:
        try:
            return bool(isodate.parse_time(to_validate))
        except Exception:
            return False


def scantree(path):
    for entry in os.scandir(path):
        if entry.is_dir(follow_symlinks=False):
            yield from scantree(entry.path)
        else:
            yield entry


def find_between(s, start, end):
    return (s.split(start))[1].split(end)[0]


def valid_hostname(host_name):
    """
    Approximate validation
    Reference: https://en.wikipedia.org/wiki/Hostname
    """

    if len(host_name) > 253:
        return False

    valid_label = re.compile(r"(?!-)[A-Z\d-]{1,63}(?<!-)$", re.IGNORECASE)
    label_parts = host_name.split(".")
    return all(valid_label.match(label) for label in label_parts)


def compute_device_key(primary_key, registration_id):
    """
    Compute device SAS key
    Args:
        primary_key: Primary group SAS token to compute device keys
        registration_id: Registration ID is alphanumeric, lowercase, and may contain hyphens.
    Returns:
        device key
    """
    secret = base64.b64decode(primary_key)
    device_key = base64.b64encode(
        hmac.new(
            secret, msg=registration_id.encode("utf8"), digestmod=hashlib.sha256
        ).digest()
    )
    return device_key


def generate_key(byte_length=32):
    """
    Generate cryptographically secure device key.
    """
    import secrets

    token_bytes = secrets.token_bytes(byte_length)
    return base64.b64encode(token_bytes).decode("utf8")


def ensure_azure_namespace_path():
    """
    Run prior to importing azure namespace packages (azure.*) to ensure the
    extension root path is configured for package import.
    """
    from azure.cli.core.extension import get_extension_path
    from azext_edge.constants import EXTENSION_NAME

    ext_path = get_extension_path(EXTENSION_NAME)
    if not ext_path:
        return

    ext_azure_dir = os.path.join(ext_path, "azure")
    if os.path.isdir(ext_azure_dir):
        import azure

        if (
            getattr(azure, "__path__", None) and ext_azure_dir not in azure.__path__
        ):  # _NamespacePath /w PEP420
            if isinstance(azure.__path__, list):
                azure.__path__.insert(0, ext_azure_dir)
            else:
                azure.__path__.append(ext_azure_dir)

    if sys.path and sys.path[0] != ext_path:
        sys.path.insert(0, ext_path)

    return


def is_valid_dtmi(dtmi):
    """Checks validity of a DTMI
    :param str dtmi: DTMI
    :returns: Boolean indicating if DTMI is valid
    :rtype: bool
    """
    pattern = re.compile(
        "^dtmi:[A-Za-z](?:[A-Za-z0-9_]*[A-Za-z0-9])?(?::[A-Za-z](?:[A-Za-z0-9_]*[A-Za-z0-9])?)*;[1-9][0-9]{0,8}$"
    )
    if not pattern.match(dtmi):
        return False
    return True


def assemble_nargs_to_dict(hash_list: List[str]) -> Dict[str, str]:
    result = {}
    if not hash_list:
        return result
    for hash in hash_list:
        if "=" not in hash:
            logger.warning(
                "Skipping processing of '%s', input format is key=value | key='value value'.",
                hash,
            )
            continue
        split_hash = hash.split("=", 1)
        result[split_hash[0]] = split_hash[1]
    for key in result:
        if not result.get(key):
            logger.warning(
                "No value assigned to key '%s', input format is key=value | key='value value'.",
                key,
            )
    return result
