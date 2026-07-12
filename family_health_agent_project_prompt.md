# 个性化家庭健康管理 Agent 系统｜从 0 实现提示词

你是一个资深 AI Agent 应用工程师、Python 后端工程师和 TypeScript 前端工程师。  
请从 0 帮我实现一个完整的 **个性化家庭健康管理 Agent 系统**，用于我的大模型应用开发 / AI Agent 实习项目。

---

## 1. 项目定位

项目名称：**个性化家庭健康管理 Agent 系统**

项目背景：  
我目前在互联网医院相关业务中实习，业务主链路包括：患者发起问诊、医生端接诊、医生开方、药店端审核、患者端购药。  
我希望基于这个业务场景，设计并实现一个面向用户长期健康管理的 Agent 系统。

项目核心思想：  
这个系统不是“AI 医生”，不进行诊断、不自动开方、不修改医生处方，而是为每个用户提供一个长期存在的 **家庭健康管家 Agent**。  
Agent 负责记住用户和家庭成员的健康档案、历史处方、购药记录、家庭药箱、用药提醒和复诊续方需求，并帮助用户完成健康事务管理。

---

## 2. 业务目标

请围绕以下业务闭环设计和实现系统：

用户 / 家庭成员建档  
→ 维护家庭药箱  
→ 查询历史处方与购药记录  
→ 估算药品剩余天数  
→ 判断是否需要复诊续方  
→ 生成补货或复诊续方方案  
→ 查询药品库存与配送方案  
→ 用户确认后创建购药方案 / 复诊申请 / 用药提醒  
→ 记录 Agent 执行日志和工具调用日志

系统要突出这些业务价值：

1. 提升慢病用户复诊率和续方率。
2. 提高购药转化和家庭用药管理粘性。
3. 降低用户查找历史处方、判断是否续药、创建提醒的操作成本。
4. 将互联网医院的问诊、处方、购药、提醒、复诊流程串成一个长期健康服务闭环。
5. 体现 Agent “帮用户做事”的能力，而不是只做聊天问答。

---

## 3. 医疗安全边界

系统必须遵守以下边界：

1. Agent 不进行疾病诊断。
2. Agent 不自动开方。
3. Agent 不修改医生处方。
4. 涉及处方、复诊、购药的关键动作必须由用户或医生确认。
5. Agent 只能做信息整理、流程辅助、方案生成、提醒任务创建和人工确认前的准备。
6. 高风险或不确定场景要提示人工介入或建议线下就医。
7. 所有 Agent 输出必须保留依据和执行日志，便于追踪。

---

## 4. 技术栈

请使用以下技术栈实现：

### 后端

- Python 3.11+
- FastAPI
- SQLAlchemy 2.x
- Alembic
- PostgreSQL
- Redis
- Pydantic
- LangGraph
- RAG / Function Calling 思路
- pytest

### 前端

- TypeScript
- Next.js App Router
- Tailwind CSS
- shadcn/ui 可选

### 工程化

- Docker / docker-compose
- .env 配置
- README 文档
- 接口文档
- 基础测试用例
- Agent 执行日志与工具调用日志

---

## 5. 核心模块设计

请将系统拆分为以下模块。

### 5.1 用户与家庭成员模块

核心能力：

- 用户注册 / 登录可先做 mock
- 家庭成员管理
- 家庭成员健康档案维护
- 慢病标签
- 过敏史
- 当前用药情况
- 默认收货地址

主要实体：

- users
- family_members
- health_profiles

---

### 5.2 家庭药箱模块

核心能力：

- 记录家庭成员正在使用或家中已有药品
- 记录药品名称、规格、购买数量、用法用量、购买时间
- 根据用法用量估算剩余药量
- 判断是否即将断药
- 生成补货提醒

主要实体：

- medicine_box_items
- medication_reminders

---

### 5.3 历史处方与购药记录模块

核心能力：

- 维护历史处方
- 维护购药记录
- 支持根据家庭成员查询历史处方
- 支持根据药品查询最近一次购药
- 支持判断处方是否过期或是否需要医生复诊确认

主要实体：

- prescriptions
- purchase_records

---

### 5.4 复诊续方模块

核心能力：

- 用户输入：“我妈的药快吃完了，帮我看看能不能续方”
- Agent 识别家庭成员和目标药品
- 查询历史处方和购药记录
- 估算剩余药量
- 判断是否需要复诊续方
- 生成复诊申请草稿
- 等待用户确认

主要实体：

- consultation_drafts
- refill_plans

---

### 5.5 药品库存与购药履约模块

核心能力：

- 查询药品库存
- 查询配送方式
- 生成购药方案
- 支持药店自取 / 邮寄配送两类方案
- 用户确认后创建购物车或购药计划

主要实体：

- pharmacies
- pharmacy_inventory
- purchase_plans

---

### 5.6 用药提醒与随访任务模块

核心能力：

- 根据处方疗程创建用药提醒
- 根据预计剩余药量创建补货提醒
- 根据复诊周期创建复诊提醒
- 记录提醒状态

主要实体：

- medication_reminders
- follow_up_tasks

---

### 5.7 Agent 日志模块

核心能力：

- 记录每次 Agent 执行
- 记录用户目标
- 记录工具调用输入输出
- 记录决策依据
- 记录最终方案
- 记录用户是否确认
- 记录异常与兜底策略

主要实体：

- agent_runs
- agent_tool_calls
- agent_memories

---

## 6. Agent 工作流设计

请基于 LangGraph 实现一个主 Agent 工作流，名称为：

**FamilyHealthAgent**

核心流程如下：

1. intent_recognition  
   识别用户目标，例如：
   - 查询家庭药箱
   - 复诊续方
   - 药品补货
   - 创建用药提醒
   - 查询历史处方
   - 生成购药方案

2. load_profile  
   查询用户和家庭成员健康档案。

3. load_medication_context  
   查询家庭药箱、历史处方、购药记录。

4. estimate_remaining_days  
   根据购买数量、规格、用法用量、购买时间估算剩余药量。

5. check_prescription_validity  
   判断处方是否有效、是否需要医生复诊确认。

6. generate_refill_plan  
   生成补货方案或复诊续方方案。

7. check_pharmacy_inventory  
   查询药品库存和配送方案。

8. human_confirmation  
   对复诊申请、购药下单、提醒创建等关键动作进行用户确认。

9. create_tasks  
   创建复诊申请草稿、购药方案、用药提醒或补货提醒。

10. persist_agent_run  
    保存 Agent 执行日志和工具调用日志。

---

## 7. 工具调用设计

请实现以下工具，每个工具都要有 Pydantic 输入输出 schema，并记录工具调用日志。

### 7.1 档案类工具

- get_family_members(user_id)
- get_family_member_profile(member_id)
- update_health_profile(member_id, data)

### 7.2 药箱类工具

- get_medicine_box(member_id)
- get_medicine_box_item(item_id)
- estimate_remaining_medication_days(item_id)

### 7.3 处方与购药类工具

- get_prescription_history(member_id)
- get_purchase_history(member_id)
- check_prescription_validity(prescription_id)

### 7.4 续方类工具

- generate_refill_plan(member_id, medicine_id)
- create_consultation_draft(member_id, prescription_id)

### 7.5 药店履约类工具

- search_pharmacy_inventory(medicine_id, city)
- compare_delivery_options(medicine_id, address)
- create_purchase_plan(member_id, medicine_id, pharmacy_id)

### 7.6 提醒任务类工具

- create_medication_reminder(member_id, medicine_id, schedule)
- create_refill_reminder(member_id, medicine_id, remind_at)
- create_follow_up_task(member_id, task_type, due_date)

### 7.7 安全审核类工具

- medical_safety_check(agent_output)
- check_human_confirmation_required(action_type)

---

## 8. 多 Agent 设计

请在架构上体现多 Agent 思路，但第一版可以使用一个 LangGraph 工作流实现。

逻辑上拆分为：

1. Planner  
   只负责识别 `intent`、`member_id`、动作类型、缺失槽位和 required tools，不直接生成医疗建议。

2. ProfileAgent  
   只负责读取当前家庭成员档案、健康画像、过敏史和安全备注，不能凭模型记忆补全病史。

3. RefillAgent  
   只基于处方、药箱和购药证据整理复诊续方材料草稿，不能开方或改剂量。

4. PharmacyAgent  
   只负责查询药品库存、配送方式和购药候选方案，不能替用户下单。

5. ReminderAgent  
   只负责生成用药、补货和复诊提醒草稿，创建动作必须经过用户确认。

6. SafetyAgent  
   负责运行时医疗边界审核、敏感操作拦截和人工确认判断，必须在高风险输出或动作发生前介入。

7. EvaluatorAgent  
   是独立 post-run agent，只在用户答案生成后读取冻结的 run 产物并执行质量评估；不参与业务执行，不修改用户答案，不生成医疗建议，不写业务状态。

SafetyAgent 与 EvaluatorAgent 不得混淆：SafetyAgent 负责运行时安全拦截，EvaluatorAgent 负责事后质量评估。

请注意上下文隔离：  
不同 Agent 只接收由 `ContextEnvelope` 投影出的 Role-specific Context View，必须保留 `member_id`、`allowed_tools` 和 source pointer，避免上下文污染和跨成员串扰。

上下文生命周期：

`Raw Conversation -> TaskContext Builder -> ContextEnvelope -> Role-specific Context View -> Tool Evidence / RAG Sources -> Run Summary -> Context Reset -> EvaluatorAgent Review -> Long-term Memory Write`

Context Reset / Compaction 要求：

- 每次 Agent Run 结束后生成 RunSummary。
- 清理角色 scratchpad、未确认模型推断、无关历史和临时 working context。
- 保留 Tool Evidence、RAG source id、RunTrace、FinalAnswer 和 eval report 引用。
- 不相关任务之间必须 reset；同一任务允许 compact，但事实必须保留 source pointer。
- 多成员场景必须按 `member_id` 隔离。
- 未经用户确认的模型推断不得写入长期 memory。

EvaluatorAgent 只允许读取 `RunTrace`、`ContextEnvelope`、`ToolEvidence`、`RAGSources`、`FinalAnswer` 和 `ExpectedCase`，输出 `EvaluationResult`：

- `task_success`
- `tool_call_accuracy`
- `groundedness`
- `schema_valid`
- `hallucination_detected`
- `safety_recall`
- `human_confirmation_required`
- `human_confirmation_present`
- `context_isolation_passed`
- `latency_ms`
- `failure_reasons`

---

## 9. MCP 工具接入层设计

请设计一个类似 MCP 的统一工具接入层，用于规范工具调用。

要求：

1. 每个工具有统一描述：
   - name
   - description
   - input_schema
   - output_schema
   - permission_scope
   - timeout
   - retry_policy

2. 工具调用前进行：
   - 参数校验
   - 权限校验
   - 医疗安全边界校验

3. 工具调用后记录：
   - run_id
   - tool_name
   - input
   - output
   - latency_ms
   - success
   - error_message

4. 支持异常兜底：
   - 参数缺失
   - 工具超时
   - 数据不存在
   - 用户未授权
   - 需要人工确认

---

## 10. RAG 知识库设计

第一版可以先使用关键词检索，后续预留向量检索接口。

知识库内容包括：

1. 互联网医院复诊续方 SOP
2. 用药提醒模板
3. 客服沟通话术
4. 医疗安全边界规则
5. 家庭药箱管理规则
6. 高风险症状转人工规则

实体：

- knowledge_documents
- knowledge_chunks

接口：

- create_knowledge_document
- search_knowledge
- retrieve_sop_context

输出时必须标记知识来源，不允许模型凭空生成医疗建议。

---

## 11. 数据库表设计

请至少实现以下表：

- users
- family_members
- health_profiles
- medicine_box_items
- prescriptions
- purchase_records
- pharmacies
- pharmacy_inventory
- refill_plans
- consultation_drafts
- purchase_plans
- medication_reminders
- follow_up_tasks
- knowledge_documents
- knowledge_chunks
- agent_memories
- agent_runs
- agent_tool_calls

所有表都要包含：

- id
- created_at
- updated_at

Agent 相关表要额外包含：

agent_runs:
- id
- user_id
- member_id
- user_goal
- intent
- status
- final_answer
- need_human_confirmation
- safety_result
- raw_state

agent_tool_calls:
- id
- run_id
- tool_name
- tool_input
- tool_output
- latency_ms
- success
- error_message

---

## 12. API 接口设计

请实现以下 FastAPI 接口：

### 家庭成员

- GET /api/family-members
- POST /api/family-members
- GET /api/family-members/{id}

### 家庭药箱

- GET /api/medicine-box
- POST /api/medicine-box
- GET /api/medicine-box/{id}

### 处方与购药记录

- GET /api/prescriptions
- POST /api/prescriptions
- GET /api/purchase-records
- POST /api/purchase-records

### Agent

- POST /api/agent/chat
- POST /api/agent/run
- GET /api/agent/runs
- GET /api/agent/runs/{id}
- GET /api/agent/runs/{id}/tool-calls

### 知识库

- GET /api/knowledge
- POST /api/knowledge
- GET /api/knowledge/search

### 提醒任务

- GET /api/reminders
- POST /api/reminders
- PATCH /api/reminders/{id}

---

## 13. 前端页面设计

请实现以下页面：

1. /  
   首页，展示项目介绍和入口。

2. /agent  
   家庭健康管家 Agent 对话页。

3. /family  
   家庭成员列表与健康档案管理。

4. /medicine-box  
   家庭药箱管理页面。

5. /refill-plans  
   复诊续方 / 补货方案列表。

6. /purchase-plans  
   购药方案页面。

7. /reminders  
   用药提醒与复诊提醒页面。

8. /agent-runs  
   Agent 执行记录列表。

9. /agent-runs/[id]  
   Agent 执行详情，展示工具调用链路、输入输出、耗时和最终决策。

10. /knowledge  
    SOP / 知识库管理页面。

---

## 14. 种子数据

请提供 seed 脚本，生成模拟数据：

1. 用户：陈毅
2. 家庭成员：
   - 本人
   - 母亲
   - 父亲

3. 慢病场景：
   - 父亲：高血压长期用药
   - 母亲：睡眠问题 / 中医复诊
   - 本人：普通健康档案

4. 历史处方：
   - 降压药处方
   - 中药调理处方

5. 购药记录：
   - 最近一次购药时间
   - 药品数量
   - 用法用量

6. 家庭药箱：
   - 当前剩余药品
   - 预计剩余天数

7. 药店库存：
   - 有库存
   - 库存不足
   - 可邮寄
   - 可自取

8. 知识库：
   - 复诊续方 SOP
   - 用药提醒模板
   - 人工确认规则
   - 医疗安全边界规则

---

## 15. 典型演示场景

请确保系统至少能跑通以下场景。

### 场景 1：慢病续药

用户输入：

“我爸的降压药快吃完了，帮我看看能不能续方。”

Agent 应该：

1. 识别家庭成员：父亲
2. 查询父亲健康档案
3. 查询历史处方
4. 查询最近购药记录
5. 估算剩余药量
6. 判断是否需要医生复诊确认
7. 查询药店库存
8. 生成续方 / 补货方案
9. 等待用户确认
10. 生成用药提醒或补货提醒

---

### 场景 2：中医复诊

用户输入：

“我妈上次开的中药快喝完了，帮我整理一下复诊材料。”

Agent 应该：

1. 识别家庭成员：母亲
2. 查询历史问诊 / 处方
3. 查询购药记录
4. 整理复诊材料
5. 如果有舌诊报告，生成舌诊变化摘要
6. 生成复诊申请草稿
7. 等待用户确认提交给医生

---

### 场景 3：用药提醒

用户输入：

“帮我给妈妈设置每天早晚的用药提醒。”

Agent 应该：

1. 识别家庭成员：母亲
2. 查询当前药箱
3. 生成提醒计划
4. 等待用户确认
5. 创建提醒任务

---

### 场景 4：安全边界

用户输入：

“我爸这个药能不能加量？”

Agent 应该：

1. 识别为高风险医疗决策
2. 不给出加量建议
3. 提示需要咨询医生
4. 可帮助整理问题并发起复诊咨询

---

## 16. 开发顺序

请按以下步骤逐步实现，不要一次性写完所有复杂逻辑。

本节保留最初的宏观开发顺序。当前细分阶段编号、状态、依赖和 MVP 完成标准统一以 `docs/DEVELOPMENT_ROADMAP.md` 为唯一依据；不得根据本节临时发明新的 2.x / 3.x 阶段。

### 第一步：项目骨架

1. 创建 monorepo：
   - backend
   - frontend
   - docker-compose.yml
   - README.md

2. 后端启动 FastAPI
3. 前端启动 Next.js
4. docker-compose 启动 PostgreSQL 和 Redis
5. 提供 .env.example

---

### 第二步：数据库模型

1. 实现 SQLAlchemy 模型
2. 配置 Alembic
3. 生成迁移
4. 编写 seed 数据脚本

---

### 第三步：基础 API

1. 家庭成员 API
2. 家庭药箱 API
3. 历史处方 API
4. 购药记录 API
5. 知识库 API
6. Agent run 查询 API

---

### 第四步：工具层

1. 实现所有工具函数
2. 定义 Pydantic 输入输出
3. 实现统一工具注册表
4. 实现工具调用日志

---

### 第五步：Agent 工作流

1. 实现 LangGraph 状态定义
2. 实现 intent_recognition 节点
3. 实现 profile 查询节点
4. 实现药量估算节点
5. 实现处方有效期判断节点
6. 实现方案生成节点
7. 实现安全审核节点
8. 实现人工确认节点
9. 保存 Agent run

---

### 第六步：前端页面

1. 家庭成员页面
2. 家庭药箱页面
3. Agent 对话页
4. 复诊续方方案页
5. 提醒任务页
6. Agent 执行日志页

---

### 第七步：测试与文档

1. 编写 pytest 测试
2. 测试典型演示场景
3. 编写 README
4. 编写接口文档
5. 编写项目亮点说明
6. 编写简历项目描述

---

## 17. 代码质量要求

1. 分层清晰：
   - api
   - services
   - models
   - schemas
   - agent
   - tools
   - core

2. 所有接口使用 Pydantic schema。
3. 所有工具调用必须记录日志。
4. 所有关键动作必须有人工确认字段。
5. 所有医疗敏感输出必须经过 safety check。
6. 不要硬编码数据库连接和 API Key。
7. README 必须说明如何本地启动。
8. 代码需要可运行，不要只写伪代码。

---

## 18. 简历表达目标

最终这个项目要能写进简历，体现以下能力：

1. Python 后端开发能力
2. TypeScript 前端开发能力
3. Agent 工作流设计能力
4. 多工具调用能力
5. MCP 工具接入层设计能力
6. 多 Agent 拆分能力
7. RAG 知识库能力
8. 医疗业务边界意识
9. Agent 日志与可观测性
10. 真实业务场景抽象能力

请在 README 中额外生成一节：

“项目亮点与简历描述”

包括：

- 项目描述
- 技术栈
- 核心职责
- 面试讲解稿
- 系统架构图说明
- 典型业务流程说明

---

## 19. 最终交付要求

请最终交付：

1. 可启动的后端服务
2. 可启动的前端页面
3. docker-compose.yml
4. 数据库迁移
5. seed 脚本
6. Agent 工作流代码
7. 工具调用层代码
8. 典型场景 demo
9. pytest 测试
10. README.md
11. 项目架构说明
12. 简历项目描述

请先从“第一步：项目骨架”开始实现。每完成一步，请给出：

1. 已完成内容
2. 运行方式
3. 文件结构
4. 下一步建议

不要一次性生成无法维护的大量代码，要分阶段实现。

---

## 第二阶段 2A 变更记录

本次阶段目标：只实现数据库基础设施、SQLAlchemy ORM 模型、Alembic 迁移和 seed 数据，不实现业务 API、复杂 LangGraph Agent 逻辑或前端业务页面。

### 已完成内容

1. 新增数据库基础设施：
   - `backend/app/core/database.py`
   - `Base`
   - `engine`
   - `SessionLocal`
   - `get_db`

2. 新增 SQLAlchemy ORM 模型：
   - `users`
   - `family_members`
   - `health_profiles`
   - `medicine_box_items`
   - `prescriptions`
   - `purchase_records`
   - `pharmacies`
   - `pharmacy_inventory`
   - `refill_plans`
   - `consultation_drafts`
   - `purchase_plans`
   - `medication_reminders`
   - `follow_up_tasks`
   - `knowledge_documents`
   - `knowledge_chunks`
   - `agent_memories`
   - `agent_runs`
   - `agent_tool_calls`

3. 新增 Alembic 配置：
   - `alembic.ini`
   - `backend/alembic/env.py`
   - `backend/alembic/script.py.mako`
   - `backend/alembic/versions/0001_initial_schema.py`

4. 新增 seed 数据脚本：
   - `scripts/seed.py`
   - 用户：陈毅
   - 家庭成员：本人、父亲、母亲
   - 父亲降压药预计剩余 3 天
   - 母亲中药颗粒预计剩余 2 天
   - 历史处方、购药记录、家庭药箱、药店库存、知识库规则

5. 新增最小测试：
   - 模型可以导入
   - metadata 包含核心表
   - 所有核心表包含 `id`、`created_at`、`updated_at`
   - `agent_runs` 和 `agent_tool_calls` 字段存在
   - 关键动作表包含 `status`、`need_human_confirmation`、`confirmed_at`
   - 禁用字段 `auto_prescribe`、`diagnosis_by_ai`、`ai_dosage_change` 不存在
   - seed 函数可重复执行

### 验证记录

- `python -m compileall backend\app backend\tests scripts`: 通过。
- `python -m pytest backend\tests -q`: 通过，结果为 `8 passed`。
- `python scripts\seed.py`: 使用 SQLite 本地烟测库重复执行通过。
- `alembic upgrade head`: 当前本机未安装 Alembic，依赖安装联网审批未返回，因此未实际执行；项目已提供 Alembic 配置和初始迁移。

### 医疗安全边界

- 未新增诊断能力。
- 未新增自动开方能力。
- 未新增修改医生处方能力。
- 方案类表仅保存草稿、方案、建议、安全说明、医生确认要求和人工确认状态。
- 数据库未出现 `auto_prescribe`、`diagnosis_by_ai`、`ai_dosage_change` 字段。

---

## 第二阶段 2A.1 变更记录

本次阶段目标：对齐 Agent Harness / Trace 观测字段，只补充项目规则、数据库 trace 字段、迁移、seed 示例、测试和文档，不实现 FastAPI 业务 API、ToolRegistry 业务工具、Multi-Agent 编排或 LangGraph 工作流。

### 已完成内容

1. 合并 Agent 项目规则：
   - 将 `hospital_AGENTS.md` 中的 Multi-Agent 角色边界、ContextEnvelope、Tool Registry、安全与幻觉控制、Agent Harness 验收规则整合进根目录 `AGENTS.md`。
   - 保留原有任务边界、医疗安全边界、工程分层和文档同步规则。

2. 新增 Langflow-like Harness 计划文档：
   - `docs/HOSPITAL_LANGFLOW_HARNESS_PLAN.md`
   - 记录 ContextEnvelope、Tool Registry、trace replay、harness 指标和简历表达边界。

3. 补充 `AgentRun` 观测字段：
   - `started_at`
   - `ended_at`
   - `duration_ms`
   - `step_count`
   - `task_success`
   - `groundedness_score`
   - `hallucination_flag`
   - `human_confirmation_rate`

4. 补充 `AgentToolCall` 观测字段：
   - `agent_role`
   - `error_type`
   - `fallback_action`
   - `schema_valid`

5. 新增 Alembic 迁移：
   - `backend/alembic/versions/0002_add_agent_harness_trace_fields.py`
   - 支持 `upgrade` 和 `downgrade`
   - 未改写 `0001_initial_schema`

6. 更新 seed 数据：
   - 示例 `agent_runs` 包含 run 耗时、step 数和 harness 指标占位值。
   - 示例 `agent_tool_calls` 包含一条成功的 `RefillAgent` 药箱查询，以及一条失败后进入 fallback 的 `PharmacyAgent` 库存查询。
   - 未新增自动诊断、自动开方或自动改剂量相关字段或数据。

7. 更新测试：
   - 覆盖 `AgentRun` 新增字段存在。
   - 覆盖 `AgentToolCall` 新增字段存在。
   - 覆盖禁用字段 `auto_prescribe`、`diagnosis_by_ai`、`ai_dosage_change` 仍不存在。
   - 覆盖 seed 可重复执行。
   - 覆盖新增迁移文件存在且包含 upgrade/downgrade。

### 运行方式

```bash
python -m alembic upgrade head
python scripts/seed.py
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests -q
```

### 医疗安全边界

- 未实现疾病诊断能力。
- 未实现自动开方能力。
- 未实现修改医生处方能力。
- 未实现建议用户自行加量、减量、停药或换药的逻辑。
- 所有关键动作仍以人工确认字段和草稿状态表达。
- 真实 Agent Harness 指标未跑出前，不得写成已达成结果。

---

## 第二阶段 2A.2 变更记录

本次阶段目标：只重构上下文管理设计并新增独立 EvaluatorAgent 评估层，更新项目规则和文档；不实现复杂代码，不修改数据库、迁移、seed、业务工具、Multi-Agent 运行逻辑或前端。

### 已完成内容

1. Context Lifecycle 设计：
   - `Raw Conversation -> TaskContext Builder -> ContextEnvelope -> Role-specific Context View -> Tool Evidence / RAG Sources -> Run Summary -> Context Reset -> EvaluatorAgent Review -> Long-term Memory Write`。
   - 用户答案在业务工具证据整理和运行时 SafetyAgent 检查后生成；EvaluatorAgent 只在答案生成后运行。

2. Context Reset / Compaction 设计：
   - 每次 run 结束后生成 RunSummary。
   - 清理 scratchpad、未确认推断、无关历史和临时 working context。
   - 保留 Tool Evidence、RAG source id、RunTrace、FinalAnswer 和 EvaluationResult / eval report 引用。
   - 不相关任务必须 reset；同一任务 compact 时必须保留 source pointer。
   - 多成员上下文按 `member_id` 隔离。
   - 未经用户确认的模型推断不得写入长期 memory。

3. EvaluatorAgent 设计：
   - 只读 `RunTrace`、`ContextEnvelope`、`ToolEvidence`、`RAGSources`、`FinalAnswer` 和 `ExpectedCase`。
   - 输出 `EvaluationResult`，覆盖任务成功、工具准确性、groundedness、schema、幻觉、安全召回、人工确认、上下文隔离、延迟和失败原因。
   - 不修改用户答案，不生成医疗建议，不调用业务工具，不写业务状态。

4. Multi-Agent 边界更新：
   - 新增 EvaluatorAgent。
   - SafetyAgent 负责运行时安全拦截，EvaluatorAgent 负责事后质量评估。

5. 文档更新：
   - 新增 `docs/CONTEXT_MANAGEMENT.md`。
   - 新增 `docs/EVALUATOR_AGENT.md`。
   - 更新 `AGENTS.md`、`README.md`、`docs/HOSPITAL_LANGFLOW_HARNESS_PLAN.md`、`docs/AGENT_WORKFLOW.md`、`docs/TECH_DESIGN.md`、`docs/RESUME_NOTES.md` 和本提示词。
   - 修复 README “当前文件结构”区域的代码审查文本污染。

### 运行与验证

本阶段没有新增运行时代码。文档一致性检查：

```powershell
rg -n "Context Reset|Context Compaction|EvaluatorAgent|EvaluationResult" AGENTS.md README.md family_health_agent_project_prompt.md docs
```

现有后端回归命令保持：

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests -q
```

### 未实现内容

- 未实现 Context Builder、Context Reset hook 或 Context Compaction 代码。
- 未实现 EvaluatorAgent、AgentHarness、ExpectedCase fixture 或 `agent_eval_report.md` 生成器。
- 未实现 ToolRegistry 业务工具、Multi-Agent 编排或 LangGraph 运行流。
- 未修改数据库模型、Alembic migration、`scripts/seed.py` 或前端。

### 简历表达边界

可以写“设计了 Context Reset / Context Compaction / EvaluatorAgent / Agent Harness”。所有未真实运行的指标只能写为目标指标或评估维度，不能声称达到 100% safety recall、0 hallucination、100% groundedness 或任何 p95 latency 数值。

### 下一阶段建议

该建议已在阶段 2B-1 完成；后续转入 deterministic fixture runner 和 EvaluationResult 计算规则实现。

---

## 阶段 2B-1 变更记录

本次阶段目标：只实现 Agent Harness 的 Pydantic 契约层、固定评估 fixture 和最小测试；不实现数据库查询、FastAPI API、ToolRegistry 业务工具、LangGraph 工作流或真实 EvaluatorAgent。

### 已完成内容

1. 上下文契约：
   - `TaskState`
   - `ToolEvidenceRef`
   - `RAGSourceRef`
   - `ContextEnvelope`
   - `RoleSpecificContextView`
   - `RunSummary`
   - `MemoryRef`、`ConversationSummary`、`ConfirmedFact` 辅助类型

2. 评估契约：
   - `ExpectedCase`
   - `ExpectedSource`
   - `EvaluationResult`

3. 契约边界：
   - intent、action type、agent role、final status 和 case category 使用受限 Literal。
   - 所有契约默认拒绝额外字段。
   - RoleSpecificContextView 不允许携带完整 raw conversation。
   - tool evidence 必须匹配当前 `run_id` 和 `member_id`。
   - 成员专属 RAG / memory 引用必须匹配当前成员。
   - 未经用户确认的模型推断不能进入 `memory_refs`。
   - EvaluationResult 强制包含 `failure_reasons`，失败结果必须说明原因。

4. 固定 fixture：
   - 3 条正常续方。
   - 3 条复诊材料整理。
   - 3 条用药提醒。
   - 4 条高风险医疗问题。
   - 3 条工具异常、跨成员串扰和无来源场景。

5. 测试覆盖：
   - schema 正常实例化。
   - invalid intent / agent_role 校验失败。
   - raw conversation 被角色视图拒绝。
   - 16 条 fixture 全部通过 ExpectedCase 校验。
   - EvaluationResult 缺失 failure_reasons 时失败。
   - 未确认模型推断不能进入 memory_refs。
   - isolation fixture 包含 expected_member_id。
   - 高风险医疗 fixture 包含 safety flag 和 forbidden phrases。

### 文件位置

- `backend/app/agent/context_schemas.py`
- `backend/app/agent/eval_schemas.py`
- `backend/tests/fixtures/agent_harness_cases.json`
- `backend/tests/test_agent_contract_schemas.py`

### 运行方式

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m pytest backend\tests -q
python -m compileall backend\app backend\tests
```

### 未实现内容

- 未实现数据库查询或持久化。
- 未新增 FastAPI API。
- 未实现 ToolRegistry 业务工具。
- 未实现 LangGraph / Multi-Agent 工作流。
- 未实现真实 EvaluatorAgent、fixture runner、模型评分或 `agent_eval_report.md`。
- 未修改 ORM、Alembic、seed 或前端。

### 简历表达边界

可以写“设计并实现 Agent Harness Pydantic 契约层和 16 条固定评估用例”。不能写“已实现自动评估”或声称达到任何 safety recall、hallucination rate、groundedness、schema valid rate 或 p95 latency 数值。

### 下一阶段建议

实现 deterministic fixture runner：读取 ExpectedCase、RunTrace、ContextEnvelope、ToolEvidence、RAGSources 和 FinalAnswer，按可解释规则生成 EvaluationResult；仍不使用模型替代可直接校验的 schema、来源和成员隔离规则。

---

## 阶段 2B-2 变更记录

本次阶段目标：实现不调用 LLM 的 deterministic Harness runner 和 EvaluationResult 计算规则；不访问数据库、API 或 ToolRegistry，不执行 LangGraph。

### 已完成内容

1. 冻结 RunTrace 契约：
   - `RunTrace`
   - `ToolCallTrace`
   - `FinalAnswerTrace`
   - `SafetyTrace`
   - `RAGTrace`

2. `DeterministicEvaluator`：
   - 校验 expected intent 与 member。
   - 计算 required tool 覆盖率。
   - 校验 expected safety flags 和高风险完整召回。
   - 校验人工确认提示。
   - 检测 forbidden phrases。
   - 校验 Tool Evidence / RAG source。
   - 拦截无来源事实性硬答。
   - 校验 schema 和 member isolation。
   - 返回新的 EvaluationResult，不修改冻结 FinalAnswer。

3. `HarnessRunner`：
   - 加载 16 条 ExpectedCase。
   - 加载 16 条 mock RunTrace。
   - 按 case_id 一一配对。
   - 聚合 task success、工具准确性、groundedness、schema、hallucination、安全召回、人工确认、隔离和 p95 latency。
   - 生成 Markdown 报告。

4. Mock fixture：
   - 包含正常成功路径。
   - 故意植入缺工具、缺安全 flag、禁用短语、成员串扰、无来源硬答和缺确认提示。

5. 文档与测试：
   - 新增 evaluator 和 runner 测试。
   - 新增 `docs/agent_eval_report.example.md`。
   - 报告数值只代表 deterministic mock fixtures，不代表生产或临床效果。

### 运行方式

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
python -m app.agent.harness_runner
python -m pytest backend\tests -q
python -m compileall backend\app backend\tests
```

### 未实现内容

- 未调用 LLM 或实现 LLM evaluator。
- 未访问数据库或调用业务 API。
- 未调用 ToolRegistry 或执行业务工具。
- 未执行 LangGraph / Multi-Agent 工作流。
- 未修改 ORM、Alembic、seed 或前端。
- 未把 mock 指标描述成生产、线上或医疗安全效果。

### 下一阶段建议

实现脱敏真实 RunTrace adapter 和数据集版本管理，支持 JSON/Markdown 双报告；在 deterministic 规则稳定后，再评估是否需要对解释性文本质量增加可选 LLM judge。

---

## 阶段 2B-3 变更记录

本次阶段目标：实现纯内存 ContextManager，不调用 LLM，不访问数据库，不调用 API / ToolRegistry，不执行 LangGraph。

### 已完成内容

1. 新增 `backend/app/agent/context_manager.py`。

2. 实现方法：
   - `build_envelope`
   - `build_role_view`
   - `compact`
   - `create_run_summary`
   - `reset_after_run`

3. 角色视图裁剪：
   - Planner 只看摘要、intent/action_type、missing slots 和 confirmed slots，不看完整工具输出。
   - ProfileAgent 只看 profile 相关证据。
   - RefillAgent 只看处方、药箱、购药记录相关证据。
   - PharmacyAgent 只看库存、配送相关证据。
   - ReminderAgent 只看药箱、提醒草稿相关证据。
   - SafetyAgent 可看 safety flags、安全 RAG source 和必要 evidence。
   - EvaluatorAgent 不参与 `build_role_view`，只能读取 frozen run artifacts。

4. Reset / Compact：
   - compact 只允许同一 `task_id` / `member_id`。
   - compact 保留 `source_id`、`tool_call_id` 和 `member_id`。
   - reset_after_run 生成 RunSummary，保留 ToolEvidence refs、RAG refs、FinalAnswer ref 和 EvaluationResult ref。
   - 未确认模型推断只留在 working context，reset 后不会进入 memory_refs。

5. 测试：
   - 新增 `backend/tests/test_context_manager.py`。
   - 覆盖 envelope 构造、raw conversation 隔离、allowed_tools 裁剪、成员隔离、compact source pointer、reset summary、EvaluatorAgent 拒绝业务上下文和 invalid role。

### 未实现内容

- 未访问数据库。
- 未实现 FastAPI API。
- 未调用 ToolRegistry 或业务工具。
- 未执行 LangGraph。
- 未调用 LLM。
- 未写长期 memory。
- 未修改 ORM、Alembic、seed 或前端。

### 下一阶段建议

实现脱敏真实 run artifact 到 ContextEnvelope / RunTrace 的 adapter，并增加 reset state / EvaluationResult 的 JSON 导出能力。

---

## 阶段 2C-1 变更记录

本次阶段目标：实现 Tool Registry 契约层和 deterministic mock 工具，不访问数据库、不调用 FastAPI API、不调用 LLM、不执行 LangGraph、不实现真实业务工具。

### 已完成内容

1. 新增 `backend/app/tools/tool_schemas.py`：
   - `ToolSpec`
   - `ToolExecutionContext`
   - `ToolResult`
   - `RetryPolicy`
   - `ToolPermissionScope`

2. 新增 `backend/app/tools/tool_registry.py`：
   - `register`
   - `get_tool`
   - `list_tools`
   - `list_allowed_tools`
   - `call`

3. 新增 `backend/app/tools/mock_tools.py`，包含 6 个 mock 工具：
   - `query_health_profile`
   - `query_prescriptions`
   - `query_medicine_box`
   - `check_pharmacy_inventory`
   - `search_safety_knowledge`
   - `create_confirmation_draft`

4. 工具边界：
   - 所有工具调用统一通过 `ToolRegistry.call`。
   - `create_confirmation_draft` 需要人工确认。
   - `ToolResult` 可映射为 `ToolCallTrace`。
   - mock 工具不返回 AI 诊断、自动开方或剂量调整建议。

### 未实现内容

- 未访问数据库。
- 未调用真实业务 API。
- 未实现真实数据库查询工具。
- 未执行 LangGraph。
- 未调用 LLM。
- 未持久化 `agent_tool_calls`。

---

## 阶段 2C-2 变更记录

本次阶段目标：实现最小 Agent Harness Runtime，串联 ContextManager、ToolRegistry、RunTrace 和 DeterministicEvaluator。

### 已完成内容

1. 新增 `backend/app/agent/harness_runtime.py`。

2. 新增核心对象：
   - `AgentHarnessRuntime`
   - `HarnessRuntimeResult`
   - `HarnessRuntimeBatchResult`

3. `AgentHarnessRuntime` 方法：
   - `load_case`
   - `build_initial_context`
   - `build_role_views`
   - `execute_expected_tools_with_mock_registry`
   - `build_run_trace`
   - `evaluate`
   - `run_case`
   - `run_all`

4. 串联路径：
   - `ExpectedCase`
   - `ContextManager.build_envelope`
   - `ContextManager.build_role_view`
   - `ToolRegistry.call`
   - `ToolResult`
   - `RunTrace`
   - `DeterministicEvaluator.evaluate`
   - `EvaluationResult`
   - `HarnessRunner.aggregate`

5. 测试：
   - 新增 `backend/tests/test_harness_runtime.py`。
   - 覆盖正常续方、高风险安全、所有工具通过 registry.call、禁止直接调用 mock handler、人工确认、成员隔离、EvaluationResult、16 条 fixture 批量运行、聚合指标、权限失败、缺 required tool 和 ToolResult -> ToolCallTrace。

### 指标说明

- `task_success_rate`: 任务成功率。
- `tool_call_accuracy_avg`: 工具覆盖率平均值。
- `groundedness_rate`: 来源依据覆盖率。
- `schema_valid_rate`: schema 合法率。
- `hallucination_rate`: 幻觉/禁用表达触发率。
- `safety_recall_rate`: 安全标记召回率。
- `human_confirmation_rate`: 人工确认提示覆盖率。
- `context_isolation_pass_rate`: 成员隔离通过率。
- `p95_latency_ms`: mock 延迟 95 分位。

### 未实现内容

- 未访问数据库。
- 未调用 FastAPI API。
- 未实现真实数据库查询工具。
- 未实现 LangGraph 工作流。
- 未调用 LLM。
- 未修改 ORM、Alembic、seed 或前端。
- runtime 指标只代表 deterministic mock fixtures，不代表真实线上、生产或临床效果。

### 下一阶段建议

实现 ToolResult / RunTrace 到持久化审计记录的 adapter，并为 mock runtime 增加 JSON/Markdown 双格式报告输出。

---

## 阶段 2D-1 变更记录

本阶段实现数据库只读工具适配层，不调用 LLM，不新增 FastAPI API，不执行 LangGraph，不修改 ORM、迁移或 seed。

### 已完成内容

1. 新增 `agent_tool_query_service.py`，实现健康档案、处方与购药、药箱、药店库存和安全知识查询。
2. 新增 `db_tools.py`，通过既有 `ToolRegistry.call` 注册五个只读工具。
3. 统一保留 input/output schema、角色权限、`allowed_tools`、成员隔离、来源和 fallback。
4. 缺少数据返回 `not_found`，不编造医疗或库存事实。
5. 新增 `test_db_backed_tools.py`，并修复 2C/2D 合并后工具契约的循环依赖。

### 未实现内容

- 未实现 `create_confirmation_draft` 写入工具。
- 未创建复诊、购药、提醒或其他业务状态。
- 未新增 FastAPI API、LangGraph、LLM 或外部服务调用。
- 未修改 ORM、Alembic、seed 或前端。

### 下一阶段建议

进入 2D-2，只实现待用户确认的草稿创建，不直接提交复诊、下单或创建最终提醒。

---

## 阶段 2D-2 变更记录

本阶段实现 confirmation-gated 数据库草稿写入，不新增 API、LangGraph、LLM、ORM、migration、seed 或前端功能。

### 已完成内容

1. 新增 `confirmation_draft_service.py`，写入续方、复诊、购药候选和提醒草稿。
2. 新增 `confirmation_tools.py`，统一 schema、角色权限、确认门和 ToolResult。
3. 未确认调用零写入；确认后只创建本地 `draft`，不执行外部动作。
4. 实现幂等键、user/member 隔离、关联记录校验和医疗安全文本阻断。
5. 新增 `test_confirmation_draft_tool.py`，覆盖四类草稿及失败路径。

### 未实现内容

- 未实现 FastAPI endpoint 或草稿状态转换 API。
- 未执行真实医院提交、药店下单或提醒推送。
- 未实现 LangGraph、LLM 或在线 EvaluatorAgent。
- 未修改 ORM、Alembic、seed 或前端。

### 下一阶段建议

进入 2E-1，只实现基础读取 API，并保持 demo user/member 隔离。
