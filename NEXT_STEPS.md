# 🎯 下一步开发任务

## ✅ 已完成

1. **代码审查教学完成**
   - 创建了 5 份学习文档
   - 发现了 9 个问题（5 个亮点）
   - 总体评分：7.5/10

2. **修复问题 1: 创建 services 层**
   - ✅ user_service.py (37 行)
   - ✅ medicine_service.py (89 行)
   - ✅ prescription_service.py (111 行)
   - ✅ 更新 __init__.py 导出

---

## 📋 待修复问题（按优先级）

### 🔴 高优先级

#### [ ] 问题 2: 移除 estimated_remaining_days 存储字段

**当前问题：**
```python
# backend/app/models/medication.py
class MedicineBoxItem:
    estimated_remaining_days: Mapped[int | None]  # ⚠️ 不应该存储
```

**修复方案：**
1. 创建 Alembic 迁移
2. 移除该字段
3. 添加 `@hybrid_property` 动态计算
4. 使用 `MedicineService.calculate_remaining_days()`

**执行命令：**
```bash
cd backend
alembic revision -m "remove_estimated_remaining_days_from_medicine_box"
# 编辑生成的迁移文件
alembic upgrade head
```

---

#### [ ] 问题 3: 为 AgentRun 添加时间统计

**当前问题：**
```python
# backend/app/models/agent_log.py
class AgentRun:
    # 缺少：started_at, finished_at, duration_ms
```

**修复方案：**
```python
class AgentRun:
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
```

**执行命令：**
```bash
cd backend
alembic revision -m "add_timing_fields_to_agent_run"
alembic upgrade head
```

---

#### [ ] 问题 4: 修复 FamilyMember 唯一约束

**当前问题：**
```python
__table_args__ = (
    UniqueConstraint("user_id", "relationship"),  # ⚠️ 太严格
)
```

**修复方案：**
移除或改为：
```python
__table_args__ = (
    UniqueConstraint("user_id", "name", "birthday"),
)
```

---

### 🟡 中优先级

#### [ ] 问题 5: 优化 JSON 字段

考虑将 `medicine_items` 拆分为独立的 `PrescriptionItem` 表。

#### [ ] 问题 6: 使用枚举替代字符串 status

创建 `backend/app/models/enums.py`：
```python
class PlanStatus(str, Enum):
    DRAFT = "draft"
    PENDING = "pending_confirmation"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
```

#### [ ] 问题 7: 完善 User 模型

添加：`hashed_password`, `email`, `avatar_url`

---

## 🚀 新功能开发

### 1. 实现 API 接口

**文件位置：** `backend/app/api/routes/`

**待实现接口：**
- `GET /api/family-members` - 获取家庭成员列表
- `POST /api/family-members` - 添加家庭成员
- `GET /api/medicine-box` - 获取家庭药箱
- `POST /api/medicine-box` - 添加药品
- `GET /api/prescriptions` - 获取处方列表
- `GET /api/agent/runs` - 获取 Agent 执行记录

**示例代码：**
```python
# backend/app/api/routes/family.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.services import UserService
from app.schemas.family import FamilyMemberResponse

router = APIRouter()

@router.get("/family-members", response_model=list[FamilyMemberResponse])
def get_family_members(
    user_id: str,
    db: Session = Depends(get_db)
):
    service = UserService(db)
    members = service.get_family_members(user_id)
    return members
```

---

### 2. 实现 Agent 工作流

**文件位置：** `backend/app/agent/family_health_agent.py`

**待实现节点：**
1. `intent_recognition` - 意图识别
2. `load_profile` - 加载档案
3. `load_medication_context` - 加载用药上下文
4. `estimate_remaining_days` - 估算剩余天数
5. `check_prescription_validity` - 检查处方有效性
6. `generate_refill_plan` - 生成续方方案
7. `human_confirmation` - 人工确认
8. `create_tasks` - 创建任务
9. `persist_agent_run` - 持久化执行记录

---

### 3. 编写测试

**文件位置：** `backend/tests/`

**待编写测试：**
- `test_services.py` - 测试 service 层
- `test_api.py` - 测试 API 接口
- `test_agent.py` - 测试 Agent 工作流

**示例：**
```python
# backend/tests/test_services.py
def test_medicine_service_calculate_remaining_days():
    # 创建测试数据
    item = MedicineBoxItem(
        remaining_quantity=30,
        dosage="每次1片",
        frequency="每日3次"
    )
    
    service = MedicineService(db)
    days = service.calculate_remaining_days(item)
    
    assert days == 10  # 30片 / 3片每天 = 10天
```

---

## 📖 学习资源

### 代码审查文档
- `docs/README_CODE_REVIEW.md` - 从这里开始
- `docs/CODE_REVIEW_TUTORIAL.md` - 6课教程
- `docs/CODE_REVIEW_FINDINGS.md` - 问题详解
- `docs/CODE_REVIEW_PRACTICE.md` - 实战练习

### 技术文档
- `docs/TECH_DESIGN.md` - 技术设计
- `docs/DB_SCHEMA.md` - 数据库设计
- `docs/API_SPEC.md` - API 规范
- `docs/AGENT_WORKFLOW.md` - Agent 工作流

---

## 🎯 本周目标

- [x] 完成代码审查
- [x] 创建 services 层
- [ ] 修复高优先级问题 2-4
- [ ] 实现基础 API 接口
- [ ] 编写单元测试

---

## 💡 开发建议

1. **先修复问题，再开发新功能**
   - 技术债务会越积越多，尽早修复

2. **遵循 TDD（测试驱动开发）**
   - 先写测试，再写实现
   - 保证代码质量

3. **遵守 AGENTS.md 规范**
   - 不要跨阶段实现
   - 医疗安全边界
   - 工程分层规则

4. **及时更新文档**
   - 每次修改后更新相关文档
   - 保持文档与代码同步

---

**创建时间：** 2026-06-05  
**下次更新：** 完成问题 2-4 修复后
