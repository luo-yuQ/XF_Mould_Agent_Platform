# 冷冲压模具行业 AI 售前客服系统项目全景总结

## 一、文档定位

本文对当前 `XF_Mould_Agent_Platform` 项目进行完整说明，既可以用于理解代码和继续开发，也可以作为简历项目介绍、技术面试展开和架构复盘材料。

文中严格区分以下三种状态：

- **已实现**：当前代码中已经存在完整调用链或可验证实现。
- **部分实现**：已有主要代码，但仍缺少真实外部集成、统一恢复能力或完整评测。
- **规划中**：只有设计文档或路线图，尚不能作为已经落地的项目成果。

当前项目并不是一个已经生产化的商业系统，而是一套可本地部署、具备完整业务原型和较强工程结构的行业多智能体应用。

---

## 二、项目背景与定位

冷冲压模具企业在售前沟通、工程分析和质量体系咨询中，需要频繁查询 FMEA 方法、冷冲压工艺风险、VDA 6.4 质量体系要求以及企业内部质量资料。传统处理方式存在以下问题：

1. 专业知识分散在 FMEA 手册、VDA 6.4 质量手册和历史业务产物中，人工检索效率较低。
2. 售前、研发和质量人员回答问题时，容易因知识背景不同而出现口径不一致。
3. PFMEA、审核记录和质量分析报告具有大量重复的结构化字段，人工编写成本较高。
4. 通用大模型缺少企业内部资料，容易产生无依据的标准条款、评分和公司能力承诺。
5. 单一问答 Agent 难以同时处理研发风险、质量保障、业务审核和报告生成等不同任务。

因此，本项目面向冷冲压模具行业，构建了一套以多智能体工作流、领域 RAG、结构化生成和规则校验为核心的 AI 售前与工程知识服务平台。

系统目前覆盖以下场景：

- FMEA、冷冲压工艺和失效模式知识问答。
- VDA 6.4、质量体系、审核和流程知识问答。
- 普通闲聊和天气工具调用。
- PFMEA 辅助生成。
- 质量问题、PFMEA 内容和审核记录检查。
- 基于 FMEA 与审核结果生成质量分析报告。
- 研发与质量 Specialist 共同参与的综合售前方案生成。
- 多会话管理、历史消息恢复和 SSE 流式响应。

更准确的产品定位是：

> 面向冷冲压模具企业售前、研发和质量人员的行业智能助手与结构化业务工作流平台。

“客服”只是统一交互入口。系统除了回答问题，还会执行检索、生成、校验、修复、持久化和报告展示等工程任务。

---

## 三、技术栈

### 1. 模型与智能体框架

- 大语言模型：通义千问，通过 DashScope OpenAI 兼容接口调用。
- Embedding：DashScope `text-embedding-v4`，默认向量维度为 1024。
- 智能体编排：LangGraph。
- 模型与消息封装：LangChain。
- 数据契约与结构校验：Pydantic。

### 2. 数据与基础设施

- PostgreSQL：用户、会话、消息、摘要、FMEA、审核、报告、产物版本和协作任务的事实存储。
- Milvus：FMEA 与 VDA 6.4 文档向量检索。
- Redis：保留了旧版会话基础设施和部署配置，但当前 FastAPI 主链路未将其作为认证、聊天记忆或 LangGraph Checkpoint 的核心存储。
- Alembic：数据库迁移。
- Docker Compose：编排前端、后端、PostgreSQL、Redis、Milvus、etcd 和 MinIO。

### 3. Web 应用

- 后端：FastAPI。
- 流式传输：SSE。
- 前端：React 19、TypeScript、Vite。
- 认证：JWT、HttpOnly Cookie、Argon2 密码哈希。

---

## 四、总体架构

系统可以分为六层。

### 1. 交互层

React 前端提供登录、会话问答、PFMEA 生成、审核检查、报告生成和售前方案页面。

### 2. API 层

FastAPI 负责：

- 用户注册、登录和身份校验。
- 会话及历史消息管理。
- 普通问答 SSE 输出。
- FMEA、Audit、Report 独立工作流调用。
- 销售协作任务创建、查询和步骤查询。
- 业务产物及版本相关接口。

### 3. 智能体编排层

当前同时存在两类编排方式：

- **路由型多智能体**：Supervisor 在 R&D、Quality、Chat 中选择一个 Agent。
- **协作型多智能体**：Planner、R&D Specialist、Quality Specialist、Reviewer、Proposal Writer 顺序协作。

此外，FMEA、Audit 和 Report 分别拥有独立 LangGraph 工作流。

### 4. 能力与约束层

该层包含：

- Agent Prompt。
- 文件化 Skills。
- Pydantic Schema。
- Verifier。
- 单次 Repair 节点。
- 确定性 Markdown 渲染器。

它们共同组成了面向本项目的轻量级 Agent Harness。

### 5. 知识与记忆层

- FMEA 手册知识库。
- VDA 6.4 质量手册知识库。
- 当前会话消息与滚动摘要。
- FMEA、Audit、Report 业务产物。
- FMEA 产物版本记录。

### 6. 数据持久化层

PostgreSQL保存可追溯业务事实，Milvus保存文档向量索引。二者职责不同，Milvus不能替代关系数据库。

---

## 五、主问答多智能体工作流

### 1. 工作流结构

主问答图的执行过程为：

```text
用户问题
→ Supervisor
→ R&D RAG → R&D Writer
  或 Quality RAG → Quality Writer
  或 Chat Agent
→ SSE 返回前端
```

这段流程图不是程序代码，而是节点调用顺序。

它由 FastAPI 普通问答接口调用。在用户提交问题后，后端构造 `AgentState`，再调用已编译的 LangGraph。LangGraph 首先执行 Supervisor，之后根据条件边进入对应分支。

### 2. Supervisor 的职责

Supervisor 使用大模型对问题进行结构化分类，输出：

- `next_agent`：目标 Agent，只允许 `rd`、`quality`、`chat`。
- `intent`：更具体的意图标签。
- `reasoning`：路由判断依据。

随后 LangGraph 的条件路由函数根据 `next_agent` 选择分支。

例如：

- 失效模式、FMEA、冲压工艺风险进入 R&D。
- VDA 6.4、认证、质量流程和审核进入 Quality。
- 问候、天气和普通闲聊进入 Chat。

系统还支持用户手动指定 R&D 或 Quality，从而跳过大模型意图识别。

### 3. R&D Agent

R&D Agent 分为两个节点：

1. RAG 节点直接使用用户问题查询 FMEA Milvus Collection。
2. Writer 节点将用户问题、检索结果和引用元数据组合后调用大模型。

RAG 检索是同步网络与数据库操作，因此代码通过线程池执行，避免阻塞 FastAPI 的异步事件循环。

Writer 会为每个检索块分配 `[N]` 引用编号，并建立编号到文档名、章节、页码、表格编号等元数据的映射。模型输出后，系统从正文中提取真实使用的引用编号，只保留存在于映射表中的编号。

### 4. Quality Agent

Quality Agent同样采用 RAG 与 Writer 两阶段结构，但只查询 VDA 6.4 质量知识库。

Quality Writer要求模型生成回答和引用编号。若结构化 JSON 解析失败，系统会降级为正则提取或原始文本，防止一次格式错误导致整个请求失败。

### 5. Chat Agent

Chat Agent不访问领域知识库，主要处理普通对话和天气查询。

它首先让模型判断是否需要调用天气工具。若产生工具调用，则执行工具并将工具结果交给模型生成最终回答；否则直接返回模型回答。

### 6. 当前主问答图的边界

这是一种 Supervisor 路由型多智能体结构。一次请求通常只进入一个专业 Agent，不代表多个专业 Agent 会共同完成同一任务。

FMEA、Audit、Report 和销售协作图都有独立入口，尚未统一接入主 Supervisor。

---

## 六、领域知识库与 RAG

### 1. 双知识库设计

系统分别建立：

- `xf_fmea_kb`：FMEA 手册知识库。
- `xf_quality_kb`：VDA 6.4 质量手册知识库。

将两类知识分集合存储，可以减少跨领域噪声，并与 R&D、Quality 的路由边界对应。

### 2. 文档解析

当前入库支持 DOCX 与 PDF。

#### DOCX

系统直接读取 DOCX 压缩包中的 XML：

- 从大纲级别或 Heading 样式恢复标题层级。
- 提取普通段落。
- 解析 Word 表格并转换为 Markdown。
- 保存当前章节和完整标题路径。

#### PDF

系统使用 PyMuPDF：

- 读取 PDF 文字层。
- 通过“相同文本与相近纵向位置在多数页面重复出现”的规则识别页眉页脚。
- 过滤纯页码。
- 通过正则识别章节标题。
- 使用 PyMuPDF 表格检测提取表格。
- 保存页码范围。

当前 PDF 解析器默认不执行 OCR，并且会跳过图片块。因此扫描版 PDF、E-R 图和流程图的图形关系暂未被解析。

### 3. 结构感知分块

分块不是直接对整篇文档做固定长度切分，而是：

1. 先按标题层级和章节边界组织内容。
2. 对章节内长段落按句子边界切分。
3. 使用默认 1000 字符 Chunk 和 100 字符重叠作为长文本兜底。
4. 为每个 Chunk 保存标题路径、章节、来源文件和页码。

这种设计减少标题与正文分离、结论被截断以及检索结果缺少章节语境的问题。

### 4. 表格多粒度设计

小于等于 20 行的小表格可整体入库。

大表格会生成三类 Chunk：

- `table_parent`：完整表格，只用于回溯，不直接参与向量检索。
- `table_summary`：列名、前后样例行和高频词组成的摘要，用于宽泛召回。
- `table_row_block`：携带表头的数据行块，每块最多 20 行，用于精确检索。

当检索命中 `table_summary` 时，系统会根据 `table_id` 再拉取最多三个关联行块。这样可以兼顾检索粒度与表格上下文完整性。

### 5. 向量化与 Milvus

入库阶段调用 Embedding 接口，将 Chunk 转换为 1024 维向量，再写入 Milvus。

每条记录除向量与文本外，还保存：

- `chunk_uid`
- 文档来源
- 章节和标题路径
- Chunk 类型
- 父块编号
- 表格编号
- 行范围
- 文件类型与文件名
- 页码范围

### 6. 在线检索

在线查询过程为：

1. 对用户 Query 生成向量。
2. 在指定 Collection 中进行 COSINE 相似度搜索。
3. 使用 Milvus Hybrid Search 接口和 RRF Ranker统一排序。
4. 排除 `table_parent`。
5. 展开命中的表格摘要。
6. 返回统一结构化 Chunk。

当前虽然调用了 Hybrid Search 接口，但实际只有一个 Dense 向量请求，因此本质上仍以稠密向量检索为主，尚未形成完整的 BM25 与 Dense 混合检索。

### 7. 引用展示

RAG 返回的不只是文本，还包含来源元数据。Writer 使用 `[N]` 标记正文引用，FastAPI 将真实引用转换为响应字段，前端再展示引用详情。

因此引用链路为：

```text
Milvus Chunk
→ citation_map
→ 模型正文中的 [N]
→ citation_ids 过滤
→ FastAPI Citation
→ React 来源展示
```

---

## 七、PFMEA 辅助生成工作流

### 1. 调用入口

PFMEA 生成拥有独立 FastAPI 接口和独立 LangGraph，不通过主 Supervisor。

前端提交产品、工序、失效现象和背景信息后，FastAPI 构造 FMEA 状态并调用 FMEA Graph。

### 2. 执行流程

```text
输入规范化
→ 检索问题规划
→ FMEA RAG
→ 结构化 Rows 生成
→ Verifier
→ 失败时最多修复一次并重新校验
→ 确定性 Markdown 渲染
→ 保存 FMEA Run 与初始版本
```

### 3. 输入与输出契约

输入包括：

- FMEA 类型，当前主要支持 PFMEA。
- 产品或分析对象。
- 目标工序。
- 失效现象。
- 补充背景。

输出的每一行包含：

- 功能与要求。
- 失效模式和失效后果。
- 严重度 S。
- 失效原因。
- 发生度 O。
- 预防与探测控制。
- 探测度 D。
- 行动优先级 AP。
- RPN。
- 建议措施。
- 证据说明。

### 4. 为什么先生成 JSON

模型不直接负责最终 Markdown 表格，而是先生成符合 Pydantic Schema 的 JSON。

这样做的原因是：

- 字段是否缺失可以被程序检查。
- 数值字段可以被代码转换和限制。
- RPN可以由程序重新计算。
- 校验器可以定位到具体行和字段。
- 最终展示格式不依赖模型是否正确输出 Markdown。

### 5. 规则校验

FMEA 校验不是单一字符串匹配，而是四类规则组合：

1. **结构校验**：检查 Rows 和必填字段。
2. **数值与枚举校验**：规范 S/O/D、AP，并重新计算 RPN。
3. **证据校验**：通过正则识别“第 X 条标准”等表述，再检查检索材料能否支持。
4. **启发式一致性校验**：检查建议措施与原因、预防控制或探测控制之间是否存在关键词联系。

当没有检索材料时，Evidence 必须标记“需人工确认”，避免把通用知识包装为手册原文。

### 6. 单次修复

若 Verifier 不通过，系统将问题列表与修复指令交给模型，最多修复一次，再重新执行 Verifier。

限制为一次是为了避免：

- 无限循环。
- Token 成本失控。
- 模型在多次改写中引入新的字段漂移。

### 7. Markdown 渲染

校验后由普通 Python 函数渲染 Markdown。

该函数不会重新推理，只负责：

- 输出固定列顺序。
- 展示 S/O/D/AP 建议值标记。
- 输出评分依据。
- 汇总高风险项。
- 增加 AI 结果需人工确认的免责声明。

### 8. 产物持久化与版本

FMEA Run保存输入、检索 Query、引用、结构化 Rows、Markdown 和校验结果。

系统还实现了 FMEA 业务产物版本能力：

- 初次生成创建 V1。
- 用户可基于历史版本继续修改。
- 新版本保存父版本、修改要求、输出 JSON、Markdown、引用和校验结果。
- 版本之间生成差异摘要。
- 可查询历史版本并恢复查看。

当前版本追改主要针对 FMEA，Audit 和 Report 尚未获得同等完整的版本能力。

---

## 八、Audit 审核检查工作流

### 1. 业务作用

Audit用于检查：

- 质量问题描述。
- PFMEA 文本。
- 审核记录。
- 其他通用质量材料。

它不是文档上传解析器，而是对用户提交的结构化字段或文本内容进行审核。

### 2. 工作流

```text
输入规范化
→ 检索问题规划
→ 按问题选择 FMEA/VDA 知识库
→ 生成结构化 Findings
→ Verifier
→ 失败时最多修复一次
→ Markdown 渲染
→ 保存 Audit Run
```

### 3. 检索策略

Audit可能同时需要 FMEA 与质量体系知识。

系统根据 Query 中是否包含 FMEA、PFMEA、VDA、质量、审核等关键词选择一个或两个 Collection，再将多个 Query 的结果去重合并。

### 4. 结构化审核结果

模型生成 Findings，而不是直接输出最终报告。Verifier检查字段完整性、风险描述、证据和整改建议，随后由渲染器生成 Markdown。

若单次修复后仍有问题，最终结果会附加人工确认提示，而不是假装已经完全可靠。

### 5. 当前边界

- Audit可以检查用户主动提交的 PFMEA 文本。
- Audit不会自动接收刚生成的 FMEA 结果。
- Audit产物已经持久化，但尚未实现完整追改和版本历史。

---

## 九、Report 报告生成工作流

### 1. 业务作用

Report将用户明确选择的 FMEA Run、Audit Run、补充背景和可选 RAG 依据组织成质量问题分析报告。

它的职责是整合已有事实，不是重新执行 FMEA 或审核推理。

### 2. 工作流

```text
输入检查
→ 加载用户选择的 FMEA/Audit 来源
→ 来源匹配检查
→ 可选 RAG
→ 构建来源快照与报告上下文
→ Report Writer
→ Verifier
→ 失败时最多修复一次
→ 保存 Report Run
→ 返回结构化结果
```

### 3. 来源契约

系统会保存来源快照，确保未来查看报告时仍能知道当时使用了哪些 FMEA、Audit 和 RAG 材料。

来源匹配目前采用规则判断，只提供提醒，不会自动替换用户选择的来源，也不能证明两个产物一定属于同一质量案例。

### 4. 报告约束

Report Writer不得：

- 新增 FMEA 失效模式。
- 改写 S/O/D/AP 或 RPN。
- 新增 Audit Findings。
- 编造标准条款、页码、责任人、日期和具体数值。

缺少 FMEA 或 Audit 时，必须明确写出“未提供相关结果，需人工确认”。

### 5. 报告校验

Verifier检查：

- 固定章节是否完整。
- 缺失来源是否被正确提示。
- 精确标准条款是否可追溯。
- 日期、数值、责任人等具体信息是否能在来源中找到。
- 结论是否引入前文没有的新事实。

---

## 十、销售协作多智能体工作流

### 1. 与主问答图的区别

主问答图是“选择一个 Agent”，销售协作图是“多个 Agent共同完成一份方案”。

当前销售协作图采用串行方式：

```text
Request Intake
→ Planner
→ R&D Specialist
→ Quality Specialist
→ Reviewer
→ Proposal Writer
→ Final Verifier
→ Persist Run
```

### 2. Planner

Planner将综合售前需求拆分为结构化任务，主要包含研发分析、质量分析、审核和方案编写。

Planner只能从允许的 Agent列表中选择任务。即使识别到可能需要 FMEA 或 Audit，也只会记录可选产物占位，当前不会自动调用这些专业工作流。

若 Planner模型输出非法、缺少核心角色或调用失败，系统会回退到固定的串行计划。

### 3. R&D Specialist

R&D Specialist查询 FMEA 知识库，输出统一的 `SpecialistOutput`：

- 摘要。
- Claims。
- Risks。
- Recommendations。
- Missing Information。
- Citations。
- Confidence。

模型引用只能从本次真实检索 Chunk的 Allowlist中选择。若没有检索结果，系统会清空引用、禁止高置信度，并要求至少产生一项信息缺口。

### 4. Quality Specialist

Quality Specialist查询 VDA 6.4 知识库，使用与 R&D 相同的数据契约，但承担质量体系、过程保障和审核证据分析。

统一契约使 Reviewer与 Writer无需理解两个 Agent各自不同的自由文本格式。

### 5. Reviewer

Reviewer采用规则优先策略，主要检查：

- R&D 或 Quality结果是否缺失。
- R&D 是否越权声明公司质量能力。
- Quality是否越权编造技术工艺方案。
- Claims、Risks和Recommendations是否缺少引用。
- 是否存在必须人工确认的信息。
- 用户是否要求“零缺陷”“绝对保证”等过度承诺。

可选 LLM审核接口已预留，但默认关闭，因此当前 Reviewer主要是确定性规则审核。

### 6. Proposal Writer

Proposal Writer不会自由编造方案事实。

模型只能从已经存在的 Claim、Risk和Recommendation ID中选择内容。随后普通 Python模板根据原始 Specialist和Reviewer结果渲染六个固定章节。

这种“模型选择，程序渲染”的设计降低了模型在最终成文阶段新增事实或引用的风险。

### 7. Final Verifier

Final Verifier检查：

- 最终报告是否存在。
- R&D、Quality和Reviewer结果是否存在。
- 六个固定章节是否完整。
- Writer引用是否来自 Specialist真实引用集合。

### 8. Run与Step持久化

每次协作任务拥有一个 `CollaborationRun`，记录：

- 用户、会话和原始请求。
- 客户上下文。
- 执行计划。
- 任务状态。
- 最终报告。
- Reviewer结果。
- 引用、错误、模型信息和指标。

每个节点拥有一个 `CollaborationStep`，记录：

- Step ID、名称和 Agent。
- 状态。
- 输入与输出 JSON。
- 错误信息。
- 开始、结束和耗时。
- 模型与指标信息。

若某一步失败，已完成步骤会保留，失败步骤标记为 `failed`，后续步骤标记为 `skipped`。

### 9. 当前实现程度

Phase C的串行协作 MVP已经完成，并具有：

- 真实 Planner结构化调用路径。
- 真实 R&D、Quality RAG与LLM路径。
- Reviewer规则。
- Proposal Writer。
- Run/Step持久化。
- 创建、查询和步骤查询 API。
- 自动化单元、API和最小E2E测试。

但真实外部 LLM、Milvus和Embedding的完整 live baseline尚未执行，因此当前自动化结果主要证明编排、契约和失败处理正确，不能直接等同于生产回答质量。

---

## 十一、Skills 与 Agent Harness

### 1. Skills

项目已实现三类文件化业务 Skill：

- `fmea_generation`
- `audit_check`
- `report_generation`

每个 Skill通常由以下内容组成：

- `SKILL.md`：业务规则和职责边界。
- 模板文件：规定最终结构和展示格式。
- 检查规则文件：规定字段、评分、引用和校验要求。

Agent在对应生成阶段加载 Skill文本并注入 Prompt。

Skills的价值是将易变化的领域规则从 Python代码和超长Prompt中拆出，使业务规则能够独立维护和复用。

### 2. Agent Harness

项目没有一个独立命名为 Harness的通用框架，但已经具备轻量级 Harness的主要组成：

- LangGraph负责节点和条件边。
- AgentState负责任务级工作状态。
- Pydantic负责输入输出契约。
- Skills负责领域规则。
- Verifier负责确定性校验。
- Repair节点负责有限修复。
- 日志包装器记录节点执行。
- Pytest和Eval Cases负责回归验证。
- FastAPI负责对外运行入口。

因此可以描述为：

> 项目形成了一套面向行业智能体应用的轻量级 Agent Harness，但它仍与当前业务强绑定，尚未抽象为独立通用平台。

---

## 十二、Pydantic 在项目中的作用

Pydantic承担数据契约层。

### 1. FastAPI请求响应

登录、FMEA生成、审核、报告和销售协作接口都使用Pydantic定义字段。字段缺失或类型错误时，FastAPI会自动返回校验错误。

### 2. 模型结构化输出

Supervisor路由、FMEARow、AuditFinding、PlannerOutput、SpecialistOutput、ReviewerOutput等均使用Pydantic约束。

### 3. Agent之间的交接

协作型多智能体不以Markdown作为内部协议，而是：

```text
LLM原始输出
→ Pydantic校验
→ 普通字典
→ LangGraph State
→ CollaborationStep.output_json
```

Pydantic保证“数据长什么样”，Verifier负责“业务上是否合理”。二者不能互相替代。

---

## 十三、记忆系统

### 1. 工作记忆

工作记忆是单次任务执行期间的临时状态。

当前项目通过 `AgentState` 或 `SalesCollaborationState` 保存：

- 用户输入。
- 当前意图和目标Agent。
- RAG结果与引用。
- FMEA Rows或Audit Findings。
- 校验结果。
- 是否已经修复。
- 报告上下文。
- 协作计划和各Specialist结果。

这些状态由LangGraph节点读取和更新。

当前尚未接入LangGraph Checkpointer，因此工作状态主要存在于当前进程和当前调用中。若服务在中间节点异常退出，不能直接从该节点继续运行。

### 2. 持久化检查点

持久化检查点是将某一时刻的完整Graph State、当前节点和执行版本写入外部存储。

它不同于聊天记录：

- 聊天记录保存用户和AI说了什么。
- Checkpoint保存工作流执行到了哪里，以及当时所有中间状态。

未来可以通过Redis或PostgreSQL Checkpointer实现任务中断恢复、人工审批后继续和状态历史查看。

### 3. 短期记忆 Memory V1

当前项目已实现单会话短期记忆：

- PostgreSQL保存全部聊天消息。
- 默认获取最近20条原始消息。
- 未被摘要覆盖的历史达到40条时触发滚动摘要。
- 每次摘要处理最老的20条消息。
- Prompt最终由“历史摘要 + 未覆盖的最近消息 + 当前问题”组成。
- 记录摘要覆盖到的最后一条消息ID。
- 清理超时且没有Assistant回复的孤儿User消息。

短期记忆只服务当前 `session_id`，不会自动召回其他会话。

### 4. 长期记忆 Memory V2

长期记忆目前只有完整设计，没有代码落地。

规划内容包括：

- 用户画像：技术栈、项目背景、长期偏好和输出风格。
- 跨会话决策记忆：架构选择、项目约束和阶段结论。
- 长期对话摘要：可独立检索的重要历史信息。
- 业务产物记忆：历史FMEA、Audit、Report和版本。
- 相似案例记忆：按任务召回相关业务产物。
- 记忆更新、去重、合并、禁用、删除、过期和冲突处理。

规划存储原则为：

- PostgreSQL保存记忆事实、状态、来源和版本。
- Milvus仅保存需要语义检索的向量索引。
- 文档RAG、对话记忆和业务产物记忆使用不同Collection或Namespace。

---

## 十四、认证、会话与Web链路

### 1. 登录认证

当前认证不依赖Redis。

执行过程为：

```text
用户名密码登录
→ PostgreSQL查询用户
→ Argon2校验密码
→ FastAPI签发JWT
→ JWT写入HttpOnly Cookie
→ 页面刷新后前端请求/auth/me
→ 浏览器自动携带Cookie
→ 后端验签并恢复用户
```

JWT默认有效期为2小时。HttpOnly降低前端脚本直接读取Token的风险。

### 2. 会话管理

PostgreSQL保存：

- ChatSession。
- ChatMessage。
- ChatSessionSummary。

接口支持会话创建、列表、重命名、删除和历史消息分页。

### 3. SSE流式问答

FastAPI负责：

- 执行LangGraph。
- 接收模型流式Chunk。
- 封装 `status`、`token`、`done` 和 `error` 等SSE事件。
- 持续写入HTTP响应流。

React负责：

- 使用Fetch建立请求。
- 读取`ReadableStream`。
- 按行解析SSE事件。
- 增量更新回答内容。
- 在`done`事件中写入最终消息、Agent类型和引用。

### 4. 前端会话缓存

前端对已加载会话采用容量为3的LRU策略，历史消息按20条分页加载。该缓存只是减少前端重复请求，PostgreSQL仍是消息事实存储。

### 5. 业务页面

当前前端包含：

- 普通问答。
- FMEA生成。
- 审核检查。
- 报告生成。
- 售前方案协作页面。

销售协作页面可：

- 创建任务。
- 将`run_id`写入URL。
- 按`run_id`加载任务。
- 每2秒轮询未结束任务。
- 展示Run状态和各Agent步骤。
- 展示最终报告、引用和人工确认项。
- 刷新或分享链接后重新查询任务。

这说明Phase D并非完全未开始，而是已经完成销售协作页面和基本恢复能力，但尚未统一所有FMEA、Audit、Report任务生命周期。

---

## 十五、Redis 在当前项目中的真实位置

Redis容器、依赖和配置仍存在，旧版 `app.py` 曾使用Redis保存会话元数据和消息，并设置一天TTL。

但当前主要FastAPI链路中：

- JWT认证不使用Redis。
- 聊天消息与摘要使用PostgreSQL。
- LangGraph没有Redis Checkpointer。
- 销售协作Run与Step使用PostgreSQL。

因此当前不能把Redis描述为核心认证或记忆组件。

未来更合适的用途包括：

- LangGraph持久化Checkpoint。
- 长任务状态和SSE断线恢复。
- Redis Stream事件流。
- RAG查询缓存。
- 接口限流。
- 幂等Key与重复提交保护。
- 短期热点会话缓存。

---

## 十六、业务产物与数据模型

### 1. 核心业务表

- `users`
- `chat_sessions`
- `chat_messages`
- `chat_session_summaries`
- `fmea_runs`
- `audit_runs`
- `report_runs`
- `business_artifact_versions`
- `collaboration_runs`
- `collaboration_steps`

### 2. 统一业务产物元数据

FMEA、Audit和Report逐步统一了：

- 标题。
- 摘要。
- 关键词。
- 产物类型。
- 引用。
- 创建和更新时间。

这些元数据用于列表展示、来源选择和未来案例检索。

### 3. 用户隔离

API读取业务Run和会话时，根据当前登录用户校验归属，避免不同用户之间通过ID读取数据。

---

## 十七、测试与评测

### 1. 当前自动化测试

项目已经包含：

- Supervisor路由测试。
- R&D与Quality引用契约测试。
- FMEA、Audit、Report API快照测试。
- PDF分块脚本。
- FMEA产物追改与版本测试。
- Report来源匹配测试。
- 时区契约测试。
- 销售协作Schema、Model、Graph、Planner、Specialist、Reviewer、Writer、API和E2E测试。

Phase C记录的全量自动化结果为：

> 123 passed，1 warning。

该数字来自路线图记录，最终文档复核时应以当前重新执行的测试结果为准。

### 2. Eval Cases

当前已有：

- FMEA评测案例。
- Audit评测案例。
- Report评测案例。
- 5个销售协作Smoke Cases。

销售协作案例覆盖：

- 技术与质量综合问题。
- 纯技术问题。
- 纯质量问题。
- 信息不足。
- 诱导过度承诺。

### 3. 当前评测边界

多数自动化测试使用Fake Retriever、Fake LLM、Mock Graph或SQLite内存数据库，以验证契约、编排和失败处理。

尚缺少：

- 完整真实LLM、Embedding和Milvus集成基线。
- 至少20个销售协作质量评测案例。
- 单Agent、Supervisor和协作Graph的对照实验。
- Token、延迟、模型调用次数和成本指标。
- 浏览器端到端测试。

---

## 十八、当前实现中的主要工程亮点

1. 将主问答、结构化业务工作流和协作型多智能体分层，而不是强行使用一个巨大Agent。
2. 使用双知识库降低研发与质量知识互相干扰。
3. 文档入库采用标题层级、长文本兜底和表格多粒度分块。
4. 保存完整引用元数据，实现从回答到原始Chunk的追溯。
5. FMEA、Audit和Report采用“结构化生成—规则校验—有限修复—确定性渲染”。
6. 使用Pydantic建立Agent交接契约。
7. Proposal Writer只能选择已有内容ID，降低最终成文时新增事实的风险。
8. 协作Run与Step持久化，使中间结果和失败位置可追踪。
9. 短期记忆采用滚动摘要，而不是无限拼接全部历史消息。
10. 用户认证、会话、流式响应和业务页面形成了完整Web原型。

---

## 十九、当前限制与技术债

1. PDF图片、扫描件、E-R图和流程图尚未接入OCR或多模态解析。
2. RAG主要仍是Dense检索，没有完成真正的Sparse与Dense混合召回和Reranker。
3. 主问答图、FMEA、Audit、Report和销售协作入口尚未统一路由。
4. FMEA与Audit不会自动衔接。
5. Report仍主要依赖用户手动选择来源。
6. 只有FMEA拥有较完整的产物追改和版本历史。
7. LangGraph尚无持久化Checkpointer。
8. Memory V2尚未实现。
9. Redis没有进入当前主链路。
10. 销售协作仍为串行，尚未并行执行R&D与Quality。
11. 销售协作真实外部集成评测不足。
12. 普通聊天支持SSE，但FMEA、Audit、Report和销售协作的任务状态、取消和恢复尚未完全统一。
13. README和Phase Tracker的部分描述已落后于代码。
14. 缺少生产级Tracing、限流、熔断、审计日志和敏感数据治理。

---

## 二十、Phase A-J 路线图与当前进度

### Phase A：基线冻结与回归保护

**目标**：在继续改造前固定现有行为，建立质量、延迟和成本基线。

**当前状态：进行中。**

已完成：

- Supervisor三类路由测试。
- R&D、Quality引用契约测试。
- FMEA、Audit、Report API快照测试。

未完成：

- 真实端到端延迟记录。
- 模型调用次数与成本基线。
- README与当前实现完全同步。

### Phase B：协作数据契约

**目标**：统一Planner、Specialist和Reviewer的结构化交接协议，并建立Run/Step持久化模型。

**当前状态：主体已完成，文档仍标为进行中。**

已完成：

- `SalesCollaborationState`。
- Planner、Specialist、Reviewer等Pydantic Schema。
- `CollaborationRun`和`CollaborationStep`。
- 数据库Migration。
- Schema、Model和数据契约测试。

遗留：

- 应用层统一错误码和状态枚举仍需继续收敛。

### Phase C：最小串行多智能体MVP

**目标**：完成第一个真实协作闭环。

**当前状态：已完成。**

已实现：

- Intake、Planner、R&D、Quality、Reviewer、Writer、Final Verifier和Persist Run。
- Specialist真实RAG与结构化LLM调用路径。
- 销售协作创建和查询API。
- Run与Step持久化。
- 最小E2E和失败场景测试。

遗留：

- 真实外部服务Live Baseline。
- 实际定向修复闭环。
- 任务中断恢复和幂等处理。

### Phase D：协作前端与任务生命周期

**目标**：让用户可查看、恢复和管理协作任务。

**当前状态：部分实现，Tracker尚未同步。**

已经实现：

- 售前方案React页面。
- Run状态、步骤、报告、引用和人工确认项展示。
- `run_id` URL恢复。
- 未结束任务轮询。
- 任务链接复制。

仍需完成：

- 将FMEA、Audit、Report统一纳入后端任务状态。
- 统一任务取消、失败重试和页面切换保护。
- 建立前端自动化测试。
- 支持真正后台执行，而不是生成接口同步等待整个Graph结束。

### Phase E：多智能体质量评测

**目标**：证明协作Graph比单Agent更有价值。

**当前状态：未开始。**

计划：

- 建立至少20个综合售前案例。
- 对比单R&D、单Quality、现有Supervisor和协作Graph。
- 评估需求覆盖率、引用准确率、无依据声明、人工确认项、延迟和成本。

进入后续阶段的前提是协作模式在综合任务中确实带来质量提升。

### Phase F：Planner路由与按需工作流

**目标**：由Planner根据复杂度选择普通问答、销售协作、FMEA或Audit。

**当前状态：未开始。**

计划：

- 简单问题继续使用现有Supervisor。
- 综合售前请求进入销售协作Graph。
- 明确要求正式PFMEA时调用FMEA Workflow。
- 提交审核材料时调用Audit Workflow。
- 增加Agent Allowlist、最大步骤数、模型调用次数和Token预算。

### Phase G：并行化与可靠性

**目标**：在语义不变的前提下降低延迟，增强失败恢复。

**当前状态：未开始。**

计划：

- R&D与Quality并行Fan-out。
- Join节点汇总。
- 超时、有限重试、部分结果和取消。
- 幂等Request Key。
- 节点级Tracing。

并行化必须建立在Phase E证明协作有效、结构化契约稳定之后。

### Phase H：Memory V2

**目标**：实现隔离、可控、可关闭的长期记忆。

**当前状态：架构设计完成，代码未开始。**

计划顺序：

1. 用户画像结构化记忆。
2. 长期对话摘要记忆。
3. 业务产物向量记忆。
4. 按任务类型检索和Prompt注入。
5. 删除、禁用、过期和冲突处理。
6. 相似FMEA案例按需接入。

### Phase I：业务产物自动关联与案例系统

**目标**：减少用户手动选择FMEA、Audit和Report来源的成本。

**当前状态：未开始。**

计划：

- 建立明确的`quality_case_id`或项目上下文实体。
- 使用Metadata Filter与Embedding相似度生成候选关联。
- 将FMEA、Audit、Report和Collaboration Run关联到同一案例。
- 候选必须显示分数与依据，并允许人工确认或覆盖。

### Phase J：生产化与后续优化

**目标**：补齐可观测、安全、可靠和运维能力。

**当前状态：未开始。**

计划：

- OpenTelemetry或等价Tracing。
- 节点级Token、延迟、错误率和成本指标。
- Prompt与模型版本记录。
- 权限、审计日志和敏感数据策略。
- 限流、超时、重试和熔断。
- 数据备份与迁移演练。
- 浏览器端到端测试。
- 在业务流程和评测数据稳定后，再判断是否需要SFT。

---

## 二十一、建议的后续实施优先级

结合当前代码，推荐顺序为：

1. 同步README与Phase Tracker，修正Phase D实际状态。
2. 执行真实LLM、Embedding和Milvus Live Baseline。
3. 完成Phase E评测集，证明协作模式收益。
4. 将销售协作接口改造成真正可查询的后台任务，补充幂等与恢复。
5. 接入LangGraph Checkpointer或等价任务检查点。
6. 统一FMEA、Audit、Report和Collaboration任务生命周期。
7. 完成Planner按需路由。
8. 在评测收益成立后并行化R&D与Quality。
9. 再实施Memory V2。
10. 最后做案例系统、生产化和SFT评估。

---

## 二十二、简历与面试表述建议

### 1. 项目一句话

> 面向冷冲压模具企业售前与质量工程场景，设计并实现基于LangGraph多智能体协作和领域RAG的AI客服平台，支持FMEA/VDA 6.4知识问答、PFMEA与审核报告辅助生成、规则校验、来源引用和Web端任务展示。

### 2. 核心贡献

> 设计Supervisor路由型问答图和Planner—Specialist—Reviewer—Writer协作图；构建FMEA与VDA 6.4双领域知识库；实现结构化业务生成、规则校验和有限修复；完成FastAPI、React、PostgreSQL、Milvus和SSE组成的完整应用链路。

### 3. 最值得深入讲的技术点

- 为什么路由型多Agent与协作型多Agent要分开。
- 文档结构感知分块与表格多粒度检索。
- Pydantic数据契约与Verifier业务校验的区别。
- 为什么先生成JSON，再确定性渲染Markdown。
- 如何通过引用Allowlist限制模型虚构来源。
- 为什么Repair最多执行一次。
- AgentState、短期记忆和长期记忆的边界。
- Run/Step持久化如何支持中间过程追踪。
- 为什么当前Redis不是核心记忆组件。

### 4. 必须诚实说明的边界

- 当前是可本地部署的原型，不是生产系统。
- 图片与扫描PDF未完成解析。
- Memory V2尚未实现。
- 销售协作真实Live评测不足。
- R&D与Quality当前串行执行。
- 主Supervisor尚未统一调度全部业务工作流。

---

## 二十三、项目总结

本项目已经从一个简单的领域问答Demo演进为包含以下能力的行业智能体平台：

- 路由型多智能体问答。
- 协作型多智能体售前方案生成。
- 双领域RAG知识库。
- 文档结构感知分块与表格多粒度检索。
- PFMEA、审核和报告独立工作流。
- Pydantic结构化输出。
- Verifier与单次修复。
- Skills和确定性模板渲染。
- 业务产物、版本与协作步骤持久化。
- 会话短期记忆。
- JWT认证、多会话和SSE流式Web应用。
- 自动化回归测试与阶段路线图。

它当前最有价值的部分并不是堆叠了多少Agent，而是已经形成了清晰的工程边界：

- 文档知识由RAG提供。
- 任务状态由LangGraph State传递。
- Agent之间通过结构化Schema交接。
- 业务正确性由Verifier补充约束。
- 最终产物由确定性渲染器输出。
- 可追溯事实由PostgreSQL保存。
- 语义索引由Milvus承担。
- 尚未实现的长期能力被明确放入Phase路线图，而没有冒充现有功能。

这使项目既能作为当前可运行原型，也具备继续向协作评测、任务恢复、长期记忆、案例系统和生产化演进的基础。
