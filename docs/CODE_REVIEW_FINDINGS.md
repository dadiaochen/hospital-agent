# 🔍 代码审查发现报告

> 日期：2026-06-05
> 审查对象：家庭健康管理 Agent 系统
> 审查阶段：第二阶段 2A（数据库层）

---

## 📊 总体评分：7.5/10

**总体评价：** 这是一个**设计良好、有医疗安全意识**的 Agent 项目骨架。

---

## ✅ 亮点（做得特别好的地方）

### 1. 🎯 HumanConfirmationMixin 设计优秀

**位置：** `backend/app/models/plans.py:16-21`

```python
class HumanConfirmationMixin:
    status: Mapped[str] = mapped_column(String(40), default="draft", nullable=False)
    need_human_confirmation: Mapped[bool] = mapped_column(default=True, nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmation_note: Mapped[str | None] = mapped_column(Text)
```

**为什么好：**
- ✅ 所有关键操作（续方、购药、提醒）都继承这个 Mixin
- ✅ 有状态字段、确认标记、确认时间、确认备注
- ✅ 体现了医疗安全意识，防止 Agent 自动执行危险操作

**应用场景：**
- `RefillPlan` - 续方方案需要确认
- `ConsultationDraft` - 复诊申请需要确认
- `PurchasePlan` - 购药方案需要确认
- `MedicationReminder` - 用药提醒需要确认
- `FollowUpTask` - 随访任务需要确认

---

### 2. 🛡️ 医疗安全策略清晰

**位置：** `backend/app/safety/policies.py`

```python
HIGH_RISK_MEDICATION_PATTERNS = [
    "加量", "减量", "停药", "换药", "替代", "能不能多吃",
]

def needs_medical_safety_interception(message: str) -> bool:
    return any(pattern in message for pattern in HIGH_RISK_MEDICATION_PATTERNS)
```

**为什么好：**
- ✅ 明确定义了高风险关键词
- ✅ 提供了安全拦截函数
- ✅ 符合 AGENTS.md 中的医疗安全边界要求

---

### 3. 📝 AgentToolCall 可观测性设计完善

**位置：** `backend/app/models/agent_log.py:44-56`

```python
class AgentToolCall(IDMixin, TimestampMixin, Base):
    run_id: Mapped[str]
    tool_name: Mapped[str]
    tool_input: Mapped[dict]
    tool_output: Mapped[dict | None]
    latency_ms: Mapped[int | None]
    success: Mapped[bool]
    error_message: Mapped[str | None]
```

**为什么好：**
- ✅ 记录了完整的工具调用链路
- ✅ 有性能监控（latency_ms）
- ✅ 有成功失败标记
- ✅ 便于审计和回溯

---

### 4. 🏗️ 使用 TYPE_CHECKING 避免循环依赖

**位置：** 所有 models 文件

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user import FamilyMember
```

**为什么好：**
- ✅ 避免了循环导入问题
- ✅ 保持了类型提示
- ✅ 不影响运行时性能

---

### 5. 🔧 统一的 Mixin 设计

**位置：** `backend/app/models/base.py`

```python
class IDMixin:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)

class TimestampMixin:
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
```

**为什么好：**
- ✅ 所有表都有统一的 ID 和时间戳
- ✅ 使用 UUID（分布式友好）
- ✅ 使用 UTC 时间（避免时区问题）

---

## ⚠️ 问题（需要改进的地方）

### 🔴 高优先级问题

#### 问题 1: services 层完全是空的

**位置：** `backend/app/services/__init__.py`

```bash
$ ls backend/app/services/
__init__.py  # 只有一个空文件
```

**问题分析：**
- ❌ 业务逻辑没有地方放
- ❌ 未来可能把逻辑写在 API 层或 Agent 层，导致代码混乱
- ❌ 难以复用和测试

**影响：** ⭐⭐⭐⭐⭐ (严重)

**建议修复：**
```python
# backend/app/services/user_service.py
class UserService:
    def __init__(self, db: Session):
        self.db = db
    
    def get_family_members(self, user_id: str) -> list[FamilyMember]:
        return self.db.query(FamilyMember).filter_by(user_id=user_id).all()

# backend/app/services/medicine_service.py
class MedicineService:
    def __init__(self, db: Session):
        self.db = db
    
    def estimate_remaining_days(self, item_id: str) -> int | None:
        item = self.db.query(MedicineBoxItem).get(item_id)
        # 计算逻辑
        return days
```

---

#### 问题 2: estimated_remaining_days 不应该存储

**位置：** `backend/app/models/medication.py:27`

```python
class MedicineBoxItem:
    remaining_quantity: Mapped[int]
    dosage: Mapped[str]
    frequency: Mapped[str]
    estimated_remaining_days: Mapped[int | None]  # ⚠️ 这是计算字段
```

**问题分析：**
- ❌ `estimated_remaining_days` 是根据 `remaining_quantity` 计算出来的
- ❌ 如果 `remaining_quantity` 更新了，`estimated_remaining_days` 可能不会同步
- ❌ 导致数据不一致

**影响：** ⭐⭐⭐⭐ (重要)

**建议修复：**

方案 1: 使用 `@hybrid_property`（推荐）

```python
from sqlalchemy.ext.hybrid import hybrid_property

class MedicineBoxItem:
    # 移除 estimated_remaining_days 字段
    
    @hybrid_property
    def estimated_remaining_days(self) -> int | None:
        """动态计算剩余天数"""
        if not self.remaining_quantity or not self.dosage:
            return None
        
        # 解析 dosage 和 frequency，计算每日用量
        daily_usage = self._parse_daily_usage()
        if daily_usage <= 0:
            return None
        
        return self.remaining_quantity // daily_usage
    
    def _parse_daily_usage(self) -> int:
        """解析用法用量，计算每日用量"""
        # 示例：dosage="1片", frequency="每日3次" -> 3
        # 需要实现解析逻辑
        pass
```

方案 2: 在更新时自动计算

```python
from sqlalchemy import event

@event.listens_for(MedicineBoxItem, 'before_update')
@event.listens_for(MedicineBoxItem, 'before_insert')
def update_estimated_days(mapper, connection, target):
    """自动更新预估剩余天数"""
    target.estimated_remaining_days = target._calculate_remaining_days()
```

**迁移步骤：**
1. 创建新的 Alembic 迁移
2. 移除 `estimated_remaining_days` 列
3. 添加计算方法
4. 更新所有引用该字段的代码

---

#### 问题 3: AgentRun 缺少执行时间统计

**位置：** `backend/app/models/agent_log.py:26-41`

```python
class AgentRun:
    # 只有 created_at 和 updated_at
    # 缺少：started_at, finished_at, duration_ms
```

**问题分析：**
- ❌ 无法统计 Agent 执行耗时
- ❌ 无法分析性能瓶颈
- ❌ 无法监控超时

**影响：** ⭐⭐⭐⭐ (重要)

**建议修复：**

```python
class AgentRun(IDMixin, TimestampMixin, Base):
    __tablename__ = "agent_runs"
    
    # ... 现有字段 ...
    
    # 新增字段
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    
    @property
    def is_running(self) -> bool:
        return self.started_at is not None and self.finished_at is None
    
    @property
    def is_finished(self) -> bool:
        return self.finished_at is not None
```

**Alembic 迁移：**
```python
# alembic/versions/xxxx_add_timing_to_agent_run.py
def upgrade():
    op.add_column('agent_runs', sa.Column('started_at', sa.DateTime(timezone=True)))
    op.add_column('agent_runs', sa.Column('finished_at', sa.DateTime(timezone=True)))
    op.add_column('agent_runs', sa.Column('duration_ms', sa.Integer()))
```

---

#### 问题 4: FamilyMember 的复合唯一约束不合理

**位置：** `backend/app/models/user.py:30`

```python
class FamilyMember:
    __table_args__ = (
        UniqueConstraint("user_id", "relationship", name="uq_family_member_user_relationship"),
    )
```

**问题分析：**
- ❌ 一个用户只能有一个"父亲"、一个"母亲"
- ❌ 但现实中可能有：生父、继父、养父
- ❌ 也可能有多个孩子，但约束限制为只能有一个"儿子"

**影响：** ⭐⭐⭐⭐ (重要)

**建议修复：**

方案 1: 移除这个约束（推荐）

```python
class FamilyMember:
    # 移除 __table_args__
    
    # 添加更合理的约束
    __table_args__ = (
        UniqueConstraint("user_id", "name", "birthday", name="uq_family_member_identity"),
    )
```

方案 2: 改用更细粒度的关系

```python
# 定义关系枚举
class RelationType(str, Enum):
    SELF = "self"
    FATHER_BIOLOGICAL = "father_biological"
    FATHER_STEP = "father_step"
    MOTHER_BIOLOGICAL = "mother_biological"
    MOTHER_STEP = "mother_step"
    SON_ELDEST = "son_eldest"
    SON_SECOND = "son_second"
    # ...
```

---

### 🟡 中优先级问题

#### 问题 5: JSON 字段过多，查询不便

**位置：** 多处

```python
# medication.py
medicine_items: Mapped[list[dict]] = mapped_column(JSON)

# medication.py
dosage: Mapped[str]  # 应该结构化
frequency: Mapped[str]  # 应该结构化

# plans.py
plan_detail: Mapped[dict] = mapped_column(JSON)
schedule: Mapped[dict] = mapped_column(JSON)
```

**问题分析：**
- ⚠️ JSON 字段无法建立索引
- ⚠️ 无法用 SQL 查询和统计
- ⚠️ 数据验证困难

**影响：** ⭐⭐⭐ (中等)

**建议：**
- 对于频繁查询的字段，考虑创建独立表
- 例如：`PrescriptionItem` 表存储处方明细
- 保留 JSON 用于非结构化或很少查询的数据

---

#### 问题 6: status 字段应该用枚举

**位置：** 多处

```python
status: Mapped[str] = mapped_column(String(40), default="draft", nullable=False)
```

**问题分析：**
- ⚠️ 字符串容易拼写错误
- ⚠️ 没有类型提示
- ⚠️ 数据库可能存储无效值

**影响：** ⭐⭐⭐ (中等)

**建议修复：**

```python
from enum import Enum as PyEnum
from sqlalchemy import Enum

class PlanStatus(str, PyEnum):
    DRAFT = "draft"
    PENDING_CONFIRMATION = "pending_confirmation"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    EXPIRED = "expired"

class RefillPlan:
    status: Mapped[str] = mapped_column(
        Enum(PlanStatus, native_enum=False),
        default=PlanStatus.DRAFT.value,
        nullable=False
    )
```

---

#### 问题 7: User 模型字段不完整

**位置：** `backend/app/models/user.py:16-22`

```python
class User:
    name: Mapped[str]
    phone: Mapped[str | None]
    is_active: Mapped[bool]
    # 缺少：密码、邮箱、头像等
```

**问题分析：**
- ⚠️ 如果需要用户登录，缺少密码字段
- ⚠️ 缺少邮箱作为备用联系方式
- ⚠️ 缺少用户头像

**影响：** ⭐⭐⭐ (中等)

**建议：**
```python
class User:
    name: Mapped[str]
    phone: Mapped[str | None]
    email: Mapped[str | None] = mapped_column(String(120), unique=True, index=True)
    hashed_password: Mapped[str | None] = mapped_column(String(128))
    avatar_url: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool]
```

---

### 🟢 低优先级问题

#### 问题 8: UUID 存储优化

**位置：** `backend/app/models/base.py:17`

```python
id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
```

**问题分析：**
- 💡 `String(36)` 占用空间较大
- 💡 PostgreSQL 有原生 UUID 类型

**影响：** ⭐⭐ (较低)

**建议：**
```python
from sqlalchemy.dialects.postgresql import UUID
import uuid

id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
```

---

#### 问题 9: 缺少复合索引

**位置：** 多处

**问题分析：**
- 💡 高频查询可能需要复合索引
- 例如：`(member_id, medicine_name)`, `(user_id, created_at)`

**影响：** ⭐⭐ (较低)

**建议：**
```python
class MedicineBoxItem:
    __table_args__ = (
        Index('ix_medicine_box_member_medicine', 'member_id', 'medicine_name'),
    )
```

---

## 📈 技术债务清单

### 立即修复（本周）

- [ ] **问题 1**: 创建 services 层实现
- [ ] **问题 3**: 为 AgentRun 添加时间统计字段

### 短期修复（1-2 周）

- [ ] **问题 2**: 将 estimated_remaining_days 改为计算属性
- [ ] **问题 4**: 修改 FamilyMember 的唯一约束

### 中期优化（1 个月）

- [ ] **问题 5**: 优化 JSON 字段，创建独立表
- [ ] **问题 6**: 使用枚举替代字符串 status
- [ ] **问题 7**: 完善 User 模型字段

### 长期优化（2-3 个月）

- [ ] **问题 8**: UUID 类型优化
- [ ] **问题 9**: 添加复合索引
- [ ] 性能测试和优化
- [ ] 添加缓存层

---

## 🎓 学到的审查技巧

### 1. 如何发现数据一致性问题

**方法：** 看字段之间的依赖关系

```python
# 🚩 红旗：计算字段被存储
total_quantity: Mapped[int]
remaining_quantity: Mapped[int]
estimated_remaining_days: Mapped[int]  # ⚠️ 这个可以从前两个算出来
```

### 2. 如何发现约束设计问题

**方法：** 用现实场景验证约束

```python
# 🚩 红旗：约束太严格
UniqueConstraint("user_id", "relationship")
# 思考：一个用户能有两个"父亲"吗？答案是可以的（生父、继父）
```

### 3. 如何发现性能问题

**方法：** 看哪些字段会被频繁查询

```python
# 🚩 红旗：没有索引的高频查询字段
medicine_name: Mapped[str]  # 如果经常按药品名查询，需要加索引
```

### 4. 如何发现可观测性缺失

**方法：** 看是否有足够的日志和监控字段

```python
# ✅ 好的可观测性设计
latency_ms: Mapped[int]
success: Mapped[bool]
error_message: Mapped[str]
```

---

## 🎯 下一步行动计划

### 第一步：修复高优先级问题（今天）

```bash
# 1. 创建 services 层
touch backend/app/services/user_service.py
touch backend/app/services/medicine_service.py
touch backend/app/services/prescription_service.py
touch backend/app/services/agent_service.py

# 2. 创建 Alembic 迁移
alembic revision -m "add_timing_to_agent_run"
```

### 第二步：实现核心 API（明天）

```bash
# 实现基础 CRUD API
- GET /api/family-members
- POST /api/family-members
- GET /api/medicine-box
- POST /api/medicine-box
```

### 第三步：实现工具层（后天）

```bash
# 实现工具函数
- get_family_members
- get_medicine_box
- estimate_remaining_days
- check_prescription_validity
```

---

## 💡 总结

### 优点（保持）

1. ✅ 医疗安全意识强
2. ✅ 分层清晰
3. ✅ 可观测性设计好
4. ✅ 使用了 Mixin 复用代码
5. ✅ 避免了循环依赖

### 缺点（改进）

1. ❌ services 层是空的
2. ❌ 有数据一致性风险
3. ❌ 缺少执行时间统计
4. ❌ 约束设计不够灵活
5. ❌ JSON 字段过多

### 建议

这是一个**很好的起点**，但需要在实现业务逻辑前修复这些问题，否则会积累技术债务。

**优先级排序：**
1. 先创建 services 层（否则逻辑没地方放）
2. 再修复数据模型问题（否则以后迁移更麻烦）
3. 最后实现 Agent 工作流（基础打好了再建高楼）

---

## 📚 参考资料

- [SQLAlchemy 2.0 文档](https://docs.sqlalchemy.org/)
- [FastAPI 最佳实践](https://fastapi.tiangolo.com/)
- [数据库设计最佳实践](https://www.postgresql.org/docs/current/)
- [医疗软件安全标准](https://www.fda.gov/)

---

**审查人：** Kiro (Claude Opus 4.8)  
**审查时间：** 2026-06-05  
**下次审查：** 完成 services 层后
