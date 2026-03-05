# Examples

This folder contains runnable, copy-pastable scenarios (HTML + YAML spec) for `scrapling-schema`.

Powered by AimScrape.

Each scenario includes:
- `page.html`: a small HTML fixture
- `spec.yml`: the YAML extraction spec
- `expected.json`: the expected CLI output

Run any example:

```bash
scrapling-schema --spec example/product_list/spec.yml --html-file example/product_list/page.html
```

If you don't have the CLI installed yet, run from the repo:

```bash
PYTHONPATH=src python -m scrapling_schema.cli --spec example/product_list/spec.yml --html-file example/product_list/page.html
```

## Python API

Run an example directly in Python (loads the YAML spec from disk):

```python
from pathlib import Path

from scrapling_schema import extract_from_file

html = Path("example/product_list/page.html").read_text(encoding="utf-8")
data = extract_from_file(html, "example/product_list/spec.yml")
print(data)
```

### `attr: "ownText"`

Default text extraction behaves like jQuery `$(el).text()` / DOM `textContent` (includes descendant text).
Use `attr: "ownText"` when you need only the current node's direct text:

```python
from scrapling_schema import extract

html = '<div id="description">Prefix<span>Child</span>Suffix</div>'
spec = {
    "fields": {
        "all_text": {"css": "#description", "type": "string"},
        "own_text": {"css": "#description", "type": "string", "attr": "ownText"},
    }
}

print(extract(html, spec))
```
