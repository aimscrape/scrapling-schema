# scrapling-schema

Schema-driven HTML extractor. Define extraction specs in Python (with full IDE type hints) or YAML, and get structured JSON out.

## Install

```bash
pip install git+https://github.com/aimscrape/scrapling-schema.git
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
            list=True,
            fields={
                "sku":   Field(css="SELF", attr="data-sku"),
                "name":  Field(css=".name", text=True, transform=["strip"]),
                "url":   Field(css="a.link", attr="href"),
                "price": Field(css=".price", text=True, transform=[
                    RegexSub(pattern=r"[^0-9.]+"),
                    "to_float",
                ]),
                "tags":  Field(css=".tags li", list=True, text=True, transform=["strip"]),
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
    list: true
    fields:
      sku:
        css: "SELF"
        attr: "data-sku"
      name:
        css: ".name"
        text: true
        transform: ["strip"]
      price:
        css: ".price"
        text: true
        transform:
          - regex_sub: { pattern: "[^0-9.]+", repl: "" }
          - to_float
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

| param | type | description |
|---|---|---|
| `css` | `str` | CSS selector. Use `"SELF"` to select the context node itself |
| `text` | `bool` | Extract text content |
| `attr` | `str` | Extract an attribute value |
| `html` | `bool` | Extract outer HTML |
| `list` | `bool` | Return a list of matched nodes |
| `fields` | `dict` | Nested fields (object or list of objects) |
| `transform` | `list` | Transform pipeline (see below) |
| `required` | `bool` | Raise `ValidationError` if value is empty |

## Transform reference

| transform | shorthand | description |
|---|---|---|
| `"strip"` | ✓ | Strip whitespace |
| `"to_int"` | ✓ | Convert to integer |
| `"to_float"` | ✓ | Convert to float |
| `RegexSub(pattern, repl)` | — | Regex substitution |
| `Split(delimiter)` | — | Split string into list (requires `list=True`) |
| `Default(value)` | — | Fallback value when result is empty |

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
