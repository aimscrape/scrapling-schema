import pytest

from scrapling_schema import ExtractError, Field, Schema, schema


def test_output_schema_override_is_used_for_json_schema() -> None:
    def summarize(items: list[str]) -> dict:
        return {"count": len(items)}

    spec = Schema(
        fields={
            "summary": Field(
                css=".item",
                type="array<string>",
                callback=summarize,
                outputSchema={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"count": {"type": "integer"}},
                    "required": ["count"],
                },
            )
        }
    )

    s = spec.json_schema(title="Example")
    assert s["properties"]["summary"]["type"] == "object"
    assert s["properties"]["summary"]["properties"]["count"]["type"] == "integer"
    assert s["properties"]["summary"]["additionalProperties"] is False


def test_output_schema_override_still_applies_required_best_effort() -> None:
    spec = Schema(
        fields={
            "x": Field(
                css="a",
                type="string",
                required=True,
                callback=lambda _: ["a"],
                outputSchema={"type": "array", "items": {"type": "string"}},
            )
        }
    )

    s = spec.json_schema()
    assert s["properties"]["x"]["type"] == "array"
    assert s["properties"]["x"]["minItems"] == 1


def test_output_schema_override_does_not_skip_spec_validation() -> None:
    with pytest.raises(ExtractError):
        schema(
            {
                "fields": {
                    "x": {
                        "css": "a",
                        # missing "type" (still invalid even if outputSchema is present)
                        "outputSchema": {"type": "string"},
                    }
                }
            }
        )

