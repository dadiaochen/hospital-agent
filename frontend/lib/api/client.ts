import type {
  AgentRun,
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
  knowledgeSearch: (queryText: string, category: string) => {
    const query = new URLSearchParams({ q: queryText.trim() });
    if (category.trim()) query.set("category", category.trim());
    return `/api/knowledge/search?${query.toString()}`;
  },
};

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    cache: "no-store",
    headers: { Accept: "application/json" },
    signal,
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
