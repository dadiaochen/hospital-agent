# 🎓 Agent 项目代码审查教程

> 本教程将一步一步教你如何审查一个从0搭建的 Agent 项目

## 📖 目录

1. [如何看项目目录结构](#第一课-如何看项目目录结构)
2. [如何判断分层是否合理](#第二课-如何判断分层是否合理)
3. [如何审查数据模型设计](#第三课-如何审查数据模型设计)
4. [如何发现潜在问题](#第四课-如何发现潜在问题)
5. [如何检查医疗安全边界](#第五课-如何检查医疗安全边界)
6. [如何审查 Agent 架构](#第六课-如何审查-agent-架构)

---

## 第一课: 如何看项目目录结构

### 1.1 顶层目录审查

```
hospital/
├── backend/          # Python 后端 ✅
├── frontend/         # Next.js 前端 ✅
├── docs/            # 文档 ✅
├── scripts/         # 工具脚本 ✅
├── docker-compose.yml  ✅
├── .env.example     ✅
└── README.md        ✅
```

**审查要点：**

✅ **好的实践：**
- 前后端分离，职责清晰
- 有独立的文档目录
- 有工具脚本目录
- 提供了 Docker 编排和环境变量示例

⚠️ **需要注意：**
- 是否有 `.gitignore`？
- 是否有依赖管理文件（`requirements.txt`, `package.json`）？
- 是否有测试目录？

### 1.2 后端目录审查

```
backend/app/
├── api/          # API 路由层
├── services/     # 业务逻辑层
├── models/       # 数据模型层（ORM）
├── schemas/      # 数据传输对象（DTO）
├── tools/        # Agent 工具层
├── agent/        # Agent 工作流层
├── rag/          # 知识库检索层
├── safety/       # 安全策略层
├── core/         # 基础设施层
└── main.py       # 应用入口
```

**审查标准：**

✅ **优点：**
1. **职责清晰**：每层有明确的职责
2. **符合领域驱动设计（DDD）**
3. **Agent 特定分层**：体现了 Agent 项目的特色

---

## 第二课: 如何判断分层是否合理

### 2.1 什么是好的分层？

好的分层应该满足：
1. **单一职责**：每层只做一件事
2. **依赖方向正确**：高层依赖低层，不反向依赖
3. **易于测试**：可以独立测试每一层
4. **易于替换**：可以替换某一层的实现而不影响其他层

### 2.2 审查依赖关系

**正确的依赖方向：**

```
api → services → models
       ↓
    tools → models
       ↓
    agent → tools → models
```

**如何检查：**
1. 打开 `api/` 目录的文件，看是否直接操作数据库
2. 打开 `models/` 目录的文件，看是否包含业务逻辑
3. 打开 `services/` 目录的文件，看是否包含 HTTP 处理逻辑

### 2.3 本项目的分层问题

#### 🚨 **问题 1: services 层是空的**

```bash
$ ls backend/app/services/
__init__.py  # 只有一个空文件
```

**问题分析：**
- 项目有 `services/` 目录但没有任何实现
- 这意味着业务逻辑可能写在了其他地方（API 层或 Agent 层）
- **风险**：容易导致逻辑混乱，难以复用

**建议：**
- 将来添加业务逻辑时，应该放在 `services/` 层
- 例如：`UserService`, `MedicineBoxService`, `PrescriptionService`

#### ✅ **优点 1: 有独立的安全层**

```
backend/app/safety/
└── policies.py  # 医疗安全策略
```

这体现了对医疗安全的重视。

---

## 第三课: 如何审查数据模型设计

### 3.1 数据模型文件组织

```
backend/app/models/
├── __init__.py       # 导出所有模型 ✅
├── base.py          # 基础 Mixin ✅
├── user.py          # 用户和家庭成员 ✅
├── medication.py    # 药品相关 ✅
├── pharmacy.py      # 药店相关 ✅
├── plans.py         # 方案相关 ✅
├── knowledge.py     # 知识库 ✅
└── agent_log.py     # Agent 日志 ✅
```

**审查要点：**

✅ **好的实践：**
1. 按业务领域拆分文件
2. 有统一的 `__init__.py` 导出
3. 有基础的 Mixin 复用

### 3.2 审查基础 Mixin

**查看 `models/base.py`：**

```python
class IDMixin:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(...)
    updated_at: Mapped[datetime] = mapped_column(...)
```

✅ **优点：**
1. 使用 UUID 作为主键（分布式友好）
2. 所有表都有时间戳
3. 使用 UTC 时间（避免时区问题）

⚠️ **潜在问题：**
1. **UUID 作为字符串存储**：`String(36)` 会比 `UUID` 类型占用更多空间
2. **建议**：考虑使用 PostgreSQL 的原生 UUID 类型

### 3.3 审查核心业务模型

#### 用户模型审查

**查看 `models/user.py`：**

```python
class User(IDMixin, TimestampMixin, Base):
    __tablename__ = "users"
    
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
```

✅ **优点：**
1. 字段简洁，没有过度设计
2. 手机号有唯一索引
3. 有软删除标记（`is_active`）

⚠️ **潜在问题：**
1. **没有密码字段**：如果需要登录，缺少密码存储
2. **没有邮箱字段**：可能需要邮箱作为备用联系方式
3. **手机号可为空但有 unique 约束**：unique 约束对 NULL 的处理需要注意

#### 家庭成员模型审查

```python
class FamilyMember(IDMixin, TimestampMixin, Base):
    __tablename__ = "family_members"
    __table_args__ = (
        UniqueConstraint("user_id", "relationship", name="uq_family_member_user_relationship"),
    )
    
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    relationship: Mapped[str] = mapped_column(String(40), nullable=False)
    gender: Mapped[str | None] = mapped_column(String(20))
    birthday: Mapped[date | None] = mapped_column(Date)
```

✅ **优点：**
1. 有复合唯一约束（一个用户的同一关系只能有一个成员）
2. 外键有索引

⚠️ **潜在问题：**
1. **复合唯一约束可能不合理**：一个用户可能有多个"父亲"（生父、继父）或多个孩子
2. **relationship 是字符串**：建议使用枚举类型
3. **没有年龄计算方法**：生日存储了，但没有提供计算年龄的方法

### 3.4 审查医疗相关模型

#### 处方模型审查

```python
class Prescription(IDMixin, TimestampMixin, Base):
    __tablename__ = "prescriptions"
    
    member_id: Mapped[str] = mapped_column(ForeignKey("family_members.id"), nullable=False, index=True)
    prescription_no: Mapped[str | None] = mapped_column(String(80), unique=True, index=True)
    doctor_name: Mapped[str | None] = mapped_column(String(80))
    hospital_name: Mapped[str | None] = mapped_column(String(120))
    doctor_diagnosis_summary: Mapped[str | None] = mapped_column(Text)
    medicine_items: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    issued_at: Mapped[date | None] = mapped_column(Date)
    expires_at: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(40), default="valid", nullable=False)
    doctor_confirmation_required: Mapped[bool] = mapped_column(default=True, nullable=False)
    safety_note: Mapped[str | None] = mapped_column(Text)
```

✅ **优点：**
1. 有处方号唯一约束
2. 有过期时间
3. 有医生确认要求标记
4. 有安全备注字段

⚠️ **潜在问题：**
1. **medicine_items 使用 JSON**：查询和统计不方便
   - **建议**：考虑创建独立的 `PrescriptionItem` 表
2. **status 是字符串**：建议使用枚举
3. **缺少处方来源**：是线上问诊还是线下？

#### 药箱模型审查

```python
class MedicineBoxItem(IDMixin, TimestampMixin, Base):
    __tablename__ = "medicine_box_items"
    
    member_id: Mapped[str] = mapped_column(ForeignKey("family_members.id"), nullable=False, index=True)
    medicine_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    specification: Mapped[str | None] = mapped_column(String(120))
    total_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    remaining_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    dosage: Mapped[str] = mapped_column(String(120), nullable=False)
    frequency: Mapped[str] = mapped_column(String(120), nullable=False)
    purchased_at: Mapped[date | None] = mapped_column(Date)
    estimated_remaining_days: Mapped[int | None] = mapped_column(Integer)
```

✅ **优点：**
1. 有剩余量和总量
2. 有预估剩余天数
3. 药品名有索引

⚠️ **潜在问题：**
1. **estimated_remaining_days 是存储字段**：这是计算字段，应该动态计算而不是存储
   - **风险**：数据可能不一致
   - **建议**：改为属性方法或在查询时计算
2. **dosage 和 frequency 是字符串**：难以解析和计算
   - **建议**：结构化存储（如 JSON 或独立字段）

### 3.5 审查 Agent 日志模型

#### AgentRun 模型

```python
class AgentRun(IDMixin, TimestampMixin, Base):
    __tablename__ = "agent_runs"
    
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    member_id: Mapped[str | None] = mapped_column(ForeignKey("family_members.id"), index=True)
    user_goal: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str | None] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(40), default="created", nullable=False)
    final_answer: Mapped[str | None] = mapped_column(Text)
    need_human_confirmation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    safety_result: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    raw_state: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
```

✅ **优点：**
1. 记录了用户目标和意图
2. 有人工确认标记
3. 有安全检查结果
4. 保存了完整状态（raw_state）

⚠️ **潜在问题：**
1. **raw_state 可能很大**：如果状态包含大量上下文，会影响性能
   - **建议**：考虑压缩或存储到对象存储
2. **缺少耗时统计**：没有 `started_at`, `finished_at`, `duration_ms`
   - **建议**：添加这些字段用于性能监控

#### AgentToolCall 模型

```python
class AgentToolCall(IDMixin, TimestampMixin, Base):
    __tablename__ = "agent_tool_calls"
    
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id"), nullable=False, index=True)
    tool_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    tool_input: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    tool_output: Mapped[dict | None] = mapped_column(JSON)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
```

✅ **优点：**
1. 记录了工具调用的输入输出
2. 有延迟统计
3. 有成功失败标记
4. 有错误信息

✅ **这是一个很好的可观测性设计！**

---

## 第四课: 如何发现潜在问题

### 4.1 检查关键文件

#### 检查依赖管理文件

```bash
# 检查后端依赖
ls backend/requirements.txt

# 检查前端依赖
ls frontend/package.json
```

#### 检查配置文件

```bash
# 检查环境变量示例
cat .env.example

# 检查是否有 .gitignore
cat .gitignore
```

### 4.2 检查循环依赖

**什么是循环依赖？**

```python
# models/user.py
from app.models.medication import Prescription  # ❌ 不好

# models/medication.py
from app.models.user import FamilyMember  # ❌ 不好
```

**如何避免？**

使用 `TYPE_CHECKING`：

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user import FamilyMember
```

✅ **本项目做得很好，使用了 TYPE_CHECKING**

### 4.3 检查索引设计

**应该加索引的字段：**
1. 外键字段
2. 经常查询的字段
3. 经常排序的字段
4. 唯一字段

**本项目的索引情况：**

✅ 已加索引：
- `users.phone`
- `family_members.user_id`
- `prescriptions.member_id`
- `medicine_box_items.member_id`
- `agent_runs.user_id`, `agent_runs.member_id`, `agent_runs.intent`
- `agent_tool_calls.run_id`, `agent_tool_calls.tool_name`

⚠️ 可能需要索引：
- `prescriptions.status` (如果经常按状态筛选)
- `medicine_box_items.medicine_name` + `member_id` (复合索引)
- `agent_runs.created_at` (时间范围查询)

### 4.4 检查数据一致性

#### 问题：estimated_remaining_days 字段

```python
class MedicineBoxItem:
    remaining_quantity: Mapped[int]
    dosage: Mapped[str]
    frequency: Mapped[str]
    estimated_remaining_days: Mapped[int | None]  # ⚠️ 存储的计算字段
```

**风险：**
- 如果 `remaining_quantity` 更新了，`estimated_remaining_days` 可能不会同步更新
- 导致数据不一致

**解决方案：**

方案1: 使用 SQLAlchemy 的 `@hybrid_property`

```python
from sqlalchemy.ext.hybrid import hybrid_property

class MedicineBoxItem:
    @hybrid_property
    def estimated_remaining_days(self) -> int | None:
        if not self.remaining_quantity or not self.dosage:
            return None
        # 计算逻辑
        return self.remaining_quantity // daily_usage
```

方案2: 在更新时自动计算

```python
@validates('remaining_quantity')
def update_remaining_days(self, key, value):
    self.estimated_remaining_days = self._calculate_remaining_days(value)
    return value
```

---

## 第五课: 如何检查医疗安全边界

### 5.1 检查禁用字段

根据 `AGENTS.md` 的要求，数据库中禁止出现：
- `auto_prescribe`
- `diagnosis_by_ai`
- `ai_dosage_change`

**如何检查：**

```bash
# 搜索这些字段
grep -r "auto_prescribe" backend/app/models/
grep -r "diagnosis_by_ai" backend/app/models/
grep -r "ai_dosage_change" backend/app/models/
```

✅ **本项目通过检查，没有这些字段**

### 5.2 检查人工确认字段

关键动作必须有 `need_human_confirmation` 或 `confirmed_at` 字段：

✅ **已有人工确认字段的表：**
- `agent_runs.need_human_confirmation`
- `prescriptions.doctor_confirmation_required`

⚠️ **可能需要添加的：**
- `refill_plans` 应该有 `user_confirmed_at`
- `purchase_plans` 应该有 `user_confirmed_at`
- `consultation_drafts` 应该有 `doctor_confirmed_at`

### 5.3 检查安全备注字段

医疗相关表应该有 `safety_note` 字段：

✅ **已有的：**
- `prescriptions.safety_note`
- `medicine_box_items.safety_note`
- `health_profiles.safety_notes`

### 5.4 检查诊断相关字段

**风险字段：**
- `diagnosis` (可能暗示 AI 诊断)
- `suggested_medicine` (可能暗示 AI 开方)
- `dosage_adjustment` (可能暗示 AI 调整剂量)

✅ **本项目只有 `doctor_diagnosis_summary`，明确标注是医生诊断**

---

## 第六课: 如何审查 Agent 架构

### 6.1 审查工具注册表设计

**查看 `tools/registry.py`：**

```python
class ToolDefinition(BaseModel):
    name: str
    description: str
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    permission_scope: str
    timeout: float = 10.0
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    requires_human_confirmation: bool = False
```

✅ **优点：**
1. 使用 Pydantic 做参数验证
2. 有超时机制
3. 有重试策略
4. 有人工确认标记
5. 有权限范围

⚠️ **潜在改进：**
1. 缺少实际的工具实现
2. 缺少工具调用日志记录逻辑
3. 缺少权限校验实现

### 6.2 审查 Agent 工作流

**检查 Agent 实现：**

```bash
ls backend/app/agent/
```

目前只有占位文件，需要后续实现。

**应该实现的节点：**
1. `intent_recognition` - 意图识别
2. `load_profile` - 加载档案
3. `load_medication_context` - 加载用药上下文
4. `estimate_remaining_days` - 估算剩余天数
5. `check_prescription_validity` - 检查处方有效性
6. `generate_refill_plan` - 生成续方方案
7. `check_pharmacy_inventory` - 检查药店库存
8. `human_confirmation` - 人工确认
9. `create_tasks` - 创建任务
10. `persist_agent_run` - 持久化执行记录

### 6.3 审查安全策略

**查看 `safety/policies.py`：**

目前是占位文件，应该实现：
1. 医疗边界检查
2. 敏感操作拦截
3. 高风险场景识别
4. 人工介入判断

---

## 📊 综合评价

### ✅ 做得好的地方

1. **分层清晰**：API、Service、Model、Agent 分层明确
2. **医疗安全意识**：有专门的安全层和人工确认机制
3. **可观测性**：Agent 日志设计完善
4. **工具化**：有统一的工具注册表
5. **文档完善**：有详细的设计文档和 README

### ⚠️ 需要改进的地方

#### 高优先级

1. **services 层是空的**：业务逻辑没有地方放
2. **estimated_remaining_days 存储问题**：计算字段不应该存储
3. **缺少时间统计**：AgentRun 缺少执行时间统计
4. **relationship 字段约束问题**：复合唯一约束可能不合理

#### 中优先级

5. **JSON 字段过多**：medicine_items, dosage, frequency 等应该结构化
6. **status 字段应该用枚举**：避免拼写错误
7. **缺少依赖管理文件**：需要确认 requirements.txt 是否完整
8. **UUID 存储优化**：考虑使用原生 UUID 类型

#### 低优先级

9. **缺少复合索引**：一些高频查询可能需要复合索引
10. **User 模型字段不完整**：缺少密码、邮箱等字段

---

## 🎯 下一步建议

### 立即修复

1. **创建 services 层实现**
   ```bash
   touch backend/app/services/user_service.py
   touch backend/app/services/medicine_service.py
   touch backend/app/services/prescription_service.py
   ```

2. **修改 estimated_remaining_days 为计算属性**

3. **为 AgentRun 添加时间统计字段**

### 短期规划

1. 实现核心 API 接口
2. 实现工具调用逻辑
3. 实现安全策略
4. 实现 Agent 工作流

### 长期规划

1. 优化数据库设计（枚举、复合索引）
2. 添加缓存层
3. 添加监控和告警
4. 性能测试和优化

---

## 📚 学习资源

### 代码审查清单

- [ ] 目录结构是否清晰？
- [ ] 分层是否合理？
- [ ] 是否有循环依赖？
- [ ] 索引设计是否合理？
- [ ] 是否有数据一致性问题？
- [ ] 是否遵守医疗安全边界？
- [ ] 是否有人工确认机制？
- [ ] 是否有日志和监控？
- [ ] 是否有测试？
- [ ] 文档是否完善？

### 推荐阅读

1. **FastAPI 最佳实践**：https://fastapi.tiangolo.com/
2. **SQLAlchemy 2.0 文档**：https://docs.sqlalchemy.org/
3. **LangGraph 教程**：https://langchain-ai.github.io/langgraph/
4. **医疗软件安全标准**：FDA Guidelines

---

## 💡 总结

这是一个**设计良好**的 Agent 项目骨架，体现了以下亮点：

1. 清晰的分层架构
2. 完善的可观测性设计
3. 明确的医疗安全边界
4. 统一的工具接入层

但还需要：

1. 实现业务逻辑层
2. 修复数据一致性问题
3. 完善 Agent 工作流
4. 添加更多测试

**总体评价：7.5/10**

这是一个值得继续开发的项目！
