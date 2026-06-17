# 🎯 代码审查实战练习指南

> 通过这份指南，你将学会如何独立审查代码

---

## 📚 学习路径总结

你已经完成了以下学习模块：

### ✅ 已完成的课程

1. **第一课：如何看项目目录结构** ✅
2. **第二课：如何判断分层是否合理** ✅
3. **第三课：如何审查数据模型设计** ✅
4. **第四课：如何发现潜在问题** ✅
5. **第五课：如何检查医疗安全边界** ✅
6. **第六课：如何审查 Agent 架构** ✅

---

## 🎓 核心学习成果

### 1. 发现的主要问题

#### 🔴 严重问题（4个）
1. **services 层是空的** - 业务逻辑无处安放
2. **estimated_remaining_days 存储问题** - 计算字段不应该存储
3. **AgentRun 缺少时间统计** - 无法监控性能
4. **FamilyMember 约束不合理** - 一个用户只能有一个父亲/母亲

#### 🟡 中等问题（3个）
5. **JSON 字段过多** - 查询和统计不便
6. **status 应该用枚举** - 字符串容易拼写错误
7. **User 模型字段不完整** - 缺少密码、邮箱等

#### 🟢 优化建议（2个）
8. **UUID 存储优化** - 使用原生 UUID 类型
9. **缺少复合索引** - 影响查询性能

### 2. 发现的亮点

1. ✅ **HumanConfirmationMixin 设计优秀** - 所有关键操作都需要确认
2. ✅ **医疗安全策略清晰** - 有明确的高风险关键词
3. ✅ **AgentToolCall 可观测性完善** - 完整的工具调用链路
4. ✅ **避免循环依赖** - 使用 TYPE_CHECKING
5. ✅ **统一的 Mixin 设计** - 代码复用性好

---

## 🔧 实战练习：自己动手修复问题

### 练习 1: 创建 services 层 ⭐⭐⭐⭐⭐

**目标：** 创建一个完整的 service 类

**步骤：**

1. 创建文件 `backend/app/services/medicine_service.py`

```python
from datetime import date
from sqlalchemy.orm import Session
from app.models import MedicineBoxItem, FamilyMember


class MedicineService:
    """药箱管理服务"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_medicine_box(self, member_id: str) -> list[MedicineBoxItem]:
        """获取家庭成员的药箱"""
        return (
            self.db.query(MedicineBoxItem)
            .filter(MedicineBoxItem.member_id == member_id)
            .all()
        )
    
    def calculate_remaining_days(self, item: MedicineBoxItem) -> int | None:
        """计算剩余天数（动态计算，不存储）"""
        if not item.remaining_quantity or not item.dosage:
            return None
        
        # TODO: 实现真实的解析逻辑
        # 这里简化处理：假设每天用1个单位
        daily_usage = self._parse_daily_usage(item.dosage, item.frequency)
        if daily_usage <= 0:
            return None
        
        return item.remaining_quantity // daily_usage
    
    def _parse_daily_usage(self, dosage: str, frequency: str) -> int:
        """解析每日用量"""
        # 示例实现
        # "每次1片" + "每日3次" -> 3
        # 实际项目需要更复杂的解析逻辑
        if "每日" in frequency:
            # 提取数字
            import re
            match = re.search(r'(\d+)次', frequency)
            if match:
                return int(match.group(1))
        return 1
    
    def check_low_stock(self, member_id: str, threshold_days: int = 7) -> list[dict]:
        """检查低库存药品"""
        items = self.get_medicine_box(member_id)
        low_stock_items = []
        
        for item in items:
            remaining_days = self.calculate_remaining_days(item)
            if remaining_days and remaining_days <= threshold_days:
                low_stock_items.append({
                    "medicine_name": item.medicine_name,
                    "remaining_quantity": item.remaining_quantity,
                    "remaining_days": remaining_days,
                    "item_id": item.id,
                })
        
        return low_stock_items
```

**练习任务：**
- [ ] 创建这个文件
- [ ] 添加更多方法：`add_medicine`, `update_quantity`, `remove_medicine`
- [ ] 为每个方法编写测试用例

---

### 练习 2: 修复 estimated_remaining_days 问题 ⭐⭐⭐⭐

**目标：** 将存储字段改为计算属性

**步骤：**

1. 修改 `backend/app/models/medication.py`

```python
from sqlalchemy.ext.hybrid import hybrid_property

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
    safety_note: Mapped[str | None] = mapped_column(Text)
    
    # 移除 estimated_remaining_days 字段
    
    member: Mapped["FamilyMember"] = relationship(back_populates="medicine_box_items")
    medication_reminders: Mapped[list["MedicationReminder"]] = relationship(back_populates="medicine_box_item")
    
    @hybrid_property
    def estimated_remaining_days(self) -> int | None:
        """动态计算剩余天数"""
        if not self.remaining_quantity or not self.dosage:
            return None
        
        # 调用 MedicineService 的计算逻辑
        # 或者直接在这里实现
        daily_usage = self._parse_daily_usage()
        if daily_usage <= 0:
            return None
        
        return self.remaining_quantity // daily_usage
    
    def _parse_daily_usage(self) -> int:
        """解析每日用量"""
        # 实现解析逻辑
        import re
        if "每日" in self.frequency:
            match = re.search(r'(\d+)次', self.frequency)
            if match:
                return int(match.group(1))
        return 1
```

2. 创建 Alembic 迁移

```bash
cd backend
alembic revision -m "remove_estimated_remaining_days_column"
```

3. 编辑生成的迁移文件

```python
def upgrade():
    op.drop_column('medicine_box_items', 'estimated_remaining_days')

def downgrade():
    op.add_column('medicine_box_items', sa.Column('estimated_remaining_days', sa.Integer()))
```

**练习任务：**
- [ ] 实现这个修改
- [ ] 运行迁移：`alembic upgrade head`
- [ ] 测试计算属性是否工作
- [ ] 更新所有引用该字段的代码

---

### 练习 3: 为 AgentRun 添加时间统计 ⭐⭐⭐⭐

**目标：** 添加执行时间监控字段

**步骤：**

1. 修改 `backend/app/models/agent_log.py`

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
    
    # 新增字段
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    
    user: Mapped["User"] = relationship(back_populates="agent_runs")
    member: Mapped["FamilyMember | None"] = relationship(back_populates="agent_runs")
    tool_calls: Mapped[list["AgentToolCall"]] = relationship(back_populates="run")
    
    @property
    def is_running(self) -> bool:
        """是否正在运行"""
        return self.started_at is not None and self.finished_at is None
    
    @property
    def is_finished(self) -> bool:
        """是否已完成"""
        return self.finished_at is not None
    
    def mark_started(self):
        """标记开始执行"""
        self.started_at = datetime.now(timezone.utc)
        self.status = "running"
    
    def mark_finished(self, status: str = "completed"):
        """标记完成执行"""
        self.finished_at = datetime.now(timezone.utc)
        self.status = status
        if self.started_at:
            delta = self.finished_at - self.started_at
            self.duration_ms = int(delta.total_seconds() * 1000)
```

2. 创建 Alembic 迁移

```bash
alembic revision -m "add_timing_to_agent_run"
```

3. 编辑迁移文件

```python
def upgrade():
    op.add_column('agent_runs', sa.Column('started_at', sa.DateTime(timezone=True)))
    op.add_column('agent_runs', sa.Column('finished_at', sa.DateTime(timezone=True)))
    op.add_column('agent_runs', sa.Column('duration_ms', sa.Integer()))

def downgrade():
    op.drop_column('agent_runs', 'duration_ms')
    op.drop_column('agent_runs', 'finished_at')
    op.drop_column('agent_runs', 'started_at')
```

**练习任务：**
- [ ] 实现这个修改
- [ ] 运行迁移
- [ ] 在 Agent 工作流中调用 `mark_started()` 和 `mark_finished()`
- [ ] 编写性能监控查询

---

### 练习 4: 修复 FamilyMember 的唯一约束 ⭐⭐⭐

**目标：** 允许一个用户有多个相同关系的家庭成员

**步骤：**

1. 修改 `backend/app/models/user.py`

```python
class FamilyMember(IDMixin, TimestampMixin, Base):
    __tablename__ = "family_members"
    
    # 移除原来的约束，使用更合理的约束
    __table_args__ = (
        # 同一用户不能有两个相同姓名和生日的成员
        UniqueConstraint("user_id", "name", "birthday", name="uq_family_member_identity"),
    )
    
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    relationship: Mapped[str] = mapped_column(String(40), nullable=False)
    gender: Mapped[str | None] = mapped_column(String(20))
    birthday: Mapped[date | None] = mapped_column(Date)
    default_address: Mapped[str | None] = mapped_column(String(255))
    
    # ... 其他字段
```

2. 或者完全移除约束

```python
class FamilyMember(IDMixin, TimestampMixin, Base):
    __tablename__ = "family_members"
    # 不设置 __table_args__
```

**练习任务：**
- [ ] 决定使用哪种方案
- [ ] 创建迁移文件
- [ ] 测试可以添加多个"父亲"或"儿子"
- [ ] 更新 seed 脚本

---

### 练习 5: 使用枚举替代字符串 status ⭐⭐⭐

**目标：** 提高类型安全性

**步骤：**

1. 创建 `backend/app/models/enums.py`

```python
from enum import Enum as PyEnum


class PlanStatus(str, PyEnum):
    """方案状态"""
    DRAFT = "draft"
    PENDING_CONFIRMATION = "pending_confirmation"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    EXPIRED = "expired"


class PrescriptionStatus(str, PyEnum):
    """处方状态"""
    VALID = "valid"
    EXPIRED = "expired"
    USED = "used"
    CANCELLED = "cancelled"


class AgentRunStatus(str, PyEnum):
    """Agent 运行状态"""
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
```

2. 在模型中使用

```python
from sqlalchemy import Enum
from app.models.enums import PlanStatus

class RefillPlan(HumanConfirmationMixin, IDMixin, TimestampMixin, Base):
    status: Mapped[str] = mapped_column(
        Enum(PlanStatus, native_enum=False, length=40),
        default=PlanStatus.DRAFT.value,
        nullable=False
    )
```

**练习任务：**
- [ ] 创建枚举文件
- [ ] 更新所有使用 status 的模型
- [ ] 创建迁移（类型不变，只是约束更严格）
- [ ] 在代码中使用枚举而不是字符串

---

## 🎯 进阶练习：独立审查新代码

### 练习 6: 审查 seed.py 脚本 ⭐⭐⭐⭐

**任务：** 阅读 `scripts/seed.py`，找出至少 3 个可以改进的地方

**提示：**
1. 函数是否太长？
2. 是否有重复代码？
3. 错误处理是否完善？
4. 是否容易扩展？

**你的答案：**
```
1. 问题：_____________
   建议：_____________

2. 问题：_____________
   建议：_____________

3. 问题：_____________
   建议：_____________
```

---

### 练习 7: 审查前端代码 ⭐⭐⭐

**任务：** 查看前端代码，评估以下方面：

1. **文件组织**
   - [ ] 路由结构是否清晰？
   - [ ] 组件是否有合理的拆分？
   - [ ] 是否有共享的工具函数？

2. **类型安全**
   - [ ] 是否使用了 TypeScript？
   - [ ] 是否有类型定义？
   - [ ] API 响应是否有类型？

3. **状态管理**
   - [ ] 如何管理全局状态？
   - [ ] 如何管理 API 数据？
   - [ ] 是否有加载和错误状态？

**你的发现：**
```
优点：
1. _____________
2. _____________

问题：
1. _____________
2. _____________

建议：
1. _____________
2. _____________
```

---

### 练习 8: 审查 docker-compose.yml ⭐⭐⭐

**任务：** 审查 Docker 配置，检查：

1. **安全性**
   - [ ] 密码是否硬编码？
   - [ ] 是否使用了默认密码？
   - [ ] 数据卷是否持久化？

2. **可用性**
   - [ ] 服务依赖关系是否正确？
   - [ ] 健康检查是否合理？
   - [ ] 端口映射是否冲突？

3. **性能**
   - [ ] 资源限制是否设置？
   - [ ] 网络配置是否优化？

**你的发现：**
```
问题 1: _____________
严重程度: □ 高 □ 中 □ 低
建议: _____________

问题 2: _____________
严重程度: □ 高 □ 中 □ 低
建议: _____________
```

---

## 📝 代码审查检查清单

每次审查代码时，使用这个清单：

### 架构层面
- [ ] 目录结构是否清晰？
- [ ] 分层是否合理？
- [ ] 是否有循环依赖？
- [ ] 依赖方向是否正确？

### 数据模型层面
- [ ] 字段类型是否合适？
- [ ] 索引设计是否合理？
- [ ] 约束是否正确？
- [ ] 是否有数据一致性风险？
- [ ] 关系定义是否正确？

### 业务逻辑层面
- [ ] 是否有业务逻辑泄漏到错误的层？
- [ ] 是否有重复代码？
- [ ] 错误处理是否完善？
- [ ] 边界情况是否处理？

### 安全层面
- [ ] 是否有医疗安全风险？
- [ ] 是否有人工确认机制？
- [ ] 是否有敏感数据泄漏？
- [ ] 是否有 SQL 注入风险？

### 性能层面
- [ ] 是否有 N+1 查询问题？
- [ ] 是否缺少必要的索引？
- [ ] 是否有不必要的计算？
- [ ] 是否有缓存机制？

### 可维护性层面
- [ ] 代码是否易读？
- [ ] 是否有注释？
- [ ] 是否有文档？
- [ ] 是否有测试？

---

## 🚀 下一步学习建议

### 1. 学习相关技术
- [ ] SQLAlchemy 2.0 进阶特性
- [ ] FastAPI 依赖注入系统
- [ ] LangGraph 工作流设计
- [ ] PostgreSQL 查询优化

### 2. 实践更多项目
- [ ] 尝试从零搭建一个类似项目
- [ ] 参与开源项目的代码审查
- [ ] 阅读优秀项目的源码

### 3. 深入某个领域
- [ ] 数据库设计最佳实践
- [ ] Agent 系统架构设计
- [ ] 医疗软件安全标准
- [ ] 分布式系统设计

---

## 💡 总结

通过这次代码审查，你学会了：

1. ✅ **结构化审查方法**：从目录到模型，从分层到安全
2. ✅ **发现问题的技巧**：看依赖、看约束、看计算、看索引
3. ✅ **评估严重程度**：区分严重问题、中等问题和优化建议
4. ✅ **提出解决方案**：不仅指出问题，还提供具体的修复方案
5. ✅ **医疗安全意识**：理解医疗软件的特殊要求

**最重要的是：** 代码审查不是为了挑刺，而是为了让代码更好、让团队成长！

---

**继续加油！🎉**
