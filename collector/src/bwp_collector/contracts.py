"""Versioned schemas shared with the future Java ingestion service."""

from jsonschema import Draft202012Validator

SLUG = {"type": "string", "pattern": "^[a-zA-Z0-9_-]{1,64}$"}
TEXT = {"type": "string", "minLength": 1, "maxLength": 64}
DECIMAL = {"type": "string", "pattern": "^(0|[1-9][0-9]{0,18})$"}


def obj(properties, required=None):
    return {"type": "object", "properties": properties,
            "required": list(properties) if required is None else required,
            "additionalProperties": False}


def array(item, minimum=1):
    return {"type": "array", "items": item, "minItems": minimum}


BOX = {"type": "array", "items": {"type": "integer", "minimum": 0}, "minItems": 4, "maxItems": 4}
FIELD = obj({"image": SLUG, "box": BOX})
VALUE_FIELDS = {"player_id": TEXT, "grade": {"enum": [5, 6, 7, 8, 9, 10]},
                "bailian_points": DECIMAL, "cumulative_wins": DECIMAL}
SAMPLE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    **obj({
        "schema_version": {"const": "1.0"},
        "sample_kind": {"enum": ["real", "synthetic"]},
        "context_confirmed": {"type": "boolean"},
        "scope_key": {"type": ["string", "null"], "minLength": 1, "maxLength": 64},
        "season_key": {"type": ["string", "null"], "minLength": 1, "maxLength": 64},
        "shikigami_id": {"type": ["string", "null"], "pattern": "^[1-9][0-9]{0,9}$"},
        "images": array(obj({"key": SLUG, "path": {"type": "string", "minLength": 1},
                             "captured_at": {"type": "string"},
                             "size": {"type": "array", "items": {"type": "integer", "minimum": 1},
                                      "minItems": 2, "maxItems": 2}})),
        "rows": array(obj({"key": SLUG, "identity_confirmed": {"type": "boolean"},
                           "fields": obj({name: FIELD for name in VALUE_FIELDS}, []),
                           "expected": obj(VALUE_FIELDS, [])}, ["key", "identity_confirmed", "fields"]))
    })
}
BATCH_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    **obj({
        "schema_version": {"const": "1.0"}, "scope_key": TEXT,
        "records": array(obj({
            "capture_id": {"type": "string", "format": "uuid"},
            "shikigami_id": {"type": "string", "pattern": "^[1-9][0-9]{0,9}$"},
            "season_key": TEXT, **VALUE_FIELDS,
            "captured_at": {"type": "string", "pattern": "^.*T.*\\.[0-9]{3}Z$", "format": "date-time"},
            "image_keys": {**array(SLUG), "uniqueItems": True}
        })),
        "images": array(obj({"key": SLUG, "sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"}}))
    })
}
CONFIG_SCHEMA = obj({
    "schema_version": {"const": "1.0"},
    "calibrated": {"type": "boolean"},
    "min_confidence": {"type": "number", "minimum": 0, "maximum": 1},
    "max_profile_delay_seconds": {"type": "number", "minimum": 0, "maximum": 600},
    "preprocess": {"enum": ["color", "gray", "threshold"]},
    "scale": {"type": "integer", "minimum": 1, "maximum": 4},
    "detection_model": {"type": "string", "minLength": 1},
    "recognition_model": {"type": "string", "minLength": 1},
    "text_detection_model_dir": {"type": ["string", "null"]},
    "text_recognition_model_dir": {"type": ["string", "null"]}
}, ["schema_version", "calibrated", "min_confidence", "max_profile_delay_seconds",
    "preprocess", "scale", "detection_model", "recognition_model"])


def validate(value, schema):
    errors = sorted(Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
                    .iter_errors(value), key=lambda e: str(list(e.path)))
    if errors:
        error = errors[0]
        raise ValueError(f"格式错误 {'.'.join(map(str, error.path))}: {error.message}")
