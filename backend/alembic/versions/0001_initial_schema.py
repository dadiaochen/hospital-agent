"""initial schema

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-06-04 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_phone", "users", ["phone"], unique=True)

    op.create_table(
        "pharmacies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("city", sa.String(length=80), nullable=False),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("supports_delivery", sa.Boolean(), nullable=False),
        sa.Column("supports_pickup", sa.Boolean(), nullable=False),
        sa.Column("contact_phone", sa.String(length=32), nullable=True),
        *timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "city", name="uq_pharmacy_name_city"),
    )
    op.create_index("ix_pharmacies_city", "pharmacies", ["city"], unique=False)

    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("source", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("safety_level", sa.String(length=40), nullable=False),
        *timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_documents_category", "knowledge_documents", ["category"], unique=False)
    op.create_index("ix_knowledge_documents_title", "knowledge_documents", ["title"], unique=False)

    op.create_table(
        "family_members",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("relationship", sa.String(length=40), nullable=False),
        sa.Column("gender", sa.String(length=20), nullable=True),
        sa.Column("birthday", sa.Date(), nullable=True),
        sa.Column("default_address", sa.String(length=255), nullable=True),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "relationship", name="uq_family_member_user_relationship"),
    )
    op.create_index("ix_family_members_user_id", "family_members", ["user_id"], unique=False)

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("keywords", sa.JSON(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["document_id"], ["knowledge_documents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_chunks_document_id", "knowledge_chunks", ["document_id"], unique=False)

    op.create_table(
        "pharmacy_inventory",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("pharmacy_id", sa.String(length=36), nullable=False),
        sa.Column("medicine_name", sa.String(length=120), nullable=False),
        sa.Column("stock_quantity", sa.Integer(), nullable=False),
        sa.Column("delivery_options", sa.JSON(), nullable=False),
        sa.Column("safety_note", sa.String(length=255), nullable=True),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["pharmacy_id"], ["pharmacies.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pharmacy_id", "medicine_name", name="uq_pharmacy_inventory_medicine"),
    )
    op.create_index("ix_pharmacy_inventory_medicine_name", "pharmacy_inventory", ["medicine_name"], unique=False)
    op.create_index("ix_pharmacy_inventory_pharmacy_id", "pharmacy_inventory", ["pharmacy_id"], unique=False)

    op.create_table(
        "health_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("member_id", sa.String(length=36), nullable=False),
        sa.Column("chronic_disease_tags", sa.JSON(), nullable=False),
        sa.Column("allergies", sa.JSON(), nullable=False),
        sa.Column("current_medications", sa.JSON(), nullable=False),
        sa.Column("health_notes", sa.Text(), nullable=True),
        sa.Column("safety_notes", sa.JSON(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["member_id"], ["family_members.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("member_id"),
    )

    op.create_table(
        "medicine_box_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("member_id", sa.String(length=36), nullable=False),
        sa.Column("medicine_name", sa.String(length=120), nullable=False),
        sa.Column("specification", sa.String(length=120), nullable=True),
        sa.Column("total_quantity", sa.Integer(), nullable=False),
        sa.Column("remaining_quantity", sa.Integer(), nullable=False),
        sa.Column("dosage", sa.String(length=120), nullable=False),
        sa.Column("frequency", sa.String(length=120), nullable=False),
        sa.Column("purchased_at", sa.Date(), nullable=True),
        sa.Column("estimated_remaining_days", sa.Integer(), nullable=True),
        sa.Column("safety_note", sa.Text(), nullable=True),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["member_id"], ["family_members.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_medicine_box_items_medicine_name", "medicine_box_items", ["medicine_name"], unique=False)
    op.create_index("ix_medicine_box_items_member_id", "medicine_box_items", ["member_id"], unique=False)

    op.create_table(
        "prescriptions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("member_id", sa.String(length=36), nullable=False),
        sa.Column("prescription_no", sa.String(length=80), nullable=True),
        sa.Column("doctor_name", sa.String(length=80), nullable=True),
        sa.Column("hospital_name", sa.String(length=120), nullable=True),
        sa.Column("doctor_diagnosis_summary", sa.Text(), nullable=True),
        sa.Column("medicine_items", sa.JSON(), nullable=False),
        sa.Column("issued_at", sa.Date(), nullable=True),
        sa.Column("expires_at", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("doctor_confirmation_required", sa.Boolean(), nullable=False),
        sa.Column("safety_note", sa.Text(), nullable=True),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["member_id"], ["family_members.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prescriptions_member_id", "prescriptions", ["member_id"], unique=False)
    op.create_index("ix_prescriptions_prescription_no", "prescriptions", ["prescription_no"], unique=True)

    op.create_table(
        "purchase_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("member_id", sa.String(length=36), nullable=False),
        sa.Column("prescription_id", sa.String(length=36), nullable=True),
        sa.Column("pharmacy_id", sa.String(length=36), nullable=True),
        sa.Column("medicine_name", sa.String(length=120), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("dosage", sa.String(length=120), nullable=True),
        sa.Column("frequency", sa.String(length=120), nullable=True),
        sa.Column("pharmacy_name", sa.String(length=120), nullable=True),
        sa.Column("purchased_at", sa.Date(), nullable=True),
        sa.Column("purchase_channel", sa.String(length=80), nullable=True),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["member_id"], ["family_members.id"]),
        sa.ForeignKeyConstraint(["pharmacy_id"], ["pharmacies.id"]),
        sa.ForeignKeyConstraint(["prescription_id"], ["prescriptions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_purchase_records_medicine_name", "purchase_records", ["medicine_name"], unique=False)
    op.create_index("ix_purchase_records_member_id", "purchase_records", ["member_id"], unique=False)
    op.create_index("ix_purchase_records_pharmacy_id", "purchase_records", ["pharmacy_id"], unique=False)
    op.create_index("ix_purchase_records_prescription_id", "purchase_records", ["prescription_id"], unique=False)

    op.create_table(
        "refill_plans",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("member_id", sa.String(length=36), nullable=False),
        sa.Column("prescription_id", sa.String(length=36), nullable=True),
        sa.Column("medicine_name", sa.String(length=120), nullable=False),
        sa.Column("remaining_days", sa.Integer(), nullable=True),
        sa.Column("plan_detail", sa.JSON(), nullable=False),
        sa.Column("suggestion", sa.Text(), nullable=True),
        sa.Column("safety_note", sa.Text(), nullable=True),
        sa.Column("doctor_confirmation_required", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("need_human_confirmation", sa.Boolean(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmation_note", sa.Text(), nullable=True),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["member_id"], ["family_members.id"]),
        sa.ForeignKeyConstraint(["prescription_id"], ["prescriptions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_refill_plans_medicine_name", "refill_plans", ["medicine_name"], unique=False)
    op.create_index("ix_refill_plans_member_id", "refill_plans", ["member_id"], unique=False)
    op.create_index("ix_refill_plans_prescription_id", "refill_plans", ["prescription_id"], unique=False)

    op.create_table(
        "consultation_drafts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("member_id", sa.String(length=36), nullable=False),
        sa.Column("prescription_id", sa.String(length=36), nullable=True),
        sa.Column("draft_content", sa.Text(), nullable=False),
        sa.Column("material_summary", sa.JSON(), nullable=False),
        sa.Column("safety_note", sa.Text(), nullable=True),
        sa.Column("doctor_confirmation_required", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("need_human_confirmation", sa.Boolean(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmation_note", sa.Text(), nullable=True),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["member_id"], ["family_members.id"]),
        sa.ForeignKeyConstraint(["prescription_id"], ["prescriptions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_consultation_drafts_member_id", "consultation_drafts", ["member_id"], unique=False)
    op.create_index("ix_consultation_drafts_prescription_id", "consultation_drafts", ["prescription_id"], unique=False)

    op.create_table(
        "purchase_plans",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("member_id", sa.String(length=36), nullable=False),
        sa.Column("medicine_name", sa.String(length=120), nullable=False),
        sa.Column("pharmacy_id", sa.String(length=36), nullable=True),
        sa.Column("plan_detail", sa.JSON(), nullable=False),
        sa.Column("delivery_option", sa.String(length=80), nullable=True),
        sa.Column("safety_note", sa.Text(), nullable=True),
        sa.Column("doctor_confirmation_required", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("need_human_confirmation", sa.Boolean(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmation_note", sa.Text(), nullable=True),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["member_id"], ["family_members.id"]),
        sa.ForeignKeyConstraint(["pharmacy_id"], ["pharmacies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_purchase_plans_medicine_name", "purchase_plans", ["medicine_name"], unique=False)
    op.create_index("ix_purchase_plans_member_id", "purchase_plans", ["member_id"], unique=False)
    op.create_index("ix_purchase_plans_pharmacy_id", "purchase_plans", ["pharmacy_id"], unique=False)

    op.create_table(
        "medication_reminders",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("member_id", sa.String(length=36), nullable=False),
        sa.Column("medicine_box_item_id", sa.String(length=36), nullable=True),
        sa.Column("medicine_name", sa.String(length=120), nullable=False),
        sa.Column("schedule", sa.JSON(), nullable=False),
        sa.Column("reminder_type", sa.String(length=40), nullable=False),
        sa.Column("safety_note", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("need_human_confirmation", sa.Boolean(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmation_note", sa.Text(), nullable=True),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["medicine_box_item_id"], ["medicine_box_items.id"]),
        sa.ForeignKeyConstraint(["member_id"], ["family_members.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_medication_reminders_medicine_box_item_id", "medication_reminders", ["medicine_box_item_id"], unique=False)
    op.create_index("ix_medication_reminders_medicine_name", "medication_reminders", ["medicine_name"], unique=False)
    op.create_index("ix_medication_reminders_member_id", "medication_reminders", ["member_id"], unique=False)

    op.create_table(
        "follow_up_tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("member_id", sa.String(length=36), nullable=False),
        sa.Column("task_type", sa.String(length=80), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("task_payload", sa.JSON(), nullable=False),
        sa.Column("safety_note", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("need_human_confirmation", sa.Boolean(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmation_note", sa.Text(), nullable=True),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["member_id"], ["family_members.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_follow_up_tasks_member_id", "follow_up_tasks", ["member_id"], unique=False)

    op.create_table(
        "agent_memories",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("member_id", sa.String(length=36), nullable=True),
        sa.Column("memory_type", sa.String(length=80), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=True),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["member_id"], ["family_members.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_memories_member_id", "agent_memories", ["member_id"], unique=False)
    op.create_index("ix_agent_memories_user_id", "agent_memories", ["user_id"], unique=False)

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("member_id", sa.String(length=36), nullable=True),
        sa.Column("user_goal", sa.Text(), nullable=False),
        sa.Column("intent", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("final_answer", sa.Text(), nullable=True),
        sa.Column("need_human_confirmation", sa.Boolean(), nullable=False),
        sa.Column("safety_result", sa.JSON(), nullable=False),
        sa.Column("raw_state", sa.JSON(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["member_id"], ["family_members.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_runs_intent", "agent_runs", ["intent"], unique=False)
    op.create_index("ix_agent_runs_member_id", "agent_runs", ["member_id"], unique=False)
    op.create_index("ix_agent_runs_user_id", "agent_runs", ["user_id"], unique=False)

    op.create_table(
        "agent_tool_calls",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("tool_name", sa.String(length=120), nullable=False),
        sa.Column("tool_input", sa.JSON(), nullable=False),
        sa.Column("tool_output", sa.JSON(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_tool_calls_run_id", "agent_tool_calls", ["run_id"], unique=False)
    op.create_index("ix_agent_tool_calls_tool_name", "agent_tool_calls", ["tool_name"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_agent_tool_calls_tool_name", table_name="agent_tool_calls")
    op.drop_index("ix_agent_tool_calls_run_id", table_name="agent_tool_calls")
    op.drop_table("agent_tool_calls")
    op.drop_index("ix_agent_runs_user_id", table_name="agent_runs")
    op.drop_index("ix_agent_runs_member_id", table_name="agent_runs")
    op.drop_index("ix_agent_runs_intent", table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_index("ix_agent_memories_user_id", table_name="agent_memories")
    op.drop_index("ix_agent_memories_member_id", table_name="agent_memories")
    op.drop_table("agent_memories")
    op.drop_index("ix_follow_up_tasks_member_id", table_name="follow_up_tasks")
    op.drop_table("follow_up_tasks")
    op.drop_index("ix_medication_reminders_member_id", table_name="medication_reminders")
    op.drop_index("ix_medication_reminders_medicine_name", table_name="medication_reminders")
    op.drop_index("ix_medication_reminders_medicine_box_item_id", table_name="medication_reminders")
    op.drop_table("medication_reminders")
    op.drop_index("ix_purchase_plans_pharmacy_id", table_name="purchase_plans")
    op.drop_index("ix_purchase_plans_member_id", table_name="purchase_plans")
    op.drop_index("ix_purchase_plans_medicine_name", table_name="purchase_plans")
    op.drop_table("purchase_plans")
    op.drop_index("ix_consultation_drafts_prescription_id", table_name="consultation_drafts")
    op.drop_index("ix_consultation_drafts_member_id", table_name="consultation_drafts")
    op.drop_table("consultation_drafts")
    op.drop_index("ix_refill_plans_prescription_id", table_name="refill_plans")
    op.drop_index("ix_refill_plans_member_id", table_name="refill_plans")
    op.drop_index("ix_refill_plans_medicine_name", table_name="refill_plans")
    op.drop_table("refill_plans")
    op.drop_index("ix_purchase_records_prescription_id", table_name="purchase_records")
    op.drop_index("ix_purchase_records_pharmacy_id", table_name="purchase_records")
    op.drop_index("ix_purchase_records_member_id", table_name="purchase_records")
    op.drop_index("ix_purchase_records_medicine_name", table_name="purchase_records")
    op.drop_table("purchase_records")
    op.drop_index("ix_prescriptions_prescription_no", table_name="prescriptions")
    op.drop_index("ix_prescriptions_member_id", table_name="prescriptions")
    op.drop_table("prescriptions")
    op.drop_index("ix_medicine_box_items_member_id", table_name="medicine_box_items")
    op.drop_index("ix_medicine_box_items_medicine_name", table_name="medicine_box_items")
    op.drop_table("medicine_box_items")
    op.drop_table("health_profiles")
    op.drop_index("ix_pharmacy_inventory_pharmacy_id", table_name="pharmacy_inventory")
    op.drop_index("ix_pharmacy_inventory_medicine_name", table_name="pharmacy_inventory")
    op.drop_table("pharmacy_inventory")
    op.drop_index("ix_knowledge_chunks_document_id", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    op.drop_index("ix_family_members_user_id", table_name="family_members")
    op.drop_table("family_members")
    op.drop_index("ix_knowledge_documents_title", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_category", table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
    op.drop_index("ix_pharmacies_city", table_name="pharmacies")
    op.drop_table("pharmacies")
    op.drop_index("ix_users_phone", table_name="users")
    op.drop_table("users")

