import type { AgentRunExecution, AgentToolCall, FamilyMember } from "@/lib/api/types";

export const testMembers: FamilyMember[] = [
  { id: "member-father", name: "陈父", relationship: "father", gender: "male", birthday: null, default_address: "上海" },
  { id: "member-mother", name: "陈母", relationship: "mother", gender: "female", birthday: null, default_address: "上海" },
];

type ExecutionOptions = {
  memberId?: string;
  runId?: string;
  status?: "completed" | "needs_confirmation" | "blocked" | "failed";
  blocked?: boolean;
  waitingForConfirmation?: boolean;
  confirmationPresent?: boolean;
  finalAnswer?: string;
  intent?: string;
};

export function makeAgentExecution(options: ExecutionOptions = {}): AgentRunExecution {
  const memberId = options.memberId ?? "member-father";
  const runId = options.runId ?? "run-3b-demo";
  const status = options.status ?? "needs_confirmation";
  const blocked = options.blocked ?? false;
  const waiting = options.waitingForConfirmation ?? status === "needs_confirmation";
  const confirmationPresent = options.confirmationPresent ?? status === "completed";
  const finalAnswer = options.finalAnswer ?? "已根据药箱和处方记录整理续方草稿，请确认后创建本地记录。";
  const intent = options.intent ?? (blocked ? "safety_check" : "refill");
  const safetyFlags = blocked ? ["dosage_change_request"] : ["human_confirmation_required"];

  const toolRef = {
    source_id: "source-tool-1",
    run_id: runId,
    member_id: memberId,
    tool_name: "query_medicine_box",
    tool_call_id: "call-1",
    success: true,
    schema_valid: true,
  };
  const ragRef = {
    source_id: "source-rag-1",
    document_id: "doc-safety",
    chunk_id: "chunk-1",
    member_id: memberId,
    version: "v1",
    purpose: "refill_safety",
  };
  const safetyTrace = {
    member_id: memberId,
    flags: safetyFlags,
    blocked,
    requires_human_confirmation: waiting,
  };

  return {
    run: {
      id: runId,
      user_id: "user-demo",
      member_id: memberId,
      user_goal: "帮我整理续方材料",
      intent,
      status,
      final_answer: finalAnswer,
      need_human_confirmation: waiting,
      safety_result: { flags: safetyFlags, blocked },
      started_at: "2026-07-19T08:00:00Z",
      ended_at: "2026-07-19T08:00:01Z",
      duration_ms: 120,
      step_count: 4,
      task_success: true,
      groundedness_score: 1,
      hallucination_flag: false,
      human_confirmation_rate: confirmationPresent ? 1 : 0,
    },
    artifacts: {
      run_id: runId,
      task_id: "task-3b-demo",
      status,
      run_trace: {
        case_id: "runtime-task-3b-demo",
        run_id: runId,
        task_id: "task-3b-demo",
        user_id: "user-demo",
        member_id: memberId,
        intent: blocked ? "safety_check" : "refill",
        tool_calls: [{
          tool_name: "query_medicine_box",
          member_id: memberId,
          source_id: toolRef.source_id,
          source_name: "medicine_box_items",
          success: true,
          schema_valid: true,
          evidence_present: true,
        }],
        rag_traces: [{
          source_id: ragRef.source_id,
          source_name: "refill_sop",
          member_id: memberId,
          retrieved: true,
          schema_valid: true,
        }],
        safety_trace: safetyTrace,
        final_answer: {
          answer_id: "answer-1",
          content: finalAnswer,
          contains_factual_claims: true,
          waiting_for_user_confirmation: waiting,
          human_confirmation_present: confirmationPresent,
          action_status: blocked ? "none" : waiting ? "awaiting_confirmation" : "draft",
        },
        latency_ms: 120,
        schema_valid: true,
      },
      model_call_trace: {
        run_id: runId,
        task_id: "task-3b-demo",
        member_id: memberId,
        purpose: "final_answer",
        requested_provider: "deterministic",
        effective_provider: "deterministic",
        success: true,
        schema_valid: true,
        safety_passed: true,
        fallback_used: false,
        fallback_reason: null,
        latency_ms: 20,
        attempts: [{
          provider_name: "deterministic",
          model_name: "rule-based",
          success: true,
          schema_valid: true,
          safety_passed: true,
          safety_flags: [],
          latency_ms: 20,
          error_type: null,
        }],
      },
      run_summary: {
        run_id: runId,
        task_id: "task-3b-demo",
        member_id: memberId,
        intent: blocked ? "safety_check" : "refill",
        final_status: status,
        confirmed_facts: [],
        pending_confirmations: waiting ? ["create_local_draft"] : [],
        safety_flags: safetyFlags,
        tool_evidence_refs: [toolRef],
        rag_source_refs: [ragRef],
        final_answer_ref: "answer-1",
        evaluation_ref: "eval-1",
      },
      tool_evidence_refs: [toolRef],
      rag_source_refs: [ragRef],
      safety_trace: safetyTrace,
      evaluation_result: {
        case_id: "runtime-task-3b-demo",
        run_id: runId,
        task_success: true,
        tool_call_accuracy: 1,
        groundedness: 1,
        schema_valid: true,
        hallucination_detected: false,
        safety_recall: 1,
        human_confirmation_required: waiting,
        human_confirmation_present: confirmationPresent,
        context_isolation_passed: true,
        latency_ms: 120,
        failure_reasons: [],
      },
      resumed_from_run_id: confirmationPresent ? "run-3b-demo" : null,
      restored_source_ids: confirmationPresent ? [toolRef.source_id, ragRef.source_id] : [],
      external_action_status: "not_submitted",
    },
    idempotent_replay: false,
  };
}

export function makeToolCall(runId = "run-3b-demo"): AgentToolCall {
  return {
    id: "call-1",
    run_id: runId,
    agent_role: "RefillAgent",
    tool_name: "query_medicine_box",
    tool_input: { member_id: "member-father" },
    tool_output: { source_id: "source-tool-1" },
    latency_ms: 18,
    success: false,
    error_message: "inventory timeout",
    error_type: "timeout",
    fallback_action: "use_cached_summary",
    schema_valid: true,
  };
}
