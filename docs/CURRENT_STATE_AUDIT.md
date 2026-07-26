# 当前状态审计

## 1. 审计结论

本项目已经完成互联网医院慢病续方与家庭用药管理 MVP 的基础设施和一条可运行的 Agent 闭环，但尚未完成《家庭健康服务 Multi-Agent 最终产品与技术规范》中定义的三条完整业务线。

当前最合适的演进方式不是推倒重写，而是保留现有数据库、Tool Registry、上下文隔离、LangGraph、Model Gateway、运行记录和评测基础，在其上扩展业务领域与外部 Provider。

阶段编号、完成状态和实施顺序以 `docs/DEVELOPMENT_ROADMAP.md` 为唯一依据。

## 2. 已实现基线

| 能力 | 当前状态 | 说明 |
| --- | --- | --- |
| FastAPI、SQLAlchemy、Alembic、PostgreSQL、Redis | 已完成 | 后端基础设施与数据库模型可运行 |
| 家庭成员、健康档案、药箱、处方、药店库存 | 已完成 | 支撑原四个 MVP 场景 |
| Tool Registry 与六类业务工具 | 已完成 | 具备权限、超时、重试、确认和调用记录 |
| ContextEnvelope 与成员隔离 | 已完成 | 任务上下文按 `member_id` 隔离 |
| LangGraph 有界工作流 | 已完成 | 支持续方、提醒、购药和安全拦截 |
| Model Gateway | 已完成 | 支持确定性 Provider 和网络模型 Provider |
| RunTrace、RunSummary、Agent 评测基础 | 已完成 | 已有运行轨迹和事后评测契约 |
| 前端家庭健康与 Agent 运行页 | 已完成 | 展示当前 MVP 数据与运行轨迹 |

## 3. 与新产品规范的差距

| 新产品能力 | 当前基础 | 主要缺口 | 路线图 |
| --- | --- | --- | --- |
| 智能预问诊与分级导诊 | 安全规则、上下文、RAG 基础 | 症状结构化、红旗症状分流、医院科室 Provider、导诊草稿 | 4B-4C |
| 家庭医生、慢病与用药履约 | 原四场景基本覆盖 | 统一履约任务、在线问诊 Provider、通知 Provider、跨任务状态 | 4B-4C |
| 报告解读与长期健康档案 | 健康档案与知识库表 | 医疗文档解析、报告结构化、指标解释、趋势事件和写入确认 | 4B-4C |
| 可追溯 RAG | `knowledge_documents`、`knowledge_chunks`、RAG 引用 | 向量优先的语义召回、关键词精确匹配与降级兜底、通用 `SourceRef`、版本校验和六项专项指标 | 4A-4C |
| Provider Adapter | Tool Registry、Model Gateway | mock/sandbox/real 三种运行模式及七类 Provider | 4A-4B |
| 新业务 API 与前端 | 现有运行 API 和 Agent UI | 三条业务线的请求契约、状态页、来源展示与确认交互 | 4B-4C |

## 4. 本轮 4A 完成内容

- 将产品范围重设为三条业务线，并保留原四场景作为已实现基线。
- 新增 `BusinessDomain`、`ProviderMode`、`SourceType`、`SourceRef` 和 `BusinessRequestContext`。
- ToolSpec 新增版本字段，ToolExecutionContext 新增 Provider 运行模式。
- ToolResult 新增工具版本、Provider 运行模式、证据引用和可重试标记。
- 建立新的产品、业务流程、Agent 架构、工具契约、安全策略和实施索引文档。
- 将 RAG 明确为三条业务线的共享基础能力，并定义六项后续评测指标。

## 5. 本轮没有实现

- 未新增三条业务线的正式 API。
- 未新增医院、在线问诊、通知、报告解析或医疗视觉的真实 Provider。
- 未改造现有 LangGraph 业务运行路径。
- 未新增数据库迁移。
- 未宣称任何新 RAG 指标已经达到目标值。

## 6. 事实边界

文档中的“已完成”只指当前仓库中可运行、可测试的实现。“计划”“目标”“待实现”不应写入简历或面试回答作为已上线成果。所有外部医院、药店、在线问诊、通知、文档解析和医疗视觉数据，在真实接口接入前只能通过显式标记的 mock 或 sandbox Provider 提供。
