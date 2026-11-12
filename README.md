# scrapling-schema

Schema-driven HTML extractor. Define extraction specs in Python (with full IDE type hints) or YAML, and get structured JSON out.

## Install

```bash
pip install scrapling-schema
```

## Requirements

- Python >= 3.10
- [scrapling](https://github.com/D4Vinci/Scrapling) >= 0.4
- PyYAML >= 6.0

## Python API

### Python type spec (recommended)

```python
from scrapling_schema import Schema, Field, Options, Clear, RegexSub

spec = Schema(
    options=Options(clear=Clear(remove_tags=["script", "style"])),
    fields={
        "products": Field(
            css=".product",
            type="array<object>",
            fields={
                "sku":   Field(css="SELF", type="string", attr="data-sku"),
                "name":  Field(css=".name", type="string"),
                "url":   Field(css="a.link", type="string", attr="href"),
                "price": Field(css=".price", type="number", transform=[
                    RegexSub(pattern=r"[^0-9.]+"),
                ]),
                "tags":  Field(css=".tags li", type="array<string>"),
            },
        )
    },
)

result = spec.extract(html)
json_schema = spec.json_schema(title="Products")
```

### Boolean fields (`type: "boolean"`)

Boolean output is derived from `type`, not a transform. The extractor coerces common truthy/falsey values:
- truthy: `"true"`, `"t"`, `"yes"`, `"y"`, `"on"`, `"1"` (case-insensitive, surrounding whitespace ignored)
- falsey: `"false"`, `"f"`, `"no"`, `"n"`, `"off"`, `"0"`
- numbers: `1` → `True`, `0` → `False` (other numbers become `None`)

Python example:

```python
from scrapling_schema import Schema, Field

html = "<span class='in-stock'> yes </span>"
spec = Schema(fields={"in_stock": Field(css=".in-stock", type="boolean")})

data = spec.extract(html)
assert data["in_stock"] is True
```

If you want invalid/missing values to fail fast, set `nullable=False`:

```python
from scrapling_schema import Schema, Field, ValidationError

html = "<span class='in-stock'> maybe </span>"
spec = Schema(fields={"in_stock": Field(css=".in-stock", type="boolean", nullable=False)})

try:
    spec.extract(html)
except ValidationError:
    pass
```

### YAML spec

```yaml
options:
  clear:
    remove_tags: ["script", "style"]

fields:
  products:
    css: ".product"
    type: "array<object>"
    fields:
      sku:
        css: "SELF"
        type: "string"
        attr: "data-sku"
      name:
        css: ".name"
        type: "string"
      price:
        css: ".price"
        type: "number"
        transform:
          - regex_sub: { pattern: "[^0-9.]+", repl: "" }
  in_stock:
    css: ".in-stock"
    type: "boolean"
```

```python
from scrapling_schema import extract_from_yaml

result = extract_from_yaml(html, yaml_spec)
```

## CLI

```bash
scrapling-schema --spec spec.yml --html-file page.html
scrapling-schema --spec spec.yml --schema
```

## Field reference

| param       | type   | description                                                  |
| ----------- | ------ | ------------------------------------------------------------ |
| `css`       | `str`  | CSS selector. Use `"SELF"` to select the context node itself |
| `attr`      | `str`  | Extract an attribute value (or special `"innerHTML"`)        |
| `type`      | `str`  | Output type: `"string"|"integer"|"number"|"boolean"|"object"|"array<string>"|"array<integer>"|"array<number>"|"array<boolean>"|"array<object>"` |
| `nullable`  | `bool` | If `false`, missing values raise `ValidationError`           |
| `defaultValue` | `any` | Fallback value used when the extracted value is empty        |
| `fields`    | `dict` | Nested fields (for `object` / `array<object>`)               |
| `transform` | `list` | Transform pipeline (see below)                               |
| `callback`  | `callable` | Field-level post-processing hook (Python API only)       |
| `outputSchema` | `dict` | Override JSON Schema for this field (useful when `callback` changes the output type/shape) |
| `required`  | `bool` | Raise `ValidationError` if value is empty                    |

Notes:
- `type` is required for every field.
- Arrays must use `type: "array<...>"` (no `items:` and no `list:`).
- `attr` supports special values:
  - `"innerHTML"`: extract HTML string from the selected node.
  - `"ownText"`: extract direct text for the selected node (excludes descendant text).

## Transform reference

| transform                 | shorthand | description                                   |
| ------------------------- | --------- | --------------------------------------------- |
| `RegexSub(pattern, repl)` | —         | Regex substitution                            |
| `Split(delimiter)`        | —         | Split string into array items (requires `type:"array<...>"`) |

Notes:
- String outputs are stripped automatically (no transform needed).
- Use field-level `defaultValue` for fallbacks (defaults are not supported inside transforms).

## When to use `transform` vs `callback`

Both are meant for post-processing, but they work at different levels and have different ergonomics.

### Use `transform` for value-centric pipelines

Good fit when you want a predictable, reusable pipeline on a single extracted value (e.g., regex cleanup, split).

Order of operations (scalar fields):
1. Extract raw string
2. Apply `transform` pipeline
3. Apply `type` coercion (`number`/`integer`/`boolean`)
4. Apply `callback` (if any)

Example: remove currency symbols before coercing to `number`:

```python
from scrapling_schema import Schema, Field, RegexSub

spec = Schema(
    fields={
        "price": Field(
            css=".price",
            type="number",
            transform=[RegexSub(pattern=r"[^0-9.]+", repl="")],
        )
    }
)
data = spec.extract(html)
```

### Use `callback` for whole-field logic (filtering, sorting, aggregation)

`callback` receives the final extracted value for the field:
- scalar field → the scalar value (`str|int|float|bool|None`)
- `array<...>` field → the whole list
- `object` field → the whole dict

This is a better fit for list-level operations or aggregations.

#### When `callback` changes the output type/shape

`callback` is an arbitrary Python function, so the library cannot reliably infer a JSON Schema for its return value.
If your callback changes the type/shape (e.g., list → object, object → string), set `outputSchema` on the field to
keep `spec.json_schema()` in sync with the actual output.

Example: filter a list of objects (keep only items you care about):

```python
from scrapling_schema.types import Schema, Field

def keep_only_a(items: list[dict]) -> list[dict]:
    return [item for item in items if "A" in item["name"]]

spec = Schema(
    fields={
        "products": Field(
            css=".item",
            type="array<object>",
            callback=keep_only_a,
            fields={
                "name": Field(css=".name", type="string"),
            },
        )
    }
)
data = spec.extract(html)
```

### `array<object>` special case: `transform` is per-item

For `type: "array<object>"`, `transform` is applied to each extracted object (each list element).
If a transform returns `None`, the item is dropped from the list.

```python
from scrapling_schema import extract

def drop_product_a(item: dict) -> dict | None:
    return None if item.get("name") == "Product A" else item

spec = {
    "fields": {
        "products": {
            "css": ".item",
            "type": "array<object>",
            "transform": [drop_product_a],
            "fields": {"name": {"css": ".name", "type": "string"}},
        }
    }
}
data = extract(html, spec)
```

### YAML note

YAML specs support only the built-in transform steps (e.g., `regex_sub`, `split`).
Python callables (`transform: [my_fn]` / `callback: my_fn`) are only supported via the Python API (typed `Schema/Field` or a Python `dict` spec), not via YAML text.

## Memory lifetime

The parser and DOM are local to each extraction. Once parsing finishes,
`extract()` releases its references to the preprocessed HTML before fields are
evaluated. Extraction uses a Selector around the existing DOM, allowing the
original Selector's raw-body cache to be released without reparsing the document.

Text and attribute pseudo-element results are converted from lxml smart strings
to plain Python strings before transforms run. Keeping these transform inputs
does not keep the source DOM alive.

Field evaluation releases its DOM references on both normal return and failure.
This also covers callbacks and transforms that catch an error, retain the
exception, and return successfully.

When `extract()` raises, it clears finished traceback frames belonging to this
library and Scrapling's parser to release DOM references and temporary values.
All extraction entry points drop their own HTML input references when they finish.
Exception identity, messages, traceback locations, and user callback locals are
preserved. Locals from cleared library/parser frames are therefore unavailable
when inspecting saved tracebacks. Callers and callbacks can still retain their
own inputs or values.

## Testing

Install the dev dependencies (in a virtualenv) and run the test suite:

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

Run a single test file:

```bash
python -m pytest tests/test_extractor.py
```

## License

[MIT](LICENSE)
