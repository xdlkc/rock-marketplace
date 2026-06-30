# 失败分类体系 — Rock Bench Analysis

本文件定义了在分析 bench 实验失败 job 时使用的标准分类体系，包含每种分类的精确定义、识别方法、典型模式，以及容易混淆的边界情况处理指南。

---

## 分类总览

| 分类 ID | 中文名称 | 核心特征 |
|---------|---------|---------|
| `strategy_error` | 策略错误 | agent 选择了错误的解题路径 |
| `capability_gap` | 能力不足 | agent 理解任务但执行力不足 |
| `misunderstanding` | 理解偏差 | agent 对任务要求产生了误解 |
| `env_issue` | 环境问题 | 沙箱/docker/网络等基础设施异常 |
| `timeout` | 超时 | 执行时间耗尽，任务未完成 |
| `infra_error` | 基础设施错误 | API 层面的崩溃或系统错误 |
| `verifier_issue` | 验证器问题 | 任务实质完成但 verifier 未计分 |
| `partial_completion` | 部分完成 | 完成了部分子任务，reward 在 (0, 1) 之间 |

---

## 1. 策略错误（strategy_error）

### 定义

agent 从一开始或在某个关键决策点选择了错误的解题策略，即使有足够能力执行，这条路也无法通向正确答案。

### 识别方法

- **early commitment**：在 trajectory 的前几步就锁定了一个错误方向，之后所有行动都在这个错误基础上构建
- **错误抽象**：对问题做了不恰当的简化或抽象，导致解法方向性偏差
- **忽视约束**：任务有明确约束（如"不能修改文件 X"），agent 直接违反
- **选错工具**：任务需要 A 工具但 agent 一直使用 B 工具

### 典型模式

```
用户让 agent 修复 bug X
→ agent 误判根因，修复了 bug Y（但 Y 其实是正常逻辑）
→ 最终 verifier 测试失败
```

```
用户要求 agent 实现算法 A（时间复杂度要求 O(n log n)）
→ agent 实现了朴素 O(n²) 版本
→ 性能测试超时
```

### 如何与"能力不足"区分

- **策略错误**：换一种方法 agent **本来可以成功**
- **能力不足**：即使选对了策略，agent 也无法正确执行

---

## 2. 能力不足（capability_gap）

### 定义

agent 正确理解了任务目标，也选择了合理的解题策略，但在执行某个具体步骤时遭遇了模型本身的能力边界——无法生成正确的代码、推理链断裂，或无法处理特定的技术复杂度。

### 识别方法

- **重复尝试同一错误**：agent 多次尝试同一个操作，每次都以相似的方式失败
- **局部推理正确，整体失败**：agent 能描述正确的思路，但代码实现存在系统性错误
- **技术盲点**：面对特定技术（稀有 API、复杂数学、专业领域知识）时完全无措
- **代码生成错误**：生成的代码有语法错误、逻辑错误，且多次修正后仍无法纠正

### 典型模式

```
任务：实现一个复杂的动态规划算法
→ agent 知道要用 DP，也能说出状态转移方程
→ 但实现总有边界条件错误，多次修正后仍然无法通过测试
```

```
任务：修改某个框架的底层配置
→ agent 找到了正确的配置文件
→ 但不了解该框架特定版本的配置格式，多次尝试格式都错误
```

### 如何与"理解偏差"区分

- **能力不足**：agent 说出的思路是对的，但实现出了问题
- **理解偏差**：agent 描述的思路本身就偏离了任务要求

---

## 3. 理解偏差（misunderstanding）

### 定义

agent 对任务的目标、要求或约束产生了错误理解，导致整个执行方向出现偏差。

### 识别方法

- **目标替换**：agent 解决了一个相关但不同的问题（例如修复了类似但不同的 bug）
- **约束遗漏**：任务有明确约束，agent 在执行中忽视了它
- **范围误判**：agent 对任务的输入/输出范围理解有误（例如误以为只需处理正整数）
- **语义歧义处理失误**：任务描述有歧义，agent 选择了错误的解释方向

### 典型模式

```
任务：为函数 foo() 添加单元测试
→ agent 理解为"修改 foo() 使其可测试"
→ 修改了生产代码而没有写测试
```

```
任务：优化查询性能（隐含要求：不改变查询结果）
→ agent 缓存了查询结果（改变了实时性）
→ verifier 检测到结果不一致而失败
```

### 与"策略错误"的区别

- **理解偏差**：agent 解决的是"另一个问题"——它的解法对它所理解的任务是正确的
- **策略错误**：agent 理解了正确的任务，但选错了解决方案

---

## 4. 环境问题（env_issue）

### 定义

任务执行失败的根因在于沙箱、docker 容器、网络、依赖包等基础设施层面，而非 agent 的决策或能力。

### 识别方法

- `exception_info` 包含 `DockerError`、`ContainerError`、`NetworkError`、`TimeoutError`（在 env_setup 阶段）
- `result.json` 的 `environment_setup` 阶段出现异常
- 多个 trial 以相同的基础设施错误失败（说明是系统性环境问题）
- `exception.txt` 中有 DNS 解析失败、镜像拉取失败、端口绑定失败等信息
- agent 的 tool_calls 命令本身是合理的，但返回了"file not found"或权限错误等环境异常

### 典型模式

```
exception: "Docker compose command failed: no such host"
→ 沙箱 DNS 配置问题，agent 无法访问外部服务
→ 与 agent 行为无关
```

```
result.json: environment_setup.duration_sec = 600
→ 镜像拉取超时，trial 还没开始就失败了
```

### 注意

如果只有 1 个 trial 遇到环境问题而其他 trial 正常，更可能是偶发故障（transient error），不应归类为系统性环境问题。多个 trial 同样失败才倾向于 `env_issue`。

---

## 5. 超时（timeout）

### 定义

agent 在 time limit 内没有完成任务，导致强制终止。

### 识别方法

- `exception_info.exception_type` 包含 `Timeout`、`AgentTimeoutError`
- `agent_execution.duration_sec` 接近或等于任务的时间限制上限
- trajectory 的最后几步 agent 仍在正常执行，没有明显的卡顿或无限循环
- verifier 未运行（因为 agent 阶段被强制终止）

### 典型模式

```
任务时间限制：600s
agent_execution.duration_sec = 598
exception_type: AgentTimeoutError
→ agent 在努力工作但时间不够用
```

### 细分

超时可以进一步细分为：

| 子类型 | 特征 |
|--------|------|
| **任务本身耗时过长** | agent 在正常推进但任务复杂度超出时间窗口 |
| **无效循环导致超时** | agent 陷入重复操作消耗时间，本质是策略错误导致超时 |

若超时是由无效循环引起，主分类应标记为 `strategy_error`，同时在分析中注明超时是次级症状。

---

## 6. 基础设施错误（infra_error）

### 定义

由平台层面（非任务沙箱内部）的错误导致失败，如 API 服务不可用、沙箱崩溃、harbor 平台异常等。

### 识别方法

- `exception_info` 包含 `InternalServerError`、`ServiceUnavailable`、`ConnectionError`
- `result.json` 显示 `finished_at = null`（任务从未完成）
- `agent_execution.duration_sec` 极短（< 10s）但没有明显的 agent 行为
- 错误信息指向平台 API（非任务环境内的工具调用）
- 一批任务同时以相同基础设施错误失败（表明是系统性问题）

### 与"环境问题"的区别

| 类型 | 失败发生在 | 典型错误 |
|------|-----------|---------|
| `env_issue` | 任务沙箱内（docker 容器、任务网络） | DNS 失败、镜像拉取、依赖安装 |
| `infra_error` | 平台层（harbor、rock 服务） | API 500、沙箱启动失败、平台超时 |

---

## 7. 验证器问题（verifier_issue）

### 定义

agent 已经实质性完成了任务（从 trajectory 角度判断），但 verifier 没有正确计分。

### 识别方法

- `result.json` 中 `agent_result` 看起来正常完成
- 但 `verifier_result.rewards` 为 0 或极低
- trajectory 末尾 agent 的操作和输出看起来符合任务要求
- `verifier/test-stderr.txt` 有 verifier 自身的错误（非任务相关）
- 若有多个 trial，部分 trial reward 为 1.0 但执行轨迹几乎相同，说明 verifier 可能有不确定性

### 判断标准

这是最难判断的分类。建议：

1. 仔细阅读 verifier 的 stdout 和 stderr，确认 verifier 期望的最终状态是什么
2. 对比 trajectory 最后的状态与 verifier 期望状态
3. 如果 agent 确实做对了但 verifier 打了 0 分，才归类为 `verifier_issue`
4. 不要因为"看起来做对了"就轻易归类为此类——应以 verifier 的评分标准为准绳

---

## 8. 部分完成（partial_completion）

### 定义

任务有多个子目标，agent 完成了部分但未全部完成，reward 落在 (0, 1) 区间。

### 识别方法

- `avg_reward` 在 0.1 ~ 0.9 之间
- `reward_stats` 显示部分 trial 有非零 reward
- verifier stdout 显示部分测试用例通过

### 注意

`partial_completion` 是描述任务完成程度的辅助分类，通常需要结合主分类使用。例如：

- "部分完成 + 策略错误"：完成了简单子任务，但复杂部分选错了策略
- "部分完成 + 能力不足"：理解了全部要求，但技术能力只够完成 60%

在写分析文件时，如果 reward 在 (0, 1)，主分类填"部分完成"，并在根因分析中说明哪些子任务完成了、哪些没有以及为什么。

---

## 边界情况处理指南

### "超时"还是"能力不足"？

关键问题：**如果给 agent 更多时间，它能完成吗？**

- 若 trajectory 显示 agent 在稳定推进且没有出错，只是时间不够 → `timeout`
- 若 agent 陷入了无效循环或反复犯同一错误 → `capability_gap` 或 `strategy_error`（超时是症状，不是根因）

### "策略错误"还是"理解偏差"？

关键问题：**agent 是否描述了正确的任务目标？**

- 若 agent 的 reasoning_content 或文字说明显示它明白任务要求，但解法路径错误 → `strategy_error`
- 若 agent 的表述从一开始就显示它误解了任务 → `misunderstanding`

### "环境问题"还是"基础设施错误"？

关键问题：**错误发生在任务沙箱内还是平台层？**

- 任务容器内的 DNS/依赖/文件系统问题 → `env_issue`
- Rock 平台/Harbor API/沙箱调度层面的错误 → `infra_error`

### 多种因素共存时

若一个 job 同时有多种失败因素，按以下优先级取主分类：

```
infra_error > env_issue > timeout > misunderstanding > strategy_error > capability_gap > partial_completion
```

基础设施类问题优先级最高，因为它们遮蔽了 agent 行为的信号——只有排除了基础设施问题，对 agent 能力的判断才有意义。

---

## Trajectory 分析检查清单

分析每个 trajectory 时，逐项确认：

- [ ] 第一个 user 消息是什么？（确认任务目标）
- [ ] agent 在 reasoning 中如何理解任务？（有无偏差）
- [ ] agent 采用了什么主要策略？（合理/不合理）
- [ ] 第几步出现了第一个明显错误？
- [ ] agent 是否识别到自己的错误？如何响应？
- [ ] 最终状态是什么？（卡住/超时/提交错误答案/放弃）
- [ ] exception.txt 中的异常属于哪个层面？
- [ ] verifier 输出与 agent 最终提交的答案是否一致？

---

## 解决方案映射表

异常任务（`abnormal` 和 `zero_plus_abnormal` 类型）的根因分析和解决方案参考。对应 `references/report-templates.md` 中报告模板 §4 解决方案部分。

### env_issue 解决方案映射

| 异常特征 | 常见 exception_type / message | 通用建议 | 参数调整方向 | 处置判断 |
|----------|------------------------------|---------|-------------|---------|
| Docker/容器启动失败 | `RuntimeError: Docker compose command failed` | 检查镜像是否正确、资源是否充足 | `--image` 更换镜像；`--memory` 增大内存 | ✅ 换镜像或加资源后 retry |
| DNS 解析失败 | `no such host`、`DNS resolution failed` | 确认沙箱网络配置、检查集群 DNS 服务 | `--cluster` 切换集群 | ⚠️ 需确认集群网络策略 |
| 镜像拉取超时 | `image pull timeout`、`ImagePullBackOff` | 检查镜像仓库可达性、镜像大小 | `--image` 使用预缓存镜像 | ✅ 换预缓存镜像后 retry |
| 依赖安装失败 | `pip install failed`、`npm install error` | 检查网络连通性和包仓库镜像配置 | `--ee` 配置镜像源环境变量 | ⚠️ 需检查沙箱网络或配置镜像源 |
| 端口绑定失败 | `port already in use`、`bind: address already in use` | 检查是否有残留容器占用端口 | 无直接参数调整 | ⚠️ 需清理残留沙箱后 retry |
| 文件系统权限错误 | `Permission denied`、`EACCES` | 检查容器内用户权限和挂载卷权限 | 无直接参数调整 | ⚠️ 需检查镜像权限配置 |
| OOM（容器级） | `OOMKilled`、`Container killed` | 增大内存分配 | `--memory` 增大（如 4Gi→8Gi）；`--cpus` 增加 | ✅ 加资源后 retry |
| 环境构建超时 | `environment_setup.duration_sec` 接近上限 | 增大 setup 超时 | `override_setup_timeout_sec` 增大 | ✅ 增大超时后 retry |

### infra_error 解决方案映射

| 异常特征 | 常见 exception_type / message | 通用建议 | 参数调整方向 | 处置判断 |
|----------|------------------------------|---------|-------------|---------|
| API 500 错误 | `InternalServerError`、`HTTP 500` | 平台服务异常，等待恢复或联系平台团队 | 无直接参数调整 | 🐛 平台 bug 需上报 |
| API 超时 | `ServiceUnavailable`、`HTTP 503`、`gateway timeout` | 平台负载过高或服务重启中 | 降低 `--concurrency`；错峰 retry | ✅ 降并发或稍后 retry |
| 沙箱启动失败 | `sandbox creation failed`、`Container not found` | 集群资源不足或调度异常 | `--cluster` 切换集群；`--memory`/`--cpus` 调小以降低调度难度 | ⚠️ 需确认集群资源或切换集群 |
| 连接被拒 | `ConnectionRefused`、`Connection reset` | API 服务不可达 | 无直接参数调整 | 🐛 平台 bug 需上报 |
| 任务未完成（finished_at=null） | `finished_at = null` 且 `duration_sec` 极短 | 任务可能在调度阶段失败 | 无直接参数调整 | 🐛 检查平台日志后上报 |
| 凭证/认证错误 | `AuthenticationError`、`401 Unauthorized`、`403 Forbidden` | 检查 API Key 是否有效、是否过期 | `--ee` 更新 API Key 环境变量 | ⚠️ 需更新凭证后 retry |
| 速率限制 | `RateLimitError`、`429 Too Many Requests` | 降低并发或切换 API Key | `--concurrency` 降低；`--ee` 切换 API Key | ✅ 降并发后 retry |
| 沙箱崩溃 | `Sandbox crashed`、`Container exited unexpectedly` | 检查是否资源不足或镜像问题 | `--memory` 增大；`--image` 更换镜像 | ✅ 加资源后 retry 或 🐛 上报 |

### 处置判断决策树

```
异常发生
├── exception 信息是否指向明确的参数问题？（OOM / 超时 / 速率限制）
│   └── 是 → 查上方映射表获取参数调整建议 → ✅ 调参后 retry
│   └── 否 ↓
├── 错误是否发生在平台层？（API 500 / 调度失败 / 沙箱生命周期）
│   └── 是 → 🐛 平台 bug 需上报
│   └── 否 ↓
├── 错误是否涉及环境配置？（网络 / 权限 / 依赖 / DNS）
│   └── 是 → ⚠️ 需人工介入检查环境
│   └── 否 → ⚠️ 需人工介入进一步排查
```

### 参数调整优先级

当多个参数都可能需要调整时，按以下优先级操作：

1. **低风险参数**（可直接调整，无需用户确认）：
   - `memory`、`cpus`：资源类参数
   - `override_timeout_sec`、`override_setup_timeout_sec`：超时类参数
   - `concurrency`：并发控制
   - `--ee` 环境变量：镜像源、超时配置等

2. **高风险参数**（需用户确认后调整）：
   - `--image`：更换运行镜像
   - `--cluster`：切换集群
   - `--model`：更换模型
   - `--agent`：更换 agent
