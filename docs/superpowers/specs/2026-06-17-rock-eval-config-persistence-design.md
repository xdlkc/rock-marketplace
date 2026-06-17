# rock-eval 配置持久化设计

> 日期：2026-06-17
> 目标：优化 rock-eval 流程 —— run/retry 时先把用户配置保存到本地 JSON 文件，再支持根据 JSON 文件跑回归。

## 1. 背景与现状

`scripts/regression.py`（2097 行）的 `run` / `retry` 子命令通过 argparse 收集参数，全部以 `args`（argparse Namespace）作为鸭子类型 `config` 对象，沿 `cmd_run` → `run_window` → `run_single_task` → `build_rc_cmd` 一路透传，最终拼成 `rc agent run` 命令行。

当前问题：配置只存在于一次命令调用的内存里，无法保存、复用、追溯。用户想复用某次回归的完整参数（含 image/cluster/ee/set 等透传项）只能手动重打一遍。

## 2. 需求（已与用户确认）

1. **保存触发**：两者都要。
   - 每次 run/retry **自动**保存一份到 `configs/{experiment_id}.json`（用于追溯）。
   - 同时支持 `--save-config <path>` 显式另存到自定义路径（用于复用模板）。
2. **读取**：`--from-config <path>` 加载 JSON 作为基底，**CLI 显式传的参数覆盖** JSON 同名字段（JSON 为主，CLI 覆盖）。
3. **保存字段**：全部 run 参数（bench/dataset/split/agent/concurrency/window-size + 全部透传参数 + tasks + poll-*）。不存 experiment_id（运行时生成）。
4. **范围**：`run` 和 `retry` 两个子命令都支持。

## 3. 约束（来自现有代码）

| 约束 | 说明 |
|------|------|
| `--config` 已被占用 | 它是 rc 的 JobConfig YAML 透传 flag（dest=`config`），新 flag 必须改名。采用 `--save-config` / `--from-config`。 |
| `required=True` 参数 | `--bench`、`--agent`、`--concurrency`、`--window-size` 当前 required。`--from-config` 模式下这些值来自 JSON，CLI 不应再强制要求 → 需放宽。 |
| `--pre/--no-pre` | store_true/store_false 一对，默认 `True`。sentinel 机制需特别处理。 |
| `--ee/--set` | `action="append"`，默认 `[]`，多次累加。 |
| config 鸭子类型 | 全程 `getattr(config, name, default)`。normalize 后的 Namespace 与现有 `build_rc_cmd` / `init_result_json` 完全兼容，下游零改动。 |
| 代码风格 | 全中文注释、`print`、无类型注解、无 dataclass、JSON 用 `json.dump(..., indent=2, ensure_ascii=False)`。不引入 yaml。 |

## 4. 方案：sentinel 默认值 + 合并层覆盖（方案 A）

### 4.1 sentinel 机制

引入模块级常量：

```python
_UNSET = object()  # 占位符，表示「CLI 未显式传入」
```

把所有「可覆盖 / 可保存」的参数默认值改为 `_UNSET`（除 `--ee/--set` 这类 append 的列表，以及 `--pre/--no-pre` 见 4.3）。

> 注意：`--resume`、`--async-mode`、`--same-experiment` 这类纯 store_true 的行为开关不参与 save/from-config（它们是「本次调用」的临时行为，不是可复现配置），保持原默认。

### 4.2 合并层（`--from-config` 覆盖逻辑）

新增函数 `apply_config(args, config_path)`，在 `parse_args` 之后、dispatch 之前调用：

```
加载 JSON → cfg
对每个可覆盖字段 f：
    if getattr(args, f) is _UNSET:        # CLI 没传
        setattr(args, f, cfg[f])          # 用 JSON 的值
    else:                                  # CLI 显式传了
        保留 args.f（覆盖 JSON）
```

`--ee/--set`（append 列表）单独处理：CLI 传了任何 `--ee` 就完全用 CLI 的列表（不与 JSON 合并，避免语义混乱）；CLI 一个都没传则用 JSON 的列表。

### 4.3 `--pre/--no-pre` 处理

`--pre` 默认 `True` 本身就难以区分「用户显式要预发」vs「默认值」。sentinel 化方式：

- `--pre` 的 `default` 改为 `_UNSET`（保持 `action="store_true"`，store_true 在 flag 出现时置 `True`）。
- `--no-pre` 保持 `action="store_false", dest="pre"`，出现时置 `False`。
- 这样：传 `--pre` → `True`；传 `--no-pre` → `False`；都不传 → `_UNSET`。
- normalize 阶段：`_UNSET` → `True`（保持现有「默认启用预发」行为）。

### 4.4 normalize（还原真实默认值）

新增 `normalize_args(args)`：把所有仍是 `_UNSET` 的字段还原成真实默认值，确保下游鸭子类型代码拿到合法值：

| 字段 | 默认值 |
|------|--------|
| `bench` / `agent` | 无默认 —— 若仍 `_UNSET` 说明 CLI 与 JSON 都没给 → 报错退出（保持 required 语义） |
| `dataset` / `split` / `image` / `cluster` / `model` / `api_key` / `namespace` / `cpus` / `memory` / `companion` / `config` / `user_id` / `base_url` | `""` |
| `concurrency` | `1` |
| `window_size` | `0` |
| `tasks` | `""` |
| `poll_interval` | `10` |
| `poll_timeout` | `600` |
| `pre` | `True` |
| `ee` / `set` | `[]` |

### 4.5 required 参数放宽

`add_rc_args` / `add_run_args` 中 `--bench`、`--agent`、`--concurrency`、`--window-size` 的 `required=True` 改为 `required=False`（默认 `_UNSET`）。真正的「必传」校验由 `normalize_args` 在运行时兜底（值仍为 `_UNSET` 则报错）。这同时让 `--from-config` 模式合法。

> 不从 JSON 加载时（纯 CLI 调用），若用户漏传 `--bench` 等，会在 normalize 阶段报清晰错误，行为等价于原来的 required。

### 4.6 配置文件读写函数

```python
# 可保存字段清单（顺序即 JSON 字段顺序，便于人读）
SAVE_FIELDS = [
    "bench", "dataset", "split", "agent",
    "image", "cluster", "model", "api_key",
    "ee", "set", "pre", "namespace", "cpus", "memory",
    "companion", "config", "async_mode", "user_id", "base_url",
    "concurrency", "window_size", "tasks",
    "poll_interval", "poll_timeout",
]

def save_config(args, path):
    """把 normalize 后的 args 序列化为 JSON 写到 path。"""
    data = {f: getattr(args, f) for f in SAVE_FIELDS}
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"配置已保存: {path}")

def load_config(path):
    """读取 JSON 配置文件。"""
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def apply_config(args, config_path):
    """--from-config：用 JSON 填充未显式传入的字段，CLI 显式值覆盖。"""
    cfg = load_config(config_path)
    for f in SAVE_FIELDS:
        if f not in cfg:
            continue
        cur = getattr(args, f, _UNSET)
        if cur is _UNSET:
            setattr(args, f, cfg[f])
        # ee/set：CLI 传了非空列表则保留（覆盖 JSON）；空列表（默认）→ 用 JSON
        # 注意 _UNSET 与 [] 的区分见 4.7
    print(f"已加载配置: {config_path}")
```

### 4.7 `ee/set` 的 _UNSET 处理

`action="append"` 默认是 `[]`，无法用 `_UNSET`。用 `default=_UNSET`：argparse 对 append action 在 flag 未出现时保留 default（即 `_UNSET`），出现时从 `[]` 开始 append。验证方式见第 7 节。

- CLI 没传任何 `--ee` → `args.ee is _UNSET` → 用 JSON 的列表。
- CLI 传了 `--ee A --ee B` → `args.ee == ["A","B"]` → 保留，覆盖 JSON。
- normalize：仍是 `_UNSET` → 还原为 `[]`。

## 5. 数据流（最终）

```
sys.argv
   │
   ▼
parse_args()  →  args（可覆盖字段默认 _UNSET；required 放宽）
   │
   ├─ args.from_config 存在 → apply_config(args, args.from_config)
   │      （JSON 填充 _UNSET 字段；CLI 非 _UNSET 字段覆盖 JSON）
   │
   ▼
normalize_args(args)  （_UNSET → 真实默认；bench/agent/concurrency/window_size 仍 _UNSET 则报错）
   │
   ▼
dispatch[command](args)  →  cmd_run / cmd_retry（原流程不变）
   │
   ├─ init_result_json(...) 之后：
   │    save_config(args, f"./configs/{experiment_id}.json")     ← 自动存
   │    if args.save_config: save_config(args, args.save_config)  ← 显式存
   │
   └─ dispatch 任务（build_rc_cmd 用 normalize 后的 args，鸭子类型兼容）
```

## 6. 改动落点

### 6.1 argparse（`add_rc_args` / `add_run_args` / retry 注册段）

- 新增 `--from-config`、`--save-config` 两个 flag（注册到 run 和 retry 的 parser；retry 不需要 `--api-key` 重复，保持与现有 `add_rc_args(p_retry)` 一致）。
- 可覆盖字段 default 改 `_UNSET`（含 `--bench/--agent/--concurrency/--window-size` 的 `required=False`）。
- `--ee/--set` 用 `default=_UNSET`。
- `--pre` default 改 `_UNSET`。
- `--resume`、`--async-mode`、`--same-experiment` 等行为开关**不动**。

### 6.2 `main()` 流程

```python
def main():
    args = parse_args()
    if getattr(args, "from_config", None):
        apply_config(args, args.from_config)
    normalize_args(args)               # 仅 run/retry 有可覆盖字段；report/sync/diagnose 无害（getattr 默认）
    dispatch = {...}
    dispatch[args.command](args)
```

> `normalize_args` 对 report/sync/diagnose 应是 no-op（这些 args 没有可覆盖字段；用 `getattr(args, f, None) is _UNSET` 判断，非 _UNSET 不动）。

### 6.3 `cmd_run` / `cmd_retry` 插入保存

- `cmd_run`：在 `init_result_json(...)`（446 行）之后插入自动存 + 显式存。
- `cmd_retry`：在 `init_result_json(...)`（1924 行）之后插入自动存 + 显式存。

两处用同一逻辑（可抽一个小 helper `_persist_configs(args, experiment_id)`）。

### 6.4 JSON Schema 示例（`configs/{experiment_id}.json`）

```json
{
  "bench": "harborframework/java100",
  "dataset": "aone-bench/java100",
  "split": "test",
  "agent": "claude-code",
  "image": "",
  "cluster": "",
  "model": "",
  "api_key": "",
  "ee": [],
  "set": [],
  "pre": true,
  "namespace": "",
  "cpus": "",
  "memory": "",
  "companion": "",
  "config": "",
  "async_mode": false,
  "user_id": "",
  "base_url": "",
  "concurrency": 5,
  "window_size": 0,
  "tasks": "",
  "poll_interval": 10,
  "poll_timeout": 600
}
```

## 7. 验证计划（无外部依赖，本地即可）

`rc` / `rockcli` 在沙箱不可用，但新增逻辑全是纯 Python 数据处理，可脱机验证：

1. **save 单测**：构造 args Namespace → `save_config` → 读回 JSON，断言字段齐全、值正确。
2. **apply_config 覆盖单测**：JSON 里 concurrency=5、bench=X；CLI 传 `--concurrency 10`（其余 _UNSET）→ apply 后 concurrency=10、bench=X（来自 JSON）。
3. **ee/set sentinel 单测**：验证 `default=_UNSET` + `action="append"` 在「不传」时为 `_UNSET`、「传 N 次」时为长度 N 的列表。
4. **pre sentinel 单测**：不传→`_UNSET`；`--pre`→`True`；`--no-pre`→`False`；normalize 后 `_UNSET`→`True`。
5. **normalize 报错单测**：bench/agent 仍 `_UNSET` → 报错退出。
6. **端到端冒烟**（mock build_rc_cmd 或 dry-run）：
   - `run --bench B --agent A --dataset D --split S --concurrency 1 --window-size 0 --tasks t1` → 生成 `configs/*.json` 且 build_rc_cmd 命令正确。
   - `run --from-config configs/xxx.json` → 不再要求 `--bench` 等，行为与原 run 一致。

> 真正调 `rc` 的端到端留给用户在真实环境跑（SKILL.md 已有 oracle/nop smoke 流程）。

## 8. 文档更新

- **SKILL.md**：第 1 节（Run）和第 5 节（Retry）各补一段「配置持久化」说明：`--save-config` / `--from-config`、自动存到 `configs/`、CLI 覆盖语义、JSON 字段。
- **references/sop.md**：在典型工作流里补「保存 / 复用配置」用法示例。

## 9. 不做的事（YAGNI）

- 不引入 YAML。
- 不做 JSON schema 版本字段（v1 隐含）。
- 不为 report/sync/diagnose 加 from-config（它们没有可复现的回归配置语义）。
- 不做配置继承 / 多文件 merge / include。
- 不存 experiment_id（运行时按 dataset_short + 时间戳生成，保持现有行为）。

---

## 10. 后续改动：窗口语义改为滑动并发（同日）

### 问题
原 `run_window` + `cmd_run` 的分批循环实现的是**批 barrier**：按 `window_size` 切批，每批
用 `ThreadPoolExecutor(max_workers=concurrency)` 跑，`with` 退出时 join 整批，再开下一批。
当 `concurrency >= window_size` 时表现为「跑满 N → 等全部结束 → 再跑下 N」，中间有空窗，
与「全局维持 N 并发」的预期不符。

### 方案（方案 A：window_size = 全局并发上限）
- `--window-size` 重定义为**全局并发上限（滑动窗口）**：始终维持 N 个任务在飞，一个完成
  立刻补充下一个，无分批 barrier。
- `--concurrency` 降级为**兼容同义词**；两者同时给定时取较小值（`resolve_concurrency`）。
- `window_size <= 0` 表示不限制（= 任务总数，全部并行）。
- `concurrency` 不再必填（默认 None，仅看 window_size）。

### 实现
- 新增 `resolve_concurrency(config, total)`：`cap = window_size<=0 ? total : window_size`，
  若 `concurrency` 非空则 `cap = min(cap, concurrency)`，最后 `max(1, cap)`。
- `run_window` 改为：`max_workers = resolve_concurrency(...)`，全部任务一次性 submit 给单个
  `ThreadPoolExecutor`——线程池天然在任务完成时复用线程调度下一个，即滑动窗口。
- `cmd_run` / `cmd_retry`：删除分批 `while offset < total` 循环，改为单次
  `run_window(...全部任务...)`；banner 由「并发数/窗口大小」两行合并为「并发上限」一行。
- `normalize_args`：`concurrency` 缺省 → None；`window_size` 缺省 → 0（不报错必传）。

### 验证（脱机，mock rc）
- window_size=2 / 5 任务：峰值并发=2、耗时≈⌈5/2⌉×单任务、t3 在 t1/t2 结束瞬间启动（无 barrier）。
- window_size=0：全部 5 并行。
- window_size=10 + concurrency=3：实际上限 3。
- cmd_run / cmd_retry 端到端：banner 显示「并发上限」、无「窗口 #N」分批打印、配置正常保存。

