# 报告详情数据契约 v1

状态：`FROZEN`（2026-08-03）

本契约是 UX-06 的前置依赖，定义报告列表和报告详情的只读 HTTP 数据形状。它不新增上传、解析、诊断、治疗、处方或外部提交能力；报告解析失败或没有可解释指标时，客户端必须展示对应状态，不得补造医疗事实。

## 1. 接口范围

### 1.1 报告列表

```text
GET /api/family-members/{member_id}/reports
```

响应：`ReportListResponse`

```json
{
  "items": [
    {
      "id": "report-mother-001",
      "member_id": "member-mother",
      "title": "年度检查报告",
      "document_type": "checkup_report",
      "status": "ready",
      "reported_at": "2026-07-20T08:00:00Z",
      "updated_at": "2026-07-20T08:05:00Z",
      "document_version": "1.0",
      "source_name": "年度检查报告",
      "metric_count": 3
    }
  ]
}
```

### 1.2 报告详情

```text
GET /api/family-members/{member_id}/reports/{report_id}
```

响应：`ReportDetailResponse`

```json
{
  "report": {
    "id": "report-mother-001",
    "member_id": "member-mother",
    "title": "年度检查报告",
    "document_type": "checkup_report",
    "status": "ready",
    "reported_at": "2026-07-20T08:00:00Z",
    "updated_at": "2026-07-20T08:05:00Z",
    "document_version": "1.0",
    "source_name": "年度检查报告",
    "metric_count": 3
  },
  "summary": {
    "text": "报告中的可读项目已整理，建议结合原始报告和专业人员意见理解。",
    "disclaimer": "这是信息整理和通俗解释，不是诊断或治疗建议。"
  },
  "metrics": [
    {
      "id": "metric-001",
      "name": "空腹血糖",
      "value": "5.6",
      "unit": "mmol/L",
      "reference_range": {
        "low": 3.9,
        "high": 6.1,
        "display_text": "3.9–6.1 mmol/L"
      },
      "interpretation_status": "within_range",
      "trend": "unknown",
      "measured_at": "2026-07-20T08:00:00Z",
      "explanation": "该项目的结果与本报告提供的参考范围相符。",
      "source_ref": "source-report-mother-001"
    }
  ],
  "sections": [
    {
      "id": "section-001",
      "title": "检查说明",
      "content": "原始报告中的检查说明或备注。",
      "source_ref": "source-report-mother-001"
    }
  ],
  "sources": [
    {
      "id": "source-report-mother-001",
      "source_type": "medical_report",
      "display_name": "年度检查报告",
      "document_version": "1.0",
      "page_number": 1,
      "excerpt": "空腹血糖 5.6 mmol/L",
      "verified": true
    }
  ],
  "safety": {
    "requires_professional_review": false,
    "notice": "如有明显不适、结果异常或对报告有疑问，请咨询医生或药师。"
  }
}
```

## 2. 字段约束

### ReportSummary

| 字段 | 类型 | 约束 |
|---|---|---|
| `id` | `string` | 报告内部标识；页面不直接展示 |
| `member_id` | `string` | 必须属于当前用户 |
| `title` | `string` | 用户可读报告名称 |
| `document_type` | `string` | 报告类型，不作为诊断结论 |
| `status` | enum | `uploaded` / `processing` / `ready` / `needs_review` / `failed` |
| `reported_at` | ISO datetime/null | 报告记录时间 |
| `updated_at` | ISO datetime | 详情更新时间 |
| `document_version` | `string` | 来源版本，变更后不得复用旧详情 |
| `source_name` | `string` | 用户可读来源名称 |
| `metric_count` | `integer` | 当前详情中可展示指标数量 |

### ReportMetric

| 字段 | 类型 | 约束 |
|---|---|---|
| `value` | `string` / `number` / `null` | 不假设所有指标都是数值 |
| `reference_range` | object/null | 包含 `low`、`high`、`display_text`；没有范围时为 `null` |
| `interpretation_status` | enum | `within_range` / `above_range` / `below_range` / `not_available` |
| `trend` | enum | `up` / `down` / `stable` / `unknown`；无历史数据必须为 `unknown` |
| `explanation` | `string` | 通俗解释，不得生成诊断或治疗建议 |
| `source_ref` | `string` | 必须能在 `sources` 中找到，页面展示来源名称而非原始 ID |

### SourceReference

`id` 仅用于前后端关联，`display_name`、`page_number`、`excerpt` 和 `verified` 用于用户可读的来源提示。未验证来源不得标记为已核实，也不得支持确定性医疗结论。

## 3. 客户端行为

- `uploaded`、`processing`：展示处理中状态，不展示指标解释。
- `needs_review`：展示“需要人工核对”，只展示已标注的原文信息。
- `failed`：展示失败原因的用户可读摘要，不把 Provider、Tool 或内部错误名展示给用户。
- `ready` 且 `metrics=[]`：展示“报告已读取，但暂时没有可解释指标”，不得用模型补齐指标。
- `safety.requires_professional_review=true`：固定展示专业人员复核提示，不提供诊断、处方或调整用药动作。
- 切换 `member_id` 时必须取消旧请求、清空旧详情，并再次校验列表和详情响应的成员归属。

## 4. 版本和兼容

- 契约版本：`report-detail.v1`。
- 新增字段必须保持可选；修改字段语义或枚举值时升级主版本。
- `extracted_content`、`object_uri`、Provider 原始响应和完整医疗正文不直接作为 HTTP DTO 暴露。
- UX-06 页面只消费本契约；上传、解析任务、确认写入和健康档案事件属于后续接口，不在本契约内。
- 实现状态：UX-06 已按本契约接入报告列表、报告详情 API 和 `/reports/[reportId]` 页面；契约本身仍保持冻结，后续语义变更必须升级版本。
- 验证状态：前端 34 个测试和后端报告读取接口 6 个测试通过；下一步进入路线图中的 UX-08，不在本阶段扩展报告写入能力。

## UX-08 入口关系

UX-08 不修改 `report-detail.v1`。报告解读继续通过 `/reports` 和 `/reports/[reportId]` 作为用户入口；旧的内部页面通过兼容跳转收回到 `/agent` 或 `/family`，不会把报告详情契约、来源 ID 或解析实现暴露到首页。
