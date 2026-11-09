"""Dataset file import with row-level validation.

Supported formats: JSON (``[...]`` or ``{"records": [...]}``), JSONL, and CSV
with a header row. Imports are all-or-nothing: invalid input imports nothing and
returns the offending row numbers so the caller can fix the file.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

MAX_IMPORT_RECORDS = 500
MAX_TEXT_LENGTH = 20_000
MAX_METADATA_LENGTH = 4_096
MAX_CONTEXT_LENGTH = 60_000
MAX_REPORTED_ERRORS = 50
ALLOWED_FIELDS = {"input", "expected_output", "context", "metadata"}


class DatasetImportError(Exception):
    """Validation failure carrying structured, row-level errors."""

    def __init__(self, errors: list[dict[str, Any]], total: int | None = None):
        super().__init__("The dataset file could not be imported.")
        self.errors = errors
        self.error_count = total if total is not None else len(errors)


def _error(row: int, field: str, message: str) -> dict[str, Any]:
    return {"row": row, "field": field, "message": message}


def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DatasetImportError(
            [_error(0, "file", "The file must be UTF-8 encoded text.")]
        ) from exc


def _parse_json(text: str) -> list[Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DatasetImportError(
            [_error(exc.lineno or 0, "file", f"Invalid JSON: {exc.msg}.")]
        ) from exc
    if isinstance(payload, dict):
        if "records" not in payload:
            raise DatasetImportError(
                [_error(0, "file", 'JSON objects must contain a "records" array.')]
            )
        payload = payload["records"]
    if not isinstance(payload, list):
        raise DatasetImportError(
            [_error(0, "file", "A JSON dataset must be an array of records.")]
        )
    return payload


def _parse_jsonl(text: str) -> list[Any]:
    rows: list[Any] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise DatasetImportError(
                [_error(line_number, "file", f"Invalid JSON on line {line_number}: {exc.msg}.")]
            ) from exc
    return rows


def _parse_context_cell(value: str) -> Any:
    stripped = value.strip()
    if not stripped:
        return None
    if stripped.startswith("["):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return stripped
    if "||" in stripped:
        return [part.strip() for part in stripped.split("||") if part.strip()]
    return stripped


def _parse_csv(text: str) -> list[Any]:
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise DatasetImportError([_error(1, "header", "The CSV needs a header row.")])
    headers = [name.strip() for name in reader.fieldnames if name]
    unknown = [name for name in headers if name not in ALLOWED_FIELDS]
    if unknown:
        raise DatasetImportError(
            [
                _error(
                    1,
                    "header",
                    "Unsupported column(s): "
                    + ", ".join(unknown)
                    + ". Use input, expected_output, context, metadata.",
                )
            ]
        )
    if "input" not in headers:
        raise DatasetImportError([_error(1, "header", 'The CSV needs an "input" column.')])

    rows: list[Any] = []
    for line_number, raw_row in enumerate(reader, start=2):
        if not any((value or "").strip() for value in raw_row.values() if isinstance(value, str)):
            continue
        row: dict[str, Any] = {"input": raw_row.get("input") or ""}
        expected = raw_row.get("expected_output")
        if expected is not None and expected != "":
            row["expected_output"] = expected
        context = raw_row.get("context")
        if context is not None and context.strip():
            row["context"] = _parse_context_cell(context)
        metadata = raw_row.get("metadata")
        if metadata is not None and metadata.strip():
            try:
                row["metadata"] = json.loads(metadata)
            except json.JSONDecodeError:
                raise DatasetImportError(
                    [
                        _error(
                            line_number,
                            "metadata",
                            "The metadata column must contain a JSON object.",
                        )
                    ]
                ) from None
        rows.append(row)
    return rows


def _normalise_record(row: Any, row_number: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    if not isinstance(row, dict):
        return {}, [_error(row_number, "record", "Each record must be a JSON object.")]

    unknown = sorted(set(row) - ALLOWED_FIELDS)
    if unknown:
        errors.append(
            _error(
                row_number,
                "record",
                "Unsupported field(s): " + ", ".join(unknown) + ".",
            )
        )

    raw_input = row.get("input")
    if not isinstance(raw_input, str) or not raw_input.strip():
        errors.append(_error(row_number, "input", "Each record needs a non-empty input."))
        input_value = ""
    else:
        input_value = raw_input
        if len(input_value) > MAX_TEXT_LENGTH:
            errors.append(
                _error(
                    row_number,
                    "input",
                    f"Input may be at most {MAX_TEXT_LENGTH} characters.",
                )
            )

    raw_expected = row.get("expected_output")
    if raw_expected is None:
        expected_value = ""
    elif not isinstance(raw_expected, str):
        errors.append(
            _error(row_number, "expected_output", "Expected output must be text.")
        )
        expected_value = ""
    else:
        expected_value = raw_expected
        if len(expected_value) > MAX_TEXT_LENGTH:
            errors.append(
                _error(
                    row_number,
                    "expected_output",
                    f"Expected output may be at most {MAX_TEXT_LENGTH} characters.",
                )
            )

    context_value: list[str] = []
    raw_context = row.get("context")
    if raw_context not in (None, "", []):
        if isinstance(raw_context, str):
            candidates = [raw_context]
        elif isinstance(raw_context, list) and all(
            isinstance(item, str) for item in raw_context
        ):
            candidates = raw_context
        else:
            errors.append(
                _error(
                    row_number,
                    "context",
                    "Context must be a string or a list of strings.",
                )
            )
            candidates = []
        context_value = [item for item in candidates if item.strip()]
        if sum(len(item) for item in context_value) > MAX_CONTEXT_LENGTH:
            errors.append(
                _error(row_number, "context", "Context is too large.")
            )

    raw_metadata = row.get("metadata")
    if raw_metadata is None:
        metadata_value = {}
    elif isinstance(raw_metadata, dict):
        metadata_value = raw_metadata
        try:
            encoded = json.dumps(metadata_value)
        except (TypeError, ValueError):
            encoded = "x" * (MAX_METADATA_LENGTH + 1)
        if len(encoded) > MAX_METADATA_LENGTH:
            errors.append(_error(row_number, "metadata", "Metadata is too large."))
    else:
        errors.append(_error(row_number, "metadata", "Metadata must be a JSON object."))
        metadata_value = {}

    return (
        {
            "input": input_value,
            "expected_output": expected_value,
            "context": context_value,
            "metadata": metadata_value,
        },
        errors,
    )


def parse_dataset_file(filename: str, raw: bytes) -> list[dict[str, Any]]:
    """Parse and validate an uploaded dataset file."""
    name = (filename or "").lower()
    text = _decode(raw)
    if name.endswith(".jsonl") or name.endswith(".ndjson"):
        rows = _parse_jsonl(text)
    elif name.endswith(".csv"):
        rows = _parse_csv(text)
    elif name.endswith(".json"):
        rows = _parse_json(text)
    else:
        raise DatasetImportError(
            [_error(0, "file", "Upload a .json, .jsonl or .csv file.")]
        )

    if not rows:
        raise DatasetImportError([_error(0, "file", "The file contains no records.")])
    if len(rows) > MAX_IMPORT_RECORDS:
        raise DatasetImportError(
            [
                _error(
                    0,
                    "file",
                    f"Import at most {MAX_IMPORT_RECORDS} records at a time.",
                )
            ]
        )

    cleaned: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for row_number, row in enumerate(rows, start=1):
        record, record_errors = _normalise_record(row, row_number)
        errors.extend(record_errors)
        if not record_errors:
            cleaned.append(record)

    if errors:
        raise DatasetImportError(errors[:MAX_REPORTED_ERRORS], total=len(errors))
    return cleaned
