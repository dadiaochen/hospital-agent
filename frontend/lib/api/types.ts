export type FamilyMember = {
  id: string;
  name: string;
  relationship: string;
  gender: string | null;
  birthday: string | null;
  default_address: string | null;
};

export type HealthProfile = {
  member_id: string;
  chronic_disease_tags: string[];
  allergies: string[];
  current_medications: Array<Record<string, unknown>>;
  health_notes: string | null;
  safety_notes: string[];
};

export type FamilyMemberHealthProfile = {
  member: FamilyMember;
  profile: HealthProfile;
};

export type MedicineBoxItem = {
  id: string;
  member_id: string;
  medicine_name: string;
  specification: string | null;
  total_quantity: number;
  remaining_quantity: number;
  dosage: string;
  frequency: string;
  purchased_at: string | null;
  estimated_remaining_days: number | null;
  safety_note: string | null;
};

export type Prescription = {
  id: string;
  member_id: string;
  prescription_no: string | null;
  doctor_name: string | null;
  hospital_name: string | null;
  doctor_diagnosis_summary: string | null;
  medicine_items: Array<Record<string, unknown>>;
  issued_at: string | null;
  expires_at: string | null;
  status: string;
  doctor_confirmation_required: boolean;
  safety_note: string | null;
};

export type PurchaseRecord = {
  id: string;
  member_id: string;
  prescription_id: string | null;
  pharmacy_id: string | null;
  medicine_name: string;
  quantity: number;
  dosage: string | null;
  frequency: string | null;
  pharmacy_name: string | null;
  purchased_at: string | null;
  purchase_channel: string | null;
};

export type PharmacyInventoryItem = {
  inventory_id: string;
  pharmacy_id: string;
  pharmacy_name: string;
  city: string;
  address: string | null;
  supports_delivery: boolean;
  supports_pickup: boolean;
  contact_phone: string | null;
  medicine_name: string;
  stock_quantity: number;
  delivery_options: string[];
  safety_note: string | null;
};

export type ConfirmationDraftType =
  | "refill_request"
  | "consultation_request"
  | "pharmacy_option"
  | "reminder_create";

export type ConfirmationDraft = {
  source_id: string;
  draft_id: string;
  draft_type: ConfirmationDraftType;
  member_id: string;
  status: "draft" | "confirmed" | "rejected";
  need_human_confirmation: boolean;
  local_confirmation_recorded: boolean;
  confirmed_at: string | null;
  resolved_at: string | null;
  decision_note: string | null;
  summary: string | null;
  created_by_run_id: string | null;
  idempotency_key: string | null;
  external_action_status: "not_submitted";
  content: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  idempotent_replay: boolean;
};

export type AgentRun = {
  id: string;
  user_id: string;
  member_id: string | null;
  user_goal: string;
  intent: string | null;
  status: string;
  final_answer: string | null;
  need_human_confirmation: boolean;
  safety_result: Record<string, unknown>;
  started_at: string;
  ended_at: string | null;
  duration_ms: number | null;
  step_count: number;
  task_success: boolean | null;
  groundedness_score: number | null;
  hallucination_flag: boolean;
  human_confirmation_rate: number | null;
};

export type KnowledgeSearchItem = {
  source_id: string;
  document_id: string;
  chunk_id: string;
  title: string;
  category: string;
  source: string;
  safety_level: string;
  chunk_index: number;
  content: string;
  keywords: string[];
};

export type ListResponse<T> = {
  items: T[];
};

export type ApiErrorBody = {
  error?: {
    code?: string;
    message?: string;
    details?: unknown;
  };
};
