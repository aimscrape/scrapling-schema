import pytest
from scrapling_schema import extract_from_yaml

HTML = """
<ul>
  <li class="item"><span class="name">Product A</span></li>
  <li class="item"><span class="name">Product B</span></li>
</ul>
""".strip()


def test_transform_on_array_object():
    # Per-item transform for array<object>
    def filter_product(item):
        if item["name"] == "Product A":
            return None  # transform returning None for item in list clears it
        return item

    spec = {
        "fields": {
            "products": {
                "css": ".item",
                "type": "array<object>",
                "transform": [filter_product],
                "fields": {
                    "name": {"css": ".name", "type": "string"},
                },
            }
        }
    }

    from scrapling_schema import core

    data = core.extract(HTML, spec)

    print(f"Result (transform): {data['products']}")
    assert len(data["products"]) == 1
    assert data["products"][0]["name"] == "Product B"


def test_callback_on_array_object():
    from scrapling_schema.types import Schema, Field

    # List-level callback
    def my_callback(items):
        # Filtering the entire list
        return [item for item in items if "A" in item["name"]]

    spec = Schema(
        fields={
            "products": Field(
                css=".item",
                type="array<object>",
                callback=my_callback,
                fields={
                    "name": Field(css=".name", type="string"),
                },
            )
        }
    )

    data = spec.extract(HTML)
    print(f"Result (callback): {data['products']}")
    assert len(data["products"]) == 1
    assert data["products"][0]["name"] == "Product A"


def test_callback_on_scalar():
    from scrapling_schema.types import Schema, Field

    def upper_name(name):
        return name.upper()

    spec = Schema(
        fields={"product_name": Field(css=".name", type="string", callback=upper_name)}
    )

    data = spec.extract(HTML)
    print(f"Result (scalar callback): {data['product_name']}")
    assert data["product_name"] == "PRODUCT A"


if __name__ == "__main__":
    pytest.main([__file__])
