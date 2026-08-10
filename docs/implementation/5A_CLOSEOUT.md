# 5A 业务闭环与分层评测收口

## 交付

- 统一解析：文本、Markdown 表格、PDF 文本层和 RapidOCR 图片 OCR 分别处理，表格、章节与结构化指标汇聚为 `ParsedDocument`；只整理来源内容，不诊断、不提供治疗方案。
- 报告闭环：`POST /family-members/{member_id}/reports` 上传后直接返回 `ready` 结构，`GET /.../reports` 即为同成员历史；不创建报告确认草稿或健康记录事件。
- 最终回答质量门：在既有 Final Output Safety 后冻结。纯格式缺陷最多触发一次无 Tool 修复；没有来源的事实和安全失败不重试、直接阻断。
- 状态：质量门审计随既有 PostgreSQL Task Checkpoint 冻结；Redis 仅为带 TTL 的读缓存，未命中、失效或异常都回源 PostgreSQL。

## 验证

```powershell
$env:PYTHONPATH=(Resolve-Path 'backend').Path
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python.exe -B -m pytest backend\tests\test_document_parser_service.py backend\tests\test_final_answer_quality_gate.py backend\tests\test_read_api.py backend\tests\test_business_task_api.py::test_task8_checkpoint_is_authoritative_for_continuation_and_tracks_versions backend\tests\test_task_checkpoint_cache.py -q -p no:cacheprovider
```

结果：38 passed（入口治理、冻结 RAGAS、Triage 续跑、PDF 文本层、RapidOCR 图片、Markdown 表格、直接报告读取、质量门与 Checkpoint 回源）。另有一条既有 sandbox 降级测试在当前基线中返回 `needs_clarification` 而非旧断言的 `failed`，未将其计为本轮通过，也未更改其行为。

## 边界

- PDF 使用 `pypdf` 在服务端直接逐页提取文本；图片使用本地 RapidOCR + ONNX Runtime CPU，不向外部服务发送文件。
- 报告指标是可直接读取的来源结构，不创建报告确认事件；处方及有外部副作用的动作仍遵守既有人工确认规则。
- 合成评测数据、单次报告和缓存产物继续只写入已忽略的 `output/` 或 `var/`。
- Git Freeze 尚待其他窗口释放 `.git/index`；本轮不会覆盖其未提交改动或权限受限的旧测试快照。
