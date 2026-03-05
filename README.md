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
