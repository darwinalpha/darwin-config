# examples/ sample index

[English](README.md) · [简体中文](README.cn.md)

Every scenario has **equivalent JSON, YAML and TOML configs**. Paths resolve relative to each sample file, so you can run the demo directly:

```bash
# From the repository root
PYTHONPATH=src py -3.12 examples/demo.py
# After installing the package
python examples/demo.py
```

| Scenario | JSON | YAML | TOML | Features demonstrated |
| --- | --- | --- | --- | --- |
| Basics | `json/01-basic.json` | `yaml/01-basic.yaml` | `toml/01-basic.toml` | Nested structure, `${VAR:default}` |
| Layered imports | `json/layered/{base,common,app}.json` | `yaml/layered/{base,common,app}.yaml` | `toml/layered/{base,common,app}.toml` | `import` chain + recursive deep merge |
| Template merges | `json/03-merge.json` | `yaml/03-merge.yaml` | `toml/03-merge.toml` | `merge` reuses objects in the same file, multiple templates |
| Inline validation | `json/04-schema-inline.json` | `yaml/04-schema-inline.yaml` | `toml/04-schema-inline.toml` | Type / required / default / range / choices |
| External schema | `json/05-schema-external.json` + `schema-*.json` | `yaml/05-schema-external.yaml` + `schema-*.yaml` | `toml/05-schema-external.toml` + `schema-*.toml` | An external schema file that itself uses `import` |
| Expressions | `json/06-expressions*.json` | `yaml/06-expressions*.yaml` | `toml/06-expressions*.toml` | Chained `this`, cross-file `root`, `calc` arithmetic |
| Reserved-word escaping | `json/07-escape.json` | `yaml/07-escape.yaml` | `toml/07-escape.toml` | `~import` / `~schema` become ordinary fields |
| Mount and aliases | `json/08-mount-adapter.json` | `yaml/08-mount-adapter.yaml` | `toml/08-mount-adapter.toml` | `mount` + `add_config` + alias + tracing |

## YAML writing notes

1. `%{calc: ...}` **must be quoted**: otherwise YAML treats `: ` as a mapping separator.
2. `${...}` inside a flow sequence **must be quoted**: `merge: ["${this.templates.http}"]`; the bare form `[${this.x}]` is parsed as a mapping start and fails.
3. Bare use in a plain scalar is safe: `url: ${this.host}/v1`.
4. Escape keys such as `~import` / `~schema` need no quotes in YAML.
5. Avoid native YAML anchors and merge keys (`&a` / `*a` / `<<`) when using the library's directives: PyYAML expands them before the library runs, `<<: [*a, *b]` is first-wins (the library's `merge` is last-wins), anchors cannot cross `import` files, and `safe_dump` expands them on save. Use `merge` / `import` instead — see section 5.4 of the main README.

## TOML writing notes

1. Root-level keys must come before any `[table]` header; keys after `[schema]` belong to that table. Use inline tables (`schema = { port = { type = "integer" } }`) if you prefer a flat layout.
2. `~`-escaped keys must be quoted: `"~import" = [...]` — TOML bare keys disallow `~`.
3. Native TOML dates/timestamps map to Python `datetime`/`date` and can be validated with `type = "datetime"` / `"date"`.
4. TOML has no `null`; omit the key to express "no value".
5. Reading TOML needs no dependency (`tomllib` is in the standard library); writing needs `pip install darwin-config[toml]`.
