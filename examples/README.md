# examples/ sample index

[English](README.md) · [简体中文](README.cn.md)

Every scenario has **equivalent JSON and YAML configs**. Paths resolve relative to each sample file, so you can run the demo directly:

```bash
# From the repository root
PYTHONPATH=src py -3.12 examples/demo.py
# After installing the package
python examples/demo.py
```

| Scenario | JSON | YAML | Features demonstrated |
| --- | --- | --- | --- |
| Basics | `json/01-basic.json` | `yaml/01-basic.yaml` | Nested structure, `${VAR:default}` |
| Layered imports | `json/layered/{base,common,app}.json` | `yaml/layered/{base,common,app}.yaml` | `import` chain + recursive deep merge |
| Template merges | `json/03-merge.json` | `yaml/03-merge.yaml` | `merge` reuses objects in the same file, multiple templates |
| Inline validation | `json/04-schema-inline.json` | `yaml/04-schema-inline.yaml` | Type / required / default / range / choices |
| External schema | `json/05-schema-external.json` + `schema-*.json` | `yaml/05-schema-external.yaml` + `schema-*.yaml` | An external schema file that itself uses `import` |
| Expressions | `json/06-expressions*.json` | `yaml/06-expressions*.yaml` | Chained `this`, cross-file `root`, `calc` arithmetic |
| Reserved-word escaping | `json/07-escape.json` | `yaml/07-escape.yaml` | `~import` / `~schema` become ordinary fields |
| Mount and aliases | `json/08-mount-adapter.json` | `yaml/08-mount-adapter.yaml` | `mount` + `add_config` + alias + tracing |

## YAML writing notes

1. `%{calc: ...}` **must be quoted**: otherwise YAML treats `: ` as a mapping separator.
2. `${...}` inside a flow sequence **must be quoted**: `merge: ["${this.templates.http}"]`; the bare form `[${this.x}]` is parsed as a mapping start and fails.
3. Bare use in a plain scalar is safe: `url: ${this.host}/v1`.
4. Escape keys such as `~import` / `~schema` need no quotes in YAML.
