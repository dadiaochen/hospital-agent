# 实施索引

## 1. 使用说明

本文只提供实施内容索引，不维护独立阶段编号。阶段顺序、状态和验收标准以 `docs/DEVELOPMENT_ROADMAP.md` 为唯一权威来源。

## 2. 当前实施序列

| 路线图阶段 | 内容 | 当前状态 |
| --- | --- | --- |
| 4A | 产品重基线、共享业务契约、Provider Mode、SourceRef 和文档统一 | 已完成 |
| 4B | 完整后端 Agent：Provider、工具、向量优先 RAG、三条业务子图、API、持久化、安全与评测 | 下一阶段 |
| 4C | 完整产品交付：成熟患者端、前后端闭环、E2E、评测、Docker、可观测性和材料收口 | 最终阶段 |

## 3. 下一阶段交付重点

4B 作为完整后端阶段，应一次性交付：

- Provider 公共接口、错误契约和运行模式配置。
- HospitalProvider、PharmacyProvider、OnlineConsultationProvider、GeoProvider、NotificationProvider、MedicalDocumentParser、MedicalVisionProvider 的 mock 实现。
- Tool Registry 到 Provider 的统一适配。
- Provider 来源转换为 `SourceRef`。
- Embedding、向量索引、关键词精确匹配、混合召回、重排和检索降级。
- 智能预问诊、家庭慢病用药、报告解读三条 LangGraph 有界业务子图。
- 业务 API、任务续跑、草稿确认、来源查询、运行记录和所需持久化。
- Agent 安全、人工确认、成员隔离、RunTrace、EvaluatorAgent 和 RAG 评测数据采集。
- 不依赖外部网络的完整后端回归测试。

4C 只做完整产品交付，不再拆出新的后续阶段：

- 成熟患者端覆盖三条业务线和完整状态。
- 前后端端到端闭环、浏览器 E2E、Harness 与六项 RAG 指标。
- Docker Compose 一键运行、结构化日志和关键链路观测。
- 删除过渡实现并完成 README、简历、面经和演示材料的事实校准。

## 4. 验收原则

- 每阶段只声明仓库中真实实现并通过测试的能力。
- mock、sandbox、real 数据和运行结果必须可区分。
- 新医疗输出必须有来源、安全检查和人工确认边界。
- RAG 指标在真实评测执行前只能写为“已定义”或“目标”，不能写成已达成。
- 4C 验收通过即视为当前产品范围完成，不以“未来再补前端、评测或部署”作为收尾。
