import copy
from unittest.mock import patch

import pytest

from hosaka.extensions.manifest import ExtensionError, _check_schema, validate_schema


def test_schema_checks_are_content_cached_and_instance_independent():
    schema = {"type": "object", "properties": {"value": {"type": "string"}}}
    _check_schema.cache_clear()
    with patch("hosaka.extensions.manifest.Draft202012Validator.check_schema") as check:
        validate_schema(schema)
        validate_schema(copy.deepcopy(schema))
        assert check.call_count == 1
        schema["properties"]["value"]["type"] = "integer"
        validate_schema(schema)
        assert check.call_count == 2
    _check_schema.cache_clear()


def test_invalid_and_external_schemas_are_never_accepted_by_cache():
    for schema in ({"type": "not-a-type"}, {"$ref": "https://example.invalid/schema"}):
        for _ in range(2):
            with pytest.raises(ExtensionError):
                validate_schema(schema)
