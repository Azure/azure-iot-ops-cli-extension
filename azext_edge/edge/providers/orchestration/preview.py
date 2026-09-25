# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""Explicit preview creation consent; release-approved text is supplied by the profile."""

import sys
from urllib.parse import urlsplit

from azure.cli.core.azclierror import ValidationError
from rich.console import Console
from rich.prompt import Confirm

from .runtime_profiles import RuntimeProfile


console = Console(stderr=True)


def confirm_preview_creation(profile: RuntimeProfile, confirm_yes: bool = False) -> bool:
    agreement = urlsplit(profile.preview_agreement_url or "")
    if not profile.preview_notice or agreement.scheme != "https" or not agreement.netloc:
        raise ValidationError(
            "This preview profile has no approved notice and agreement URL. Creation cannot continue."
        )
    console.print(profile.preview_notice, markup=False)
    console.print(profile.preview_agreement_url, markup=False)
    if confirm_yes:
        return True
    if not sys.stdin.isatty():
        raise ValidationError("Preview creation requires explicit acceptance. Use --yes for noninteractive execution.")
    try:
        return Confirm.ask("Accept the preview terms and create a preview instance?", default=True, console=console)
    except (EOFError, KeyboardInterrupt):
        return False
