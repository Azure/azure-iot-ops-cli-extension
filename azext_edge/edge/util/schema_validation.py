# coding=utf-8
# ----------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License file in the project root for license information.
# ----------------------------------------------------------------------------------------------

from typing import Optional

from azure.cli.core.azclierror import InvalidArgumentValueError


def check_json_schema(schema: dict) -> Optional[str]:
    """Check whether a schema is a recognized, valid JSON Schema suitable for validation.

    Returns None if the schema is usable. Returns a human-readable reason string if
    validation should be skipped — either because the $schema dialect is not recognized
    (e.g., IoT Operations custom formats) or the schema is structurally invalid.
    """
    import jsonschema

    schema_dialect = schema.get("$schema", "")
    if schema_dialect and "json-schema.org" not in schema_dialect:
        return f"Schema dialect '{schema_dialect}' is not a recognized JSON Schema format"

    validator_cls = jsonschema.validators.validator_for(schema)
    try:
        validator_cls.check_schema(schema)
    except jsonschema.SchemaError as e:
        return f"Schema is not valid JSON Schema: {e.message}"

    return None


def validate_data_against_schema(schema: dict, data: dict, name: Optional[str] = None) -> None:
    """Validate data against a JSON Schema, raising on validation failures.

    Collects all validation errors, formats them with property paths and
    oneOf/anyOf context handling, and raises InvalidArgumentValueError.
    Assumes the schema itself is valid — use check_json_schema() first
    for untrusted schemas.
    """
    import jsonschema

    validator = jsonschema.validators.validator_for(schema)(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: str(list(e.path)))

    if not errors:
        return

    final_messages = []
    for error in errors:
        path = ".".join([str(p) for p in error.path])
        if error.validator in ("oneOf", "anyOf") and error.context:
            # Prefer value-mismatch errors over structural-mismatch errors
            # when multiple sub-schema alternatives fail.
            value_errors = [
                e for e in error.context
                if e.validator not in ("additionalProperties", "required", "type", "const", "enum")
            ]
            best = jsonschema.exceptions.best_match(value_errors or error.context)
            msg = best.message
        else:
            msg = error.message

        if path:
            final_messages.append(f"Property '{path}' is invalid: {msg}")
        else:
            final_messages.append(f"Invalid configuration: {msg}")

    error_msg = "\n".join(final_messages)
    prefix = f"The following {name} values are invalid:\n" if name else "Invalid input data:\n"
    raise InvalidArgumentValueError(f"{prefix}{error_msg}")
