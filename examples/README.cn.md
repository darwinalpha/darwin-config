# examples/ 配置样本索引

[English](README.md) · 简体中文

每种场景都提供 **JSON 与 YAML 两份等价配置**。路径全部相对于样本文件自身解析，可直接运行：

```bash
# 从仓库根目录
PYTHONPATH=src py -3.12 examples/demo.py
# 安装包后
python examples/demo.py
```

| 场景 | JSON | YAML | 演示能力 |
| --- | --- | --- | --- |
| 基础加载 | `json/01-basic.json` | `yaml/01-basic.yaml` | 嵌套结构、`${VAR:default}` |
| 分层导入 | `json/layered/{base,common,app}.json` | `yaml/layered/{base,common,app}.yaml` | `import` 链 + 递归深度合并 |
| 模板合并 | `json/03-merge.json` | `yaml/03-merge.yaml` | `merge` 复用同文件对象、多模板 |
| 内联校验 | `json/04-schema-inline.json` | `yaml/04-schema-inline.yaml` | 类型/必填/默认值/范围/枚举 |
| 外部 Schema | `json/05-schema-external.json` + `schema-*.json` | `yaml/05-schema-external.yaml` + `schema-*.yaml` | 外部 schema 文件内部再 `import` |
| 表达式 | `json/06-expressions*.json` | `yaml/06-expressions*.yaml` | `this` 链式引用、`root` 跨文件、`calc` 算术 |
| 保留字转义 | `json/07-escape.json` | `yaml/07-escape.yaml` | `~import` / `~schema` 变回业务字段 |
| 挂载与别名 | `json/08-mount-adapter.json` | `yaml/08-mount-adapter.yaml` | `mount` + `add_config` + 别名 + 追溯 |

## YAML 书写注意

1. `%{calc: ...}` **必须加引号**：否则 YAML 把 `: ` 当映射分隔符。
2. flow sequence 中的 `${...}` **必须加引号**：`merge: ["${this.templates.http}"]`，裸写 `[${this.x}]` 会被当成映射起始符而解析失败。
3. 块标量中的裸写是安全的：`url: ${this.host}/v1`。
4. `~import` / `~schema` 这类转义键在 YAML 中无需引号。
