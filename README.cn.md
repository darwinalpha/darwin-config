# darwin-config

[English](README.md) · 简体中文

分层、可递归的 JSON / YAML 配置加载器：一个文件里写清「从哪来、怎么合、怎么校验、怎么引用」，剩下交给库。

- **核心零第三方依赖**；YAML 为可选增强
- 一套 DSL 同时搞定：分层导入、模板合并、环境变量、文件内/跨文件引用、算术表达式、Schema 校验
- **小而明确的 API**：加载、读取、覆盖、别名、校验与追溯，没有多余的状态管理函数

```bash
pip install darwin-config              # JSON 开箱即用
pip install 'darwin-config[yaml]'      # 追加 YAML 支持
```

Python ≥ 3.12。

---

## 1. 一眼看懂：配置文件长什么样

同一份配置，JSON / YAML 等价，指令都是**裸关键字** `import` / `merge` / `mount` / `schema`：

**`settings.yaml`**

```yaml
import:                          # 1) 先导入基础层，可多个，后面的覆盖前面的
  - base.yaml
schema:                          # 2) 校验 + 自动补默认值（下面的 port 没写，自动补 5432）
  database.host: { type: string, required: true }
  database.port: { type: integer, default: 5432, min: 1, max: 65535 }

database:
  host: ${DB_HOST:localhost}     # 3) 环境变量：values > 环境变量 > 默认值
  # port 由 schema 补上
  dsn: "postgresql://${this.database.host}:${this.database.port}/app"  # 4) 文件内引用
  pool:
    merge: ${this.defaults.pool} # 5) 复用本文件其它对象作为模板
    max: 50

# 模板对象（不挂载到最终配置以外的地方，仅作为 merge 源）
defaults:
  pool: { min: 1, max: 10, timeout: 30 }

app:
  retry: 3
  interval: 2
  budget: "%{calc: ${this.app.retry} * ${this.app.interval} }"  # 6) 算术（YAML 中加引号）
```

```python
from darwin_config import init_config, get_config

init_config(files=["settings.yaml"], mount="config", validate=True)

get_config("config.database.dsn")   # 'postgresql://localhost:5432/app'
get_config("config.database.pool")  # {'min': 1, 'max': 50, 'timeout': 30}
get_config("config.app.budget")     # 6
```

**等价的 JSON 版**（`%{calc: ...}` 无需引号）：

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

> `examples/` 下有 8 组 JSON/YAML 对照样本和一个可运行演示脚本，先跑 `PYTHONPATH=src py -3.12 examples/demo.py` 就能看到全部能力。

---

## 2. 语法速查

| 写法 | 含义 | 时机 |
| --- | --- | --- |
| `import: "base.yaml"` / `import: [...]` | 导入其它配置，相对当前文件解析，可嵌套；后导入的覆盖先导入的，当前文件覆盖所有导入 | 加载期 |
| `merge: ${this.templates.http}` / `[...]` | 把同文件其它对象作为模板深度合并进当前对象；当前对象字段优先 | 加载期 |
| `mount: adapter.tushare` | 声明文件挂载点（仅顶层，`add_config` 时生效） | 加载期 |
| `schema: {...}` / `schema: "rules.json"` | 校验规则，内联或外部文件（仅顶层；外部文件内部还支持 `import`） | 加载期，早于环境变量替换 |
| `${this.a.b}` | 文件内引用，可链式引用其它引用 | 加载期 |
| `${root.a.b}` | 全局配置树引用，可跨文件；**运行期读取时解析** | 运行期 |
| `${VAR}` / `${VAR:default}` | 环境变量；优先级 `values` > `os.environ` > 默认值，无默认值且缺失会报错 | 加载期（运行时残留的由节点再解析一次） |
| `%{calc: expr}` | 受限算术，仅允许 `+ - * / // % **` 与白名单函数（`abs/min/max/round/sum/len/int/float/str/bool`） | 运行期 |
| `~import` / `~schema` 等 | `~` 前缀把保留字转义为普通业务字段（流水线末尾统一脱壳） | 加载期 |
| `{param}` | 业务模板占位符，原样保留，不会被环境变量替换 | — |

**YAML 两个坑**（JSON 无此问题）：

1. `%{calc: ...}` 必须加引号：`total: "%{calc: ${this.a} * 2}"`，否则 `: ` 被 YAML 当成映射分隔符。
2. flow sequence 里的 `${...}` 必须加引号：`merge: ["${this.tpl}"]`，裸写 `[${this.tpl}]` 中 `{` 会被当成映射起始符而解析失败。块标量里裸写安全：`url: ${this.host}/v1`。

---

## 3. 五个核心 API 实用案例

### `init_config(files, mount="", values=None, validate=False, base_dir=None, directives=None)`

初始化全局配置系统：展开 glob、按文件顺序加载、合并、建立节点树。**每次调用都会重置此前状态**。

```python
from darwin_config import init_config

# 多文件：后面的文件覆盖前面的；glob 与 ${VAR} 路径变量均可用
init_config(
    files=["config/base.yaml", "config/env/${APP_ENV:dev}/*.json"],
    mount="config",                    # 所有内容挂到 config.*，留空则挂在根
    values={"APP_ENV": "prod"},        # 注入变量，优先级高于环境变量
    validate=True,                     # 开启 schema 校验与默认值填充
    base_dir="config",                 # 相对路径基准，默认 cwd
    directives={"import": "cfg_import"},  # 可选：重命名保留字
)
```

### `get_config(path="", default=None, raise_on_not_found=False)`

读取配置；整串 `${root.xxx}` 表达式在读取时才解析，所以可以引用「后加入」的配置。

```python
from darwin_config import get_config, ConfigPathNotFoundError

get_config("config.database.host")                    # 'localhost'
get_config("config.database.timeout", default=30)     # 缺失时返回默认值
get_config("config.database")                         # 返回整棵子树（dict）
get_config()                                          # 返回全部已解析配置
get_config("config.missing", raise_on_not_found=True) # 抛 ConfigPathNotFoundError
```

### `set_config(path, value)`

运行时覆盖，不写回文件；来源被标记为 `user`，`config_trace()` 可看到时间戳。注意 `reload_config()` 会清除这类覆盖。

```python
from darwin_config import set_config, get_config

set_config("config.database.host", "127.0.0.1")
assert get_config("config.database.host") == "127.0.0.1"
```

### `try_config(*paths, default=None)`

按顺序取第一个**非 None** 的值，适合做配置回退链；路径异常会被吞掉。

```python
from darwin_config import try_config

timeout = try_config(
    "config.runtime.timeout",   # 运行时设置
    "config.server.timeout",    # 文件配置
    "config.defaults.timeout",  # 兜底
    default=30,
)
```

### `add_config(source, mount=None, values=None, validate=True)`

在初始化之后继续追加配置：`source` 可以是路径、glob 字符串或字典；文件内的 `mount` 指令决定真实挂载点。若传入的 `mount` 与文件声明不同，会自动注册**别名**，两个路径都能读、写会同步到同一节点。

```python
from darwin_config import add_config, get_config, config_trace

add_config("adapters/tushare.yaml")                       # 用文件内 mount: adapter.tushare
add_config("adapters/extra/*.json", mount="custom.tushare")  # 别名 → adapter.tushare
add_config({"mount": "runtime.cache", "ttl": 60})        # 直接传字典

assert get_config("adapter.tushare.auth.token") == get_config("custom.tushare.auth.token")
print(config_trace("adapter.tushare.auth.token"))        # 追溯来源文件与挂载点
```

### `add_alias(alias, target)`

给已有路径起一个语义化名字，或做迁移期的兼容名。别名读写都指向目标节点；目标可以暂时不存在，读取时才解析（与 `${root.xxx}` 一致）。

```python
from darwin_config import add_alias, init_config, get_config, set_config

init_config(files=["settings.yaml"], mount="config")
add_alias("primary", "config.database")

get_config("primary.host")       # 等价 config.database.host
set_config("primary.host", "x")  # 原路径同步生效
```

**其余 API**：`reload_config()`（重放所有 `add_config`）、`get_meta(path)`、`config_trace(path)`、`get_trace_summary()`、`get_aliases()` / `has_alias()`、`ConfigLoader`（不使用全局状态的独立实例）、`Schema` / `FieldRule` / `create_schema` / `validate_config` / `validate_and_fill`，以及异常 `ConfigError` / `ConfigValidationError` / `ConfigPathNotFoundError` / `ConfigCircularReferenceError` / `ConfigMountError` —— 均可从 `darwin_config` 直接导入。

顶层只导出上述开发者真正会用到的 API，没有空操作兼容函数或环境变量管理函数。

---

## 4. 特色功能详解

### 4.1 别名（alias）

不是「复制一份值」，而是节点树里的跳转指针：读写都指向同一个目标，支持**最长前缀匹配**与循环检测。`get_aliases()` / `has_alias()` 可查询现有别名。

两种产生方式：

```python
init_config(files=["settings.yaml"], mount="config")

# 1) 显式注册（推荐）：给已有路径起语义化名字
add_alias("primary", "adapter.tushare")

# 2) 挂载时隐式产生：传入的 mount 与文件内 mount 不同即注册别名
add_config("adapter.yaml", mount="custom.tushare")

get_config("primary.auth.token")      # 等价 adapter.tushare.auth.token
set_config("primary.auth.token", "x") # 写入后原路径也变成 x
```

别名与 `add_config` 共用同一套重名检查；循环引用会在读取时抛 `ConfigCircularReferenceError`。

### 4.2 Schema 校验与默认值

支持 `type`（string/integer/float/boolean/array/object）、`required`、`default`、`choices`、`min/max`、`pattern`、`custom validator`、`message`。规则可以内联，也可以放在外部 JSON/YAML 文件里（外部文件自身还能 `import` 其它规则文件）。校验失败抛 `ConfigValidationError`，errors 是按字段聚合的字典。

```python
from darwin_config import Schema, create_schema, validate_and_fill

schema = create_schema({
    "host": {"type": "string", "required": True},
    "port": {"type": "integer", "default": 8080, "min": 1, "max": 65535},
})
cfg = validate_and_fill({"host": "localhost"}, schema)
# {'host': 'localhost', 'port': 8080}
```

> 注意流水线顺序是 **schema → 环境变量**：若字段写成 `"${PORT}"` 而 schema 声明 `integer`，校验阶段看到的是字符串，会报类型错误。解决办法是严格要求时用 `%{calc: ${PORT}}` 或在 schema 里声明 `string`。

### 4.3 引用体系：`this` vs `root`

- `${this.xxx}` 是**文件内引用**，在加载期解析，可链式（`a → b → c`）也可嵌在字符串中间。
- `${root.xxx}` 是**全局引用**，运行期从根节点解析，所以可以引用别的文件、甚至 `add_config` 追加进来的配置。
- 两者可以混用，互不干扰；循环引用会抛 `ConfigCircularReferenceError`。

### 4.4 环境变量

库只**消费**环境变量，不修改调用方的进程环境。配置中用 `${VAR}` / `${VAR:default}` 引用；需要显式注入时通过 `init_config(values={...})`，其优先级高于 `os.environ`。库本身不提供任何环境变量读写辅助函数。

```python
init_config(files=["settings.yaml"], mount="config", values={"DB_HOST": "localhost"})
```

### 4.5 来源追溯

每个叶子节点都带 `source` / `mount` / `timestamp` / `overrides` 元数据：

```python
config_trace("config.database.host")
# config.database.host → settings.yaml (mount: config) (overridden by: runtime.json)
get_trace_summary()   # {'settings.yaml': 12, 'runtime.json': 3, 'user': 1}
```

### 4.6 保留字冲突的三层解法

`import/merge/mount/schema` 是保留字，但不会妨碍正常业务字段：

1. **作用域**：`mount` / `schema` 只在文件顶层识别，嵌套的 `database.schema: "public"` 是普通字段。
2. **转义**：`~import: [1, 2]`、`~schema: {name: mysql}` 在流水线末尾脱壳为普通字段。
3. **重映射**：`init_config(..., directives={"import": "cfg_import"})` 整体换名；原 `import` 随即变回普通字段。

### 4.7 独立加载器

不想用进程级全局状态时：

```python
from darwin_config import ConfigLoader

loader = ConfigLoader(config_files=["a.yaml", "b.yaml"], mount="cfg", validate=True)
data = loader.load()          # {'cfg': {...}}，不涉及全局节点树
```

---

## 5. 递归合并（recursive merge）规则

库里有三处合并，语义一致：**字典递归、非字典覆盖、后写胜出**。

### 5.1 `import` 指令 —— 跨文件分层

```
app.yaml   import: [common.yaml]        ┐
common.yaml import: base.yaml           ├─ 先 base，再 common，最后 app 自身
base.yaml  {server: {host, port, timeout}} ┘
```

结果：`server = {host: <base>, port: <common>, timeout: <app>}` —— 只覆盖出现的键，没写的键继承下来。
多个 `import` 按**数组顺序**逐个合并（后面的覆盖前面的）；当前文件的顶层字段最后覆盖；该过程递归发生在**任意嵌套层级**，所以 `database: {import: "db.yaml"}` 也成立。

### 5.2 `merge` 指令 —— 同文件对象模板

```yaml
defaults: { timeout: 30, retry: 3, headers: { Accept: json } }
job:
  merge: ${this.defaults}
  timeout: 60
# → {timeout: 60, retry: 3, headers: {Accept: json}}
```

`merge` 源可用字符串或数组（多个源按顺序合并），必须是 `${this.xxx}` 形式；源不存在时只告警不报错。源对象自身也可以带 `merge`，会先递归展开。

### 5.3 `add_config` / 多文件 —— 节点树合并

- 叶子覆盖叶子：新值胜出，旧 `source` 记入 `overrides` 并更新时间戳
- 叶子遇到分支：分支胜出（不会被标量打平）
- 分支遇到分支：**逐键递归**合并，未出现的键保留
- 别名节点跳过，不参与合并
- 多次 `add_config` 按调用顺序，后者胜出；`set_config` 是最高优先级的运行时覆盖

**总优先级（低 → 高）**：
`import 的文件（左→右）` → `当前文件自身字段` → `schema 默认值（仅填空缺）` → `files 列表中靠后的文件` → `add_config 追加内容` → `set_config 运行时设置`

> `None` 是有效值，会覆盖旧值而不会被忽略；`reload_config()` 会从文件重新构建并重放全部 `add_config`，因此会清掉 `set_config` 的运行时覆盖。

---

## 6. 测试

```bash
pip install -e '.[yaml,test]'
pytest tests -q
```

测试分为 `tests/unit/`（工具函数、节点树、Schema、处理器等单模块）与 `tests/integration/`（多文件分层、混合格式、端到端 API 流程），另有按特性组织的回归测试。

## 7. 许可

MIT
