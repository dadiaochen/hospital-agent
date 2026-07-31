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

export type AgentIntent = "refill" | "reminder" | "pharmacy" | "safety_check";

export type AgentRunCreateRequest = {
  member_id: string;
  idempotency_key: string;
  user_input: string;
  medication_name?: string;
  city?: string;
  human_confirmation_granted: false;
};

export type AgentRunContinueRequest = {
  idempotency_key: string;
  confirmation_message: string;
  human_confirmation_granted: true;
};

export type ToolCallTrace = {
  tool_name: string;
  member_id: string;
  source_id: string | null;
  source_name: string | null;
  success: boolean;
  schema_valid: boolean;
  evidence_present: boolean;
};

export type RAGTrace = {
  source_id: string;
  source_name: string;
  member_id: string | null;
  retrieved: boolean;
  schema_valid: boolean;
};

export type SafetyTrace = {
  member_id: string;
  flags: string[];
  blocked: boolean;
  requires_human_confirmation: boolean;
};

export type FinalAnswerTrace = {
  answer_id: string;
  content: string;
  contains_factual_claims: boolean;
  waiting_for_user_confirmation: boolean;
  human_confirmation_present: boolean;
  action_status: "none" | "draft" | "awaiting_confirmation" | "executed";
};

export type RunTrace = {
  case_id: string;
  run_id: string;
  task_id: string;
  user_id: string;
  member_id: string;
  intent: AgentIntent;
  tool_calls: ToolCallTrace[];
  rag_traces: RAGTrace[];
  safety_trace: SafetyTrace;
  final_answer: FinalAnswerTrace;
  latency_ms: number;
  schema_valid: boolean;
};

export type ToolEvidenceRef = {
  source_id: string;
  run_id: string;
  member_id: string;
  tool_name: string;
  tool_call_id: string | null;
  success: boolean;
  schema_valid: boolean;
};

export type RAGSourceRef = {
  source_id: string;
  document_id: string;
  chunk_id: string;
  member_id: string | null;
  version: string | null;
  purpose: string;
};

export type ConfirmedFact = {
  fact_key: string;
  value: unknown;
  source_ids: string[];
  confirmed_by_user: boolean;
};

export type RunSummary = {
  run_id: string;
  task_id: string;
  member_id: string;
  intent: AgentIntent;
  final_status: "completed" | "needs_confirmation" | "blocked" | "failed";
  confirmed_facts: ConfirmedFact[];
  pending_confirmations: string[];
  safety_flags: string[];
  tool_evidence_refs: ToolEvidenceRef[];
  rag_source_refs: RAGSourceRef[];
  final_answer_ref: string;
  evaluation_ref: string | null;
};

export type EvaluationResult = {
  case_id: string;
  run_id: string;
  task_success: boolean;
  tool_call_accuracy: number | null;
  groundedness: number | null;
  schema_valid: boolean;
  hallucination_detected: boolean;
  safety_recall: number | null;
  human_confirmation_required: boolean;
  human_confirmation_present: boolean;
  context_isolation_passed: boolean;
  latency_ms: number;
  failure_reasons: string[];
};

export type ModelProviderAttemptTrace = {
  provider_name: string;
  model_name: string;
  success: boolean;
  schema_valid: boolean;
  safety_passed: boolean;
  safety_flags: string[];
  latency_ms: number;
  error_type: string | null;
};

export type ModelCallTrace = {
  run_id: string;
  task_id: string;
  member_id: string;
  purpose: string;
  requested_provider: string;
  effective_provider: string | null;
  success: boolean;
  schema_valid: boolean;
  safety_passed: boolean;
  fallback_used: boolean;
  fallback_reason: string | null;
  latency_ms: number;
  attempts: ModelProviderAttemptTrace[];
};

export type AgentRunArtifacts = {
  run_id: string;
  task_id: string;
  status: string;
  run_trace: RunTrace;
  model_call_trace: ModelCallTrace;
  run_summary: RunSummary;
  tool_evidence_refs: ToolEvidenceRef[];
  rag_source_refs: RAGSourceRef[];
  safety_trace: SafetyTrace;
  evaluation_result: EvaluationResult;
  resumed_from_run_id: string | null;
  restored_source_ids: string[];
  external_action_status: "not_submitted";
};

export type AgentRunExecution = {
  run: AgentRun;
  artifacts: AgentRunArtifacts;
  idempotent_replay: boolean;
};

export type AgentToolCall = {
  id: string;
  run_id: string;
  agent_role: string;
  tool_name: string;
  tool_input: Record<string, unknown>;
  tool_output: Record<string, unknown> | null;
  latency_ms: number | null;
  success: boolean;
  error_message: string | null;
  error_type: string | null;
  fallback_action: string | null;
  schema_valid: boolean;
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
