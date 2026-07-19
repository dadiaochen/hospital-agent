import type {
  AgentRun,
  AgentRunArtifacts,
  AgentRunContinueRequest,
  AgentRunCreateRequest,
  AgentRunExecution,
  AgentToolCall,
  ApiErrorBody,
  ConfirmationDraft,
  FamilyMember,
  FamilyMemberHealthProfile,
  KnowledgeSearchItem,
  ListResponse,
  MedicineBoxItem,
  PharmacyInventoryItem,
  Prescription,
  PurchaseRecord,
} from "@/lib/api/types";

const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

export class ApiClientError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
  ) {
    super(message);
    this.name = "ApiClientError";
  }
}

export const apiPaths = {
  familyMembers: "/api/family-members",
  healthProfile: (memberId: string) =>
    `/api/family-members/${encodeURIComponent(memberId)}/health-profile`,
  medicineBox: (memberId: string) =>
    `/api/family-members/${encodeURIComponent(memberId)}/medicine-box`,
  prescriptions: (memberId: string) =>
    `/api/family-members/${encodeURIComponent(memberId)}/prescriptions`,
  purchaseRecords: (memberId: string) =>
    `/api/family-members/${encodeURIComponent(memberId)}/purchase-records`,
  confirmationDrafts: (memberId: string) =>
    `/api/confirmation-drafts?member_id=${encodeURIComponent(memberId)}`,
  pharmacyInventory: (medicineName: string, city: string) => {
    const query = new URLSearchParams();
    if (medicineName.trim()) query.set("medicine_name", medicineName.trim());
    if (city.trim()) query.set("city", city.trim());
    return `/api/pharmacy-inventory?${query.toString()}`;
  },
  agentRuns: (memberId: string) =>
    `/api/agent-runs?member_id=${encodeURIComponent(memberId)}`,
  agentRunsRoot: "/api/agent-runs",
  agentRun: (runId: string) =>
    `/api/agent-runs/${encodeURIComponent(runId)}`,
  agentRunToolCalls: (runId: string) =>
    `/api/agent-runs/${encodeURIComponent(runId)}/tool-calls`,
  agentRunArtifacts: (runId: string) =>
    `/api/agent-runs/${encodeURIComponent(runId)}/artifacts`,
  continueAgentRun: (runId: string) =>
    `/api/agent-runs/${encodeURIComponent(runId)}/continue`,
  knowledgeSearch: (queryText: string, category: string) => {
    const query = new URLSearchParams({ q: queryText.trim() });
    if (category.trim()) query.set("category", category.trim());
    return `/api/knowledge/search?${query.toString()}`;
  },
};

async function requestJson<T>(
  path: string,
  options: { method?: "GET" | "POST"; body?: unknown; signal?: AbortSignal } = {},
): Promise<T> {
  const method = options.method ?? "GET";
  const response = await fetch(`${API_BASE_URL}${path}`, {
    cache: "no-store",
    method,
    headers: {
      Accept: "application/json",
      ...(method === "POST" ? { "Content-Type": "application/json" } : {}),
    },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: options.signal,
  });

  if (!response.ok) {
    let body: ApiErrorBody = {};
    try {
      body = (await response.json()) as ApiErrorBody;
    } catch {
      // Some infrastructure errors return HTML or an empty body.
    }
    throw new ApiClientError(
      body.error?.message ?? `请求失败（HTTP ${response.status}）`,
      response.status,
      body.error?.code ?? "http_error",
    );
  }

  return (await response.json()) as T;
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  return requestJson<T>(path, { signal });
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  return requestJson<T>(path, { method: "POST", body });
}

export function assertMemberScoped<T extends { member_id: string | null }>(
  records: T[],
  memberId: string,
  resourceName: string,
): T[] {
  const crossMemberRecord = records.find(
    (record) => record.member_id !== memberId,
  );
  if (crossMemberRecord) {
    throw new ApiClientError(
      `${resourceName} 返回了其他家庭成员的数据，页面已停止展示`,
      409,
      "context_isolation_failed",
    );
  }
  return records;
}

export function assertAgentArtifactsScoped(
  artifacts: AgentRunArtifacts,
  memberId: string,
): AgentRunArtifacts {
  const scopedMemberIds = [
    artifacts.run_trace.member_id,
    artifacts.run_summary.member_id,
    artifacts.safety_trace.member_id,
    artifacts.model_call_trace.member_id,
    ...artifacts.run_trace.tool_calls.map((call) => call.member_id),
    ...artifacts.run_trace.rag_traces.flatMap((reference) =>
      reference.member_id === null ? [] : [reference.member_id],
    ),
    ...artifacts.tool_evidence_refs.map((reference) => reference.member_id),
    ...artifacts.rag_source_refs.flatMap((reference) =>
      reference.member_id === null ? [] : [reference.member_id],
    ),
    ...artifacts.run_summary.tool_evidence_refs.map(
      (reference) => reference.member_id,
    ),
    ...artifacts.run_summary.rag_source_refs.flatMap((reference) =>
      reference.member_id === null ? [] : [reference.member_id],
    ),
  ];
  if (scopedMemberIds.some((scopedMemberId) => scopedMemberId !== memberId)) {
    throw new ApiClientError(
      "Agent 冻结产物包含其他家庭成员数据，页面已停止展示",
      409,
      "context_isolation_failed",
    );
  }
  const runIds = [
    artifacts.run_id,
    artifacts.run_trace.run_id,
    artifacts.run_summary.run_id,
    artifacts.model_call_trace.run_id,
    artifacts.evaluation_result.run_id,
  ];
  const taskIds = [
    artifacts.task_id,
    artifacts.run_trace.task_id,
    artifacts.run_summary.task_id,
    artifacts.model_call_trace.task_id,
  ];
  if (new Set(runIds).size !== 1 || new Set(taskIds).size !== 1) {
    throw new ApiClientError(
      "Agent 冻结产物的 run/task 引用不一致，页面已停止展示",
      409,
      "trace_contract_failed",
    );
  }
  return artifacts;
}

export const api = {
  async listFamilyMembers(signal?: AbortSignal): Promise<FamilyMember[]> {
    return (await getJson<ListResponse<FamilyMember>>(apiPaths.familyMembers, signal))
      .items;
  },

  async getHealthProfile(
    memberId: string,
    signal?: AbortSignal,
  ): Promise<FamilyMemberHealthProfile> {
    const result = await getJson<FamilyMemberHealthProfile>(
      apiPaths.healthProfile(memberId),
      signal,
    );
    assertMemberScoped([result.profile], memberId, "健康档案");
    if (result.member.id !== memberId) {
      throw new ApiClientError(
        "健康档案成员与当前选择不一致",
        409,
        "context_isolation_failed",
      );
    }
    return result;
  },

  async listMedicineBox(
    memberId: string,
    signal?: AbortSignal,
  ): Promise<MedicineBoxItem[]> {
    const result = await getJson<ListResponse<MedicineBoxItem>>(
      apiPaths.medicineBox(memberId),
      signal,
    );
    return assertMemberScoped(result.items, memberId, "家庭药箱");
  },

  async listPrescriptions(
    memberId: string,
    signal?: AbortSignal,
  ): Promise<Prescription[]> {
    const result = await getJson<ListResponse<Prescription>>(
      apiPaths.prescriptions(memberId),
      signal,
    );
    return assertMemberScoped(result.items, memberId, "处方记录");
  },

  async listPurchaseRecords(
    memberId: string,
    signal?: AbortSignal,
  ): Promise<PurchaseRecord[]> {
    const result = await getJson<ListResponse<PurchaseRecord>>(
      apiPaths.purchaseRecords(memberId),
      signal,
    );
    return assertMemberScoped(result.items, memberId, "购药记录");
  },

  async listConfirmationDrafts(
    memberId: string,
    signal?: AbortSignal,
  ): Promise<ConfirmationDraft[]> {
    const result = await getJson<ListResponse<ConfirmationDraft>>(
      apiPaths.confirmationDrafts(memberId),
      signal,
    );
    return assertMemberScoped(result.items, memberId, "确认草稿");
  },

  async searchPharmacyInventory(
    medicineName: string,
    city: string,
    signal?: AbortSignal,
  ): Promise<PharmacyInventoryItem[]> {
    if (!medicineName.trim() && !city.trim()) {
      throw new ApiClientError(
        "请至少输入药品名或城市",
        422,
        "validation_error",
      );
    }
    return (
      await getJson<ListResponse<PharmacyInventoryItem>>(
        apiPaths.pharmacyInventory(medicineName, city),
        signal,
      )
    ).items;
  },

  async listAgentRuns(
    memberId: string,
    signal?: AbortSignal,
  ): Promise<AgentRun[]> {
    const result = await getJson<ListResponse<AgentRun>>(
      apiPaths.agentRuns(memberId),
      signal,
    );
    return assertMemberScoped(result.items, memberId, "Agent 执行记录");
  },

  async createAgentRun(request: AgentRunCreateRequest): Promise<AgentRunExecution> {
    const result = await postJson<AgentRunExecution>(apiPaths.agentRunsRoot, request);
    assertMemberScoped([result.run], request.member_id, "Agent 执行结果");
    assertAgentArtifactsScoped(result.artifacts, request.member_id);
    return result;
  },

  async getAgentRun(
    runId: string,
    memberId: string,
    signal?: AbortSignal,
  ): Promise<AgentRun> {
    const result = await getJson<AgentRun>(apiPaths.agentRun(runId), signal);
    return assertMemberScoped([result], memberId, "Agent 执行记录")[0];
  },

  async listAgentToolCalls(
    runId: string,
    signal?: AbortSignal,
  ): Promise<AgentToolCall[]> {
    return (
      await getJson<ListResponse<AgentToolCall>>(
        apiPaths.agentRunToolCalls(runId),
        signal,
      )
    ).items;
  },

  async getAgentRunArtifacts(
    runId: string,
    memberId: string,
    signal?: AbortSignal,
  ): Promise<AgentRunArtifacts> {
    const result = await getJson<AgentRunArtifacts>(
      apiPaths.agentRunArtifacts(runId),
      signal,
    );
    return assertAgentArtifactsScoped(result, memberId);
  },

  async continueAgentRun(
    runId: string,
    memberId: string,
    request: AgentRunContinueRequest,
  ): Promise<AgentRunExecution> {
    const result = await postJson<AgentRunExecution>(
      apiPaths.continueAgentRun(runId),
      request,
    );
    assertMemberScoped([result.run], memberId, "Agent 续跑结果");
    assertAgentArtifactsScoped(result.artifacts, memberId);
    return result;
  },

  async searchKnowledge(
    queryText: string,
    category: string,
    signal?: AbortSignal,
  ): Promise<KnowledgeSearchItem[]> {
    if (!queryText.trim()) {
      throw new ApiClientError(
        "请输入检索关键词",
        422,
        "validation_error",
      );
    }
    return (
      await getJson<ListResponse<KnowledgeSearchItem>>(
        apiPaths.knowledgeSearch(queryText, category),
        signal,
      )
    ).items;
  },
};
