# examples/ 配置样本索引

[English](README.md) · 简体中文

每种场景都提供 **JSON、YAML、TOML 三份等价配置**。路径全部相对于样本文件自身解析，可直接运行：

```bash
# 从仓库根目录
PYTHONPATH=src py -3.12 examples/demo.py
# 安装包后
python examples/demo.py
```

| 场景 | JSON | YAML | TOML | 演示能力 |
| --- | --- | --- | --- | --- |
| 基础加载 | `json/01-basic.json` | `yaml/01-basic.yaml` | `toml/01-basic.toml` | 嵌套结构、`${VAR:default}` |
| 分层导入 | `json/layered/{base,common,app}.json` | `yaml/layered/{base,common,app}.yaml` | `toml/layered/{base,common,app}.toml` | `import` 链 + 递归深度合并 |
| 模板合并 | `json/03-merge.json` | `yaml/03-merge.yaml` | `toml/03-merge.toml` | `merge` 复用同文件对象、多模板 |
| 内联校验 | `json/04-schema-inline.json` | `yaml/04-schema-inline.yaml` | `toml/04-schema-inline.toml` | 类型/必填/默认值/范围/枚举 |
| 外部 Schema | `json/05-schema-external.json` + `schema-*.json` | `yaml/05-schema-external.yaml` + `schema-*.yaml` | `toml/05-schema-external.toml` + `schema-*.toml` | 外部 schema 文件内部再 `import` |
| 表达式 | `json/06-expressions*.json` | `yaml/06-expressions*.yaml` | `toml/06-expressions*.toml` | `this` 链式引用、`root` 跨文件、`calc` 算术 |
| 保留字转义 | `json/07-escape.json` | `yaml/07-escape.yaml` | `toml/07-escape.toml` | `~import` / `~schema` 变回业务字段 |
| 挂载与别名 | `json/08-mount-adapter.json` | `yaml/08-mount-adapter.yaml` | `toml/08-mount-adapter.toml` | `mount` + `add_config` + 别名 + 追溯 |

## YAML 书写注意

1. `%{calc: ...}` **必须加引号**：否则 YAML 把 `: ` 当映射分隔符。
2. flow sequence 中的 `${...}` **必须加引号**：`merge: ["${this.templates.http}"]`，裸写 `[${this.x}]` 会被当成映射起始符而解析失败。
3. 块标量中的裸写是安全的：`url: ${this.host}/v1`。
4. `~import` / `~schema` 这类转义键在 YAML 中无需引号。

## TOML 书写注意

1. 根级键必须写在任何 `[table]` **之前**；写在 `[schema]` 之后的键属于该表。若想平铺，可用内联表（`schema = { port = { type = "integer" } }`）。
2. `~` 转义键必须**加引号**：`"~import" = [...]`——TOML 裸键不允许 `~`。
3. TOML 原生日期/时间解析为 Python `datetime`/`date`，可用 `type = "datetime"` / `"date"` 校验。
4. TOML 没有 `null`，用省略字段表示「无值」。
5. 读取 TOML 无需依赖（`tomllib` 在标准库中）；写入需 `pip install darwin-config[toml]`。
