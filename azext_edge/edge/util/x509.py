# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

"""
x509: certificate utilities.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple, Union

from azure.cli.core.azclierror import InvalidArgumentValueError
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from knack.log import get_logger

from azext_edge.edge.providers.orchestration.common import X509FileExtension

# aka prime256v1
DEFAULT_EC_ALGO = ec.SECP256R1()
DEFAULT_VALID_DAYS = 365

logger = get_logger(__name__)


def generate_self_signed_cert(valid_days: int = DEFAULT_VALID_DAYS) -> Tuple[bytes, bytes]:
    if not valid_days or valid_days < 0:
        valid_days = DEFAULT_VALID_DAYS
    # Not using DEFAULT_EC_ALGO due CodeQL issue parsing private key algo
    key = ec.generate_private_key(curve=ec.SECP256R1(), backend=default_backend())
    key_bytes = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )

    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, "Azure IoT Operations Quickstart Root CA - Not for Production"),
        ]
    )
    public_key = key.public_key()
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(public_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=valid_days))
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=None),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                key_cert_sign=True,
                digital_signature=False,
                crl_sign=False,
                content_commitment=False,
                data_encipherment=False,
                decipher_only=False,
                encipher_only=False,
                key_agreement=False,
                key_encipherment=False,
            ),
            critical=False,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(public_key),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    return (cert.public_bytes(serialization.Encoding.PEM), key_bytes)


def decode_x509_files(
    cert_data: bytes,
    content_format: str,
    extension: str
) -> Optional[List[Union[x509.Certificate, x509.CertificateRevocationList]]]:
    # Decodes an X.509 file from PEM or DER format.
    certs: List = []
    try:
        if content_format == X509FileExtension.PEM.name:
            # PEM format
            certs = x509.load_pem_x509_certificates(cert_data)
        elif content_format == X509FileExtension.DER.name:
            # DER format
            if extension and extension.lower() == X509FileExtension.DER.value:
                certs = [x509.load_der_x509_certificate(cert_data, default_backend())]
            elif extension and extension.lower() == X509FileExtension.CRL.value:
                certs = [x509.load_der_x509_crl(cert_data, default_backend())]
        return certs
    except Exception as e:
        raise InvalidArgumentValueError(
            f"Failed to decode certificate data. Ensure the data is in {content_format} format. Error: {e}"
        )
