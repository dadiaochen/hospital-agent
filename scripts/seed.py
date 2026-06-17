from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys
from typing import Any, TypeVar

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.database import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    AgentRun,
    AgentToolCall,
    ConsultationDraft,
    FamilyMember,
    HealthProfile,
    KnowledgeChunk,
    KnowledgeDocument,
    MedicineBoxItem,
    Pharmacy,
    PharmacyInventory,
    Prescription,
    PurchaseRecord,
    RefillPlan,
    User,
)

ModelT = TypeVar("ModelT")


def one_or_create(session: Session, statement: Select[tuple[ModelT]], model: type[ModelT], values: dict[str, Any]) -> ModelT:
    instance = session.execute(statement).scalar_one_or_none()
    if instance is None:
        instance = model(**values)
        session.add(instance)
        session.flush()
    else:
        for key, value in values.items():
            setattr(instance, key, value)
        session.flush()
    return instance


def seed_user_and_family(session: Session) -> dict[str, FamilyMember | User]:
    user = one_or_create(
        session,
        select(User).where(User.phone == "13800000001"),
        User,
        {"name": "陈毅", "phone": "13800000001", "is_active": True},
    )

    myself = one_or_create(
        session,
        select(FamilyMember).where(FamilyMember.user_id == user.id, FamilyMember.relationship == "self"),
        FamilyMember,
        {
            "user_id": user.id,
            "name": "陈毅",
            "relationship": "self",
            "gender": "male",
            "birthday": date(1998, 5, 10),
            "default_address": "上海市浦东新区互联网医院示例地址",
        },
    )
    father = one_or_create(
        session,
        select(FamilyMember).where(FamilyMember.user_id == user.id, FamilyMember.relationship == "father"),
        FamilyMember,
        {
            "user_id": user.id,
            "name": "父亲",
            "relationship": "father",
            "gender": "male",
            "birthday": date(1965, 8, 20),
            "default_address": "上海市浦东新区互联网医院示例地址",
        },
    )
    mother = one_or_create(
        session,
        select(FamilyMember).where(FamilyMember.user_id == user.id, FamilyMember.relationship == "mother"),
        FamilyMember,
        {
            "user_id": user.id,
            "name": "母亲",
            "relationship": "mother",
            "gender": "female",
            "birthday": date(1968, 3, 12),
            "default_address": "上海市浦东新区互联网医院示例地址",
        },
    )

    profile_data = [
        (
            myself,
            {
                "member_id": myself.id,
                "chronic_disease_tags": [],
                "allergies": [],
                "current_medications": [],
                "health_notes": "普通健康档案，当前无长期慢病用药记录。",
                "safety_notes": ["系统仅做健康事务管理，不做诊断。"],
            },
        ),
        (
            father,
            {
                "member_id": father.id,
                "chronic_disease_tags": ["高血压", "慢病长期用药"],
                "allergies": ["未记录明确药物过敏史"],
                "current_medications": [{"medicine_name": "苯磺酸氨氯地平片", "usage": "按医生处方服用"}],
                "health_notes": "父亲为高血压长期用药场景，续方前需要医生确认。",
                "safety_notes": ["不得建议自行加量、减量、停药或换药。"],
            },
        ),
        (
            mother,
            {
                "member_id": mother.id,
                "chronic_disease_tags": ["睡眠问题", "中医复诊"],
                "allergies": ["未记录明确药物过敏史"],
                "current_medications": [{"medicine_name": "中药颗粒", "usage": "按上次中医处方疗程服用"}],
                "health_notes": "母亲需要整理中医复诊材料，不生成诊断结论。",
                "safety_notes": ["中医复诊材料仅做整理，提交前需要用户确认。"],
            },
        ),
    ]

    for member, values in profile_data:
        one_or_create(
            session,
            select(HealthProfile).where(HealthProfile.member_id == member.id),
            HealthProfile,
            values,
        )

    return {"user": user, "myself": myself, "father": father, "mother": mother}


def seed_medication_context(session: Session, father: FamilyMember, mother: FamilyMember) -> dict[str, Any]:
    today = date.today()

    father_prescription = one_or_create(
        session,
        select(Prescription).where(Prescription.prescription_no == "RX-FATHER-BP-001"),
        Prescription,
        {
            "member_id": father.id,
            "prescription_no": "RX-FATHER-BP-001",
            "doctor_name": "王医生",
            "hospital_name": "示例互联网医院",
            "doctor_diagnosis_summary": "医生处方记录：高血压长期管理。",
            "medicine_items": [
                {
                    "medicine_name": "苯磺酸氨氯地平片",
                    "specification": "5mg*28片",
                    "dosage": "每次1片",
                    "frequency": "每日1次",
                }
            ],
            "issued_at": today - timedelta(days=25),
            "expires_at": today + timedelta(days=5),
            "status": "valid",
            "doctor_confirmation_required": True,
            "safety_note": "续方和剂量相关判断必须由医生确认。",
        },
    )

    mother_prescription = one_or_create(
        session,
        select(Prescription).where(Prescription.prescription_no == "RX-MOTHER-TCM-001"),
        Prescription,
        {
            "member_id": mother.id,
            "prescription_no": "RX-MOTHER-TCM-001",
            "doctor_name": "李医生",
            "hospital_name": "示例中医互联网医院",
            "doctor_diagnosis_summary": "医生处方记录：睡眠问题中医调理。",
            "medicine_items": [
                {
                    "medicine_name": "中药颗粒",
                    "specification": "7剂",
                    "dosage": "每次1袋",
                    "frequency": "早晚各1次",
                }
            ],
            "issued_at": today - timedelta(days=5),
            "expires_at": today + timedelta(days=10),
            "status": "valid",
            "doctor_confirmation_required": True,
            "safety_note": "复诊材料仅做整理，不能替代医生辨证。",
        },
    )

    father_box = one_or_create(
        session,
        select(MedicineBoxItem).where(
            MedicineBoxItem.member_id == father.id,
            MedicineBoxItem.medicine_name == "苯磺酸氨氯地平片",
        ),
        MedicineBoxItem,
        {
            "member_id": father.id,
            "medicine_name": "苯磺酸氨氯地平片",
            "specification": "5mg*28片",
            "total_quantity": 28,
            "remaining_quantity": 3,
            "dosage": "每次1片",
            "frequency": "每日1次",
            "purchased_at": today - timedelta(days=25),
            "estimated_remaining_days": 3,
            "safety_note": "剩余约3天，建议准备复诊续方材料并等待确认。",
        },
    )
    mother_box = one_or_create(
        session,
        select(MedicineBoxItem).where(MedicineBoxItem.member_id == mother.id, MedicineBoxItem.medicine_name == "中药颗粒"),
        MedicineBoxItem,
        {
            "member_id": mother.id,
            "medicine_name": "中药颗粒",
            "specification": "7剂",
            "total_quantity": 14,
            "remaining_quantity": 4,
            "dosage": "每次1袋",
            "frequency": "早晚各1次",
            "purchased_at": today - timedelta(days=5),
            "estimated_remaining_days": 2,
            "safety_note": "剩余约2天，可整理复诊材料，提交前需要确认。",
        },
    )

    one_or_create(
        session,
        select(PurchaseRecord).where(
            PurchaseRecord.prescription_id == father_prescription.id,
            PurchaseRecord.medicine_name == "苯磺酸氨氯地平片",
        ),
        PurchaseRecord,
        {
            "member_id": father.id,
            "prescription_id": father_prescription.id,
            "pharmacy_id": None,
            "medicine_name": "苯磺酸氨氯地平片",
            "quantity": 28,
            "dosage": "每次1片",
            "frequency": "每日1次",
            "pharmacy_name": "仁心互联网药房",
            "purchased_at": today - timedelta(days=25),
            "purchase_channel": "internet_hospital",
        },
    )
    one_or_create(
        session,
        select(PurchaseRecord).where(PurchaseRecord.prescription_id == mother_prescription.id, PurchaseRecord.medicine_name == "中药颗粒"),
        PurchaseRecord,
        {
            "member_id": mother.id,
            "prescription_id": mother_prescription.id,
            "pharmacy_id": None,
            "medicine_name": "中药颗粒",
            "quantity": 14,
            "dosage": "每次1袋",
            "frequency": "早晚各1次",
            "pharmacy_name": "安和中医药房",
            "purchased_at": today - timedelta(days=5),
            "purchase_channel": "internet_hospital",
        },
    )

    refill_plan = one_or_create(
        session,
        select(RefillPlan).where(RefillPlan.member_id == father.id, RefillPlan.medicine_name == "苯磺酸氨氯地平片"),
        RefillPlan,
        {
            "member_id": father.id,
            "prescription_id": father_prescription.id,
            "medicine_name": "苯磺酸氨氯地平片",
            "remaining_days": 3,
            "plan_detail": {"next_step": "整理续方材料，等待用户确认后发起复诊申请"},
            "suggestion": "可准备复诊续方材料，不自动开方。",
            "safety_note": "不提供剂量调整建议。",
            "doctor_confirmation_required": True,
            "status": "draft",
            "need_human_confirmation": True,
            "confirmed_at": None,
            "confirmation_note": None,
        },
    )
    consultation_draft = one_or_create(
        session,
        select(ConsultationDraft).where(ConsultationDraft.member_id == mother.id, ConsultationDraft.prescription_id == mother_prescription.id),
        ConsultationDraft,
        {
            "member_id": mother.id,
            "prescription_id": mother_prescription.id,
            "draft_content": "母亲中药颗粒即将服完，需整理上次处方、购药记录和近期睡眠情况给医生复诊参考。",
            "material_summary": {"remaining_days": 2, "materials": ["历史处方", "购药记录", "近期睡眠变化"]},
            "safety_note": "复诊材料仅供医生参考，提交前需要用户确认。",
            "doctor_confirmation_required": True,
            "status": "draft",
            "need_human_confirmation": True,
            "confirmed_at": None,
            "confirmation_note": None,
        },
    )

    return {
        "father_prescription": father_prescription,
        "mother_prescription": mother_prescription,
        "father_box": father_box,
        "mother_box": mother_box,
        "refill_plan": refill_plan,
        "consultation_draft": consultation_draft,
    }


def seed_pharmacy(session: Session) -> None:
    pharmacy_a = one_or_create(
        session,
        select(Pharmacy).where(Pharmacy.name == "仁心互联网药房", Pharmacy.city == "上海"),
        Pharmacy,
        {
            "name": "仁心互联网药房",
            "city": "上海",
            "address": "上海市浦东新区示例路1号",
            "supports_delivery": True,
            "supports_pickup": True,
            "contact_phone": "021-00000001",
        },
    )
    pharmacy_b = one_or_create(
        session,
        select(Pharmacy).where(Pharmacy.name == "安和中医药房", Pharmacy.city == "上海"),
        Pharmacy,
        {
            "name": "安和中医药房",
            "city": "上海",
            "address": "上海市徐汇区示例路2号",
            "supports_delivery": True,
            "supports_pickup": False,
            "contact_phone": "021-00000002",
        },
    )

    for pharmacy, medicine_name, stock, options, note in [
        (pharmacy_a, "苯磺酸氨氯地平片", 120, ["delivery", "pickup"], "有库存，可邮寄或自取。"),
        (pharmacy_a, "中药颗粒", 0, ["delivery"], "库存不足，需联系药房确认。"),
        (pharmacy_b, "中药颗粒", 50, ["delivery"], "有库存，可邮寄。"),
    ]:
        one_or_create(
            session,
            select(PharmacyInventory).where(PharmacyInventory.pharmacy_id == pharmacy.id, PharmacyInventory.medicine_name == medicine_name),
            PharmacyInventory,
            {
                "pharmacy_id": pharmacy.id,
                "medicine_name": medicine_name,
                "stock_quantity": stock,
                "delivery_options": options,
                "safety_note": note,
            },
        )


def seed_knowledge(session: Session) -> None:
    documents = [
        (
            "复诊续方 SOP",
            "refill_sop",
            "internal_sop:v1",
            "复诊续方流程必须先整理历史处方、购药记录、剩余药量和用户主诉，再由用户确认后提交医生。",
            ["复诊", "续方", "医生确认"],
        ),
        (
            "用药提醒模板",
            "reminder_template",
            "internal_template:v1",
            "创建用药提醒前，需要向用户展示提醒对象、药品名称、提醒时间、频次和确认状态。",
            ["用药提醒", "人工确认"],
        ),
        (
            "人工确认规则",
            "human_confirmation",
            "safety_policy:v1",
            "复诊申请、购药方案、提醒创建等关键动作必须等待用户确认后执行。",
            ["人工确认", "关键动作"],
        ),
        (
            "医疗安全边界规则",
            "medical_safety",
            "safety_policy:v1",
            "系统不诊断、不自动开方、不修改处方，不提供自行加量、减量、停药、换药建议。",
            ["安全边界", "不诊断", "不自动开方"],
        ),
    ]

    for title, category, source, content, keywords in documents:
        document = one_or_create(
            session,
            select(KnowledgeDocument).where(KnowledgeDocument.title == title),
            KnowledgeDocument,
            {
                "title": title,
                "category": category,
                "source": source,
                "content": content,
                "safety_level": "medical_boundary" if "安全" in title else "general",
            },
        )
        one_or_create(
            session,
            select(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id, KnowledgeChunk.chunk_index == 0),
            KnowledgeChunk,
            {
                "document_id": document.id,
                "chunk_index": 0,
                "content": content,
                "keywords": keywords,
            },
        )


def seed_agent_audit_example(session: Session, user: User, father: FamilyMember) -> None:
    run_started = datetime.now(timezone.utc)
    run_ended = run_started + timedelta(milliseconds=180)
    run = one_or_create(
        session,
        select(AgentRun).where(AgentRun.user_id == user.id, AgentRun.user_goal == "我爸的降压药快吃完了，帮我看看能不能续方。"),
        AgentRun,
        {
            "user_id": user.id,
            "member_id": father.id,
            "user_goal": "我爸的降压药快吃完了，帮我看看能不能续方。",
            "intent": "chronic_refill",
            "status": "draft",
            "final_answer": "已整理父亲降压药续方前材料，等待用户确认后再发起复诊申请。",
            "need_human_confirmation": True,
            "safety_result": {"allowed": True, "reason": "仅整理材料，不诊断、不开方、不调整剂量。"},
            "raw_state": {"phase": "seed_demo", "remaining_days": 3},
            "started_at": run_started,
            "ended_at": run_ended,
            "duration_ms": 180,
            "step_count": 4,
            "task_success": True,
            "groundedness_score": 1.0,
            "hallucination_flag": False,
            "human_confirmation_rate": 1.0,
        },
    )
    one_or_create(
        session,
        select(AgentToolCall).where(AgentToolCall.run_id == run.id, AgentToolCall.tool_name == "get_medicine_box"),
        AgentToolCall,
        {
            "run_id": run.id,
            "agent_role": "RefillAgent",
            "tool_name": "get_medicine_box",
            "tool_input": {"member_id": father.id},
            "tool_output": {"medicine_name": "苯磺酸氨氯地平片", "estimated_remaining_days": 3},
            "latency_ms": 12,
            "success": True,
            "error_message": None,
            "error_type": None,
            "fallback_action": "not_required",
            "schema_valid": True,
        },
    )
    one_or_create(
        session,
        select(AgentToolCall).where(AgentToolCall.run_id == run.id, AgentToolCall.tool_name == "check_pharmacy_inventory"),
        AgentToolCall,
        {
            "run_id": run.id,
            "agent_role": "PharmacyAgent",
            "tool_name": "check_pharmacy_inventory",
            "tool_input": {"medicine_name": "苯磺酸氨氯地平片", "city": "上海"},
            "tool_output": None,
            "latency_ms": 120,
            "success": False,
            "error_message": "seed demo: pharmacy inventory service unavailable",
            "error_type": "tool_unavailable",
            "fallback_action": "use_prescription_material_draft_only",
            "schema_valid": True,
        },
    )


def main() -> None:
    with SessionLocal() as session:
        family = seed_user_and_family(session)
        seed_medication_context(session, family["father"], family["mother"])
        seed_pharmacy(session)
        seed_knowledge(session)
        seed_agent_audit_example(session, family["user"], family["father"])
        session.commit()
        print("Seed data is ready: user=陈毅, members=本人/父亲/母亲, medication contexts, pharmacy inventory, knowledge rules.")


if __name__ == "__main__":
    main()
