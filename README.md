# darwin-config

[English](README.md) · [简体中文](README.cn.md)

A layered, recursive JSON / YAML configuration loader: declare where values come from, how they merge, how they are validated and referenced — all in one file. The library takes care of the rest.

- **Zero third-party dependencies in the core**; YAML is an optional extra
- One DSL covers everything: layered imports, template merges, environment variables, in-file / cross-file references, arithmetic expressions, and schema validation
- **A small, well-defined API**: load, read, override, alias, validate and trace — no redundant state-management helpers

```bash
pip install darwin-config              # JSON works out of the box
pip install 'darwin-config[yaml]'      # add YAML support
```

Python >= 3.12.

---

## 1. At a glance: what a config file looks like

The same configuration in equivalent JSON and YAML. Directives are **bare keywords**: `import` / `merge` / `mount` / `schema`:

**`settings.yaml`**

```yaml
import:                          # 1) import base layers first; multiple allowed, later ones override earlier ones
  - base.yaml
schema:                          # 2) validate + fill defaults (port is missing below, so 5432 is filled in)
  database.host: { type: string, required: true }
  database.port: { type: integer, default: 5432, min: 1, max: 65535 }

database:
  host: ${DB_HOST:localhost}     # 3) environment variable: values > env > default
  # port is filled in by the schema
  dsn: "postgresql://${this.database.host}:${this.database.port}/app"  # 4) in-file reference
  pool:
    merge: ${this.defaults.pool} # 5) reuse another object in this file as a template
    max: 50

# Template object (not meant to be a standalone config; used only as a merge source)
defaults:
  pool: { min: 1, max: 10, timeout: 30 }

app:
  retry: 3
  interval: 2
  budget: "%{calc: ${this.app.retry} * ${this.app.interval} }"  # 6) arithmetic (quote it in YAML)
```

```python
from darwin_config import init_config, get_config

init_config(files=["settings.yaml"], mount="config", validate=True)

get_config("config.database.dsn")   # 'postgresql://localhost:5432/app'
get_config("config.database.pool")  # {'min': 1, 'max': 50, 'timeout': 30}
get_config("config.app.budget")     # 6
```

**Equivalent JSON** (`%{calc: ...}` needs no quotes here):

```json
{
  "import": ["base.json"],
  "schema": {
    "database.host": { "type": "string", "required": true },
    "database.port": { "type": "integer", "default": 5432, "min": 1, "max": 65535 }
  },
  "database": {
    "host": "${DB_HOST:localhost}",
    "dsn": "postgresql://${this.database.host}:${this.database.port}/app",
    "pool": { "merge": "${this.defaults.pool}", "max": 50 }
  },
  "defaults": { "pool": { "min": 1, "max": 10, "timeout": 30 } },
  "app": {
    "retry": 3,
    "interval": 2,
    "budget": "%{calc: ${this.app.retry} * ${this.app.interval} }"
  }
}
```

> `examples/` contains 8 pairs of equivalent JSON/YAML samples and a runnable demo. Run `PYTHONPATH=src py -3.12 examples/demo.py` to see every capability in action.

---

## 2. Syntax quick reference

| Syntax | Meaning | Resolved at |
| --- | --- | --- |
| `import: "base.yaml"` / `import: [...]` | Import other configs, resolved relative to the current file; nesting is supported. Later imports override earlier ones; the current file overrides all imports | Load time |
| `merge: ${this.templates.http}` / `[...]` | Deep-merge another object in the same file into the current one; the current object's fields win | Load time |
| `mount: adapter.tushare` | Declare the mount point of a file (top level only; used by `add_config`) | Load time |
| `schema: {...}` / `schema: "rules.json"` | Validation rules, inline or from an external file (top level only; external files may themselves use `import`) | Load time, before env substitution |
| `${this.a.b}` | In-file reference; references can chain | Load time |
| `${root.a.b}` | Global config-tree reference, works across files; **resolved on read at runtime** | Runtime |
| `${VAR}` / `${VAR:default}` | Environment variable; precedence: `values` > `os.environ` > default; missing without a default raises an error | Load time (any leftover at runtime is resolved once more by the node) |
| `%{calc: expr}` | Restricted arithmetic; only `+ - * / // % **` and whitelisted functions (`abs/min/max/round/sum/len/int/float/str/bool`) | Runtime |
| `~import` / `~schema`, etc. | The `~` prefix escapes a reserved word into an ordinary business field (unescaped at the end of the pipeline) | Load time |
| `{param}` | Business template placeholder, kept as-is and never touched by env substitution | — |

**Two YAML gotchas** (JSON does not have these):

1. `%{calc: ...}` must be quoted: `total: "%{calc: ${this.a} * 2}"`, otherwise `: ` is treated as a mapping separator by YAML.
2. `${...}` inside a flow sequence must be quoted: `merge: ["${this.tpl}"]`. Written bare as `[${this.tpl}]`, YAML treats `{` as the start of a mapping and parsing fails. Bare use in a plain scalar is safe: `url: ${this.host}/v1`.

---

## 3. Five core APIs in practice

### `init_config(files, mount="", values=None, validate=False, base_dir=None, directives=None)`

Initialize the global configuration system: expand globs, load files in order, merge them, and build the node tree. **Every call resets all previous state.**

```python
from darwin_config import init_config

# Multiple files: later files override earlier ones; globs and ${VAR} path variables both work
init_config(
    files=["config/base.yaml", "config/env/${APP_ENV:dev}/*.json"],
    mount="config",                    # mount everything under config.*; empty means the root
    values={"APP_ENV": "prod"},        # injected variables, higher priority than env vars
    validate=True,                     # enable schema validation and default filling
    base_dir="config",                 # base directory for relative paths; defaults to cwd
    directives={"import": "cfg_import"},  # optional: rename a reserved word
)
```

### `get_config(path="", default=None, raise_on_not_found=False)`

Read a value. A whole-string `${root.xxx}` expression is resolved on read, so it can reference config added **later**.

```python
from darwin_config import get_config, ConfigPathNotFoundError

get_config("config.database.host")                    # 'localhost'
get_config("config.database.timeout", default=30)     # fallback when missing
get_config("config.database")                         # whole subtree (dict)
get_config()                                          # all resolved config
get_config("config.missing", raise_on_not_found=True) # raises ConfigPathNotFoundError
```

### `set_config(path, value)`

Runtime override, not written back to any file; the source is marked as `user` and `config_trace()` shows a timestamp. Note that `reload_config()` discards these overrides.

```python
from darwin_config import set_config, get_config

set_config("config.database.host", "127.0.0.1")
assert get_config("config.database.host") == "127.0.0.1"
```

### `try_config(*paths, default=None)`

Return the first **non-None** value in order — handy for fallback chains; missing-path errors are swallowed.

```python
from darwin_config import try_config

timeout = try_config(
    "config.runtime.timeout",   # runtime override
    "config.server.timeout",    # file config
    "config.defaults.timeout",  # fallback
    default=30,
)
```

### `add_config(source, mount=None, values=None, validate=True)`

Append config after initialization: `source` may be a path, a glob string, or a dict. The file's own `mount` directive determines the real mount point. If the passed `mount` differs from the one declared in the file, an **alias** is registered automatically — both paths are readable, and writes go to the same node.

```python
from darwin_config import add_config, get_config, config_trace

add_config("adapters/tushare.yaml")                       # uses the file's mount: adapter.tushare
add_config("adapters/extra/*.json", mount="custom.tushare")  # alias -> adapter.tushare
add_config({"mount": "runtime.cache", "ttl": 60})        # pass a dict directly

assert get_config("adapter.tushare.auth.token") == get_config("custom.tushare.auth.token")
print(config_trace("adapter.tushare.auth.token"))        # trace the source file and mount point
```

### `add_alias(alias, target)`

Give an existing path a semantic name, or a compatibility name during a migration. Reads and writes through the alias hit the target node. The target may not exist yet — it is resolved on read (same as `${root.xxx}`).

```python
from darwin_config import add_alias, init_config, get_config, set_config

init_config(files=["settings.yaml"], mount="config")
add_alias("primary", "config.database")

get_config("primary.host")       # same as config.database.host
set_config("primary.host", "x")  # the original path changes too
```

**Other APIs**: `reload_config()` (replays all `add_config` calls), `get_meta(path)`, `config_trace(path)`, `get_trace_summary()`, `get_aliases()` / `has_alias()`, `ConfigLoader` (an independent instance that avoids global state), `Schema` / `FieldRule` / `create_schema` / `validate_config` / `validate_and_fill`, and the exceptions `ConfigError` / `ConfigValidationError` / `ConfigPathNotFoundError` / `ConfigCircularReferenceError` / `ConfigMountError` — all importable directly from `darwin_config`.

Only the APIs developers actually use are exported at the top level; there are no no-op compatibility functions or environment-variable management helpers.

---

## 4. Features in detail

### 4.1 Aliases

Not "a copy of the value" but a jump pointer inside the node tree: reads and writes target the same node. Supports **longest-prefix matching** and cycle detection. Use `get_aliases()` / `has_alias()` to inspect existing aliases.

Two ways to create one:

```python
init_config(files=["settings.yaml"], mount="config")

# 1) Explicit registration (recommended): give an existing path a semantic name
add_alias("primary", "adapter.tushare")

# 2) Implicit during mounting: a passed mount differing from the file's mount registers an alias
add_config("adapter.yaml", mount="custom.tushare")

get_config("primary.auth.token")      # same as adapter.tushare.auth.token
set_config("primary.auth.token", "x") # the original path becomes x as well
```

Aliases share the same duplicate-name check as `add_config`; a circular reference raises `ConfigCircularReferenceError` on read.

### 4.2 Schema validation and defaults

Supports `type` (string/integer/float/boolean/array/object), `required`, `default`, `choices`, `min/max`, `pattern`, custom validators, and `message`. Rules can be inline or in an external JSON/YAML file (which may itself `import` other rule files). Validation failures raise `ConfigValidationError`, whose `errors` is a field-keyed dict.

```python
from darwin_config import Schema, create_schema, validate_and_fill

schema = create_schema({
    "host": {"type": "string", "required": True},
    "port": {"type": "integer", "default": 8080, "min": 1, "max": 65535},
})
cfg = validate_and_fill({"host": "localhost"}, schema)
# {'host': 'localhost', 'port': 8080}
```

> Note the pipeline order is **schema → environment variables**: if a field is written as `"${PORT}"` but the schema declares `integer`, validation sees a string and reports a type error. Use `%{calc: ${PORT}}` when strict typing is required, or declare the field as `string` in the schema.

### 4.3 References: `this` vs `root`

- `${this.xxx}` is an **in-file reference**, resolved at load time; references can chain (`a -> b -> c`) and can be embedded in the middle of a string.
- `${root.xxx}` is a **global reference**, resolved from the root node at runtime, so it can reference other files — even config appended later via `add_config`.
- The two can be mixed without interference; circular references raise `ConfigCircularReferenceError`.

### 4.4 Environment variables

The library only **consumes** environment variables; it never modifies the caller's process environment. Reference them in config with `${VAR}` / `${VAR:default}`; for explicit injection use `init_config(values={...})`, which takes precedence over `os.environ`. The library provides no helpers for reading or writing environment variables.

```python
init_config(files=["settings.yaml"], mount="config", values={"DB_HOST": "localhost"})
```

### 4.5 Source tracing

Every leaf node carries `source` / `mount` / `timestamp` / `overrides` metadata:

```python
config_trace("config.database.host")
# config.database.host → settings.yaml (mount: config) (overridden by: runtime.json)
get_trace_summary()   # {'settings.yaml': 12, 'runtime.json': 3, 'user': 1}
```

### 4.6 Three ways around reserved-word collisions

`import/merge/mount/schema` are reserved words, but they won't get in the way of normal business fields:

1. **Scope**: `mount` / `schema` are recognized only at the top level of a file; a nested `database.schema: "public"` is an ordinary field.
2. **Escaping**: `~import: [1, 2]` and `~schema: {name: mysql}` are unescaped into ordinary fields at the end of the pipeline.
3. **Remapping**: `init_config(..., directives={"import": "cfg_import"})` renames a directive globally; the original `import` then becomes an ordinary field again.

### 4.7 Standalone loader

When you don't want process-level global state:

```python
from darwin_config import ConfigLoader

loader = ConfigLoader(config_files=["a.yaml", "b.yaml"], mount="cfg", validate=True)
data = loader.load()          # {'cfg': {...}}, no global node tree involved
```

---

## 5. Recursive merge rules

There are three merge points in the library, all with consistent semantics: **dicts merge recursively, non-dicts are overwritten, and the later writer wins**.

### 5.1 The `import` directive — cross-file layering

```
app.yaml   import: [common.yaml]        ┐
common.yaml import: base.yaml           ├─ base first, then common, then app itself
base.yaml  {server: {host, port, timeout}} ┘
```

Result: `server = {host: <base>, port: <common>, timeout: <app>}` — only the keys that appear are overridden; the rest are inherited.
Multiple `import` entries merge in **array order** (later overrides earlier); the current file's top-level fields override everything last. This happens recursively at **any nesting level**, so `database: {import: "db.yaml"}` works too.

### 5.2 The `merge` directive — in-file object templates

```yaml
defaults: { timeout: 30, retry: 3, headers: { Accept: json } }
job:
  merge: ${this.defaults}
  timeout: 60
# -> {timeout: 60, retry: 3, headers: {Accept: json}}
```

A `merge` source may be a string or an array (multiple sources merged in order) and must be in `${this.xxx}` form. A missing source only logs a warning. Source objects may themselves contain `merge`, which is expanded recursively first.

### 5.3 `add_config` / multiple files — node-tree merge

- Leaf over leaf: the new value wins; the old `source` is recorded in `overrides` and the timestamp is updated
- Leaf against branch: the branch wins (it is not flattened by a scalar)
- Branch against branch: **recursive key-by-key merge**, keys that don't appear are retained
- Alias nodes are skipped and never merged
- Multiple `add_config` calls follow call order; later wins. `set_config` is the highest-priority runtime override

**Overall precedence (low → high)**:
`imported files (left → right)` → `current file's own fields` → `schema defaults (fill gaps only)` → `later files in files` → `add_config additions` → `set_config runtime settings`

> `None` is a valid value and overrides the old one rather than being ignored; `reload_config()` rebuilds from files and replays all `add_config` calls, which clears `set_config` runtime overrides.

---

## 6. Tests

```bash
pip install -e '.[yaml,test]'
pytest tests -q
```

Tests are split into `tests/unit/` (individual modules: utilities, node tree, Schema, processor, etc.) and `tests/integration/` (multi-file layering, mixed formats, end-to-end API flows), plus feature-oriented regression tests.

## 7. License

MIT
