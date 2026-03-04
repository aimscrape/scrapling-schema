# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

scrapling-schema is a schema-driven HTML extractor that converts HTML into structured JSON using declarative specs. Users can define extraction rules in Python (with full IDE type hints) or YAML format.

## Development Commands

### Setup
```bash
pip install -e ".[dev]"
```

### Testing
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_extractor.py

# Run specific test
pytest tests/test_extractor.py::test_scalar_text_default_and_strip_transform
```

### CLI Usage
```bash
# Extract data from HTML
scrapling-schema --spec spec.yml --html-file page.html

# Generate JSON Schema from spec
scrapling-schema --spec spec.yml --schema
```

## Architecture

### Core Components

**src/scrapling_schema/types.py** - Python type definitions for type-safe spec building
- `Schema`, `Field`, `Options` - Main spec structures with full dataclass support
- Transform classes: `RegexSub`, `Split`, `ToInt`, `ToFloat`, `Default`
- All types have `.to_dict()` methods to convert to dict format for core processing

**src/scrapling_schema/core.py** - Extraction engine and spec processing
- `extract()` - Main extraction function, takes HTML + dict spec
- `extract_from_yaml()` / `extract_from_file()` - YAML spec loaders
- `schema()` / `schema_from_yaml()` - JSON Schema generation
- Uses `scrapling.parser.Selector` for HTML parsing
- Transform pipeline: processes `transform` lists sequentially
- Field evaluation: `_eval_field()` handles css selection, text/attr/html extraction, nested fields, and transforms

**src/scrapling_schema/cli.py** - Command-line interface
- Handles `--spec`, `--html`, `--html-file`, `--schema` arguments
- Exit codes: 0=success, 2=spec error, 3=validation error

### Data Flow

1. Spec (Python types or YAML) → dict format via `.to_dict()` or YAML parsing
2. HTML preprocessing: remove unwanted tags based on `options.clear.remove_tags`
3. Parse HTML with `scrapling.parser.Selector`
4. Evaluate fields recursively:
   - CSS selection (supports "SELF" for context node)
   - Extract text/attr/html
   - Apply transform pipeline
   - Handle nested fields and lists
   - Validate `required` fields
5. Return structured dict/list result

### Transform Pipeline

Transforms are applied sequentially. Built-in transforms:
- `"strip"` - whitespace trimming
- `"to_int"` / `"to_float"` - type conversion
- `RegexSub(pattern, repl)` - regex substitution
- `Split(delimiter)` - string splitting (requires `list=True`)
- `Default(value)` - fallback for empty values
- Custom callables (Python-only, not serializable to YAML)

### Field Extraction Modes

Fields support one extraction mode at a time:
- `text=True` - extract text content
- `attr="name"` - extract attribute value
- `html=True` - extract outer HTML
- `fields={...}` - nested object/list extraction

Use `list=True` to extract multiple matches instead of just the first.

## Testing

Tests use pytest and cover:
- Basic extraction scenarios (test_extractor.py)
- JSON Schema generation (test_json_schema.py)
- Spec validation and error handling (test_spec_validation.py)
- Complex nested structures (test_more_scenarios.py)

Test HTML fixtures are defined inline as string constants.
