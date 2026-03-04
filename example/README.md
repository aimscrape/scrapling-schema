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
