"use client";

import { AsyncContent } from "@/components/AsyncContent";
import { PageHeader } from "@/components/PageHeader";
import { useMember } from "@/components/providers/MemberProvider";
import { StatusBadge } from "@/components/StatusBadge";
import { api } from "@/lib/api/client";
import type { ConfirmationDraft, Prescription } from "@/lib/api/types";
import { describeRecord, formatDate, formatStatus } from "@/lib/format";
import { useApiResource } from "@/lib/useApiResource";

type RefillPageData = {
  prescriptions: Prescription[];
  drafts: ConfirmationDraft[];
};

export default function RefillPlansPage() {
  const {
    selectedMemberId,
    selectedMember,
    loading: membersLoading,
    error: membersError,
    reload: reloadMembers,
  } = useMember();
  const memberId = selectedMemberId;
  const resource = useApiResource<RefillPageData>(
    memberId ? `refill:${memberId}` : null,
    async (signal) => {
      if (!memberId) throw new Error("请先选择家庭成员");
      const [prescriptions, drafts] = await Promise.all([
        api.listPrescriptions(memberId, signal),
        api.listConfirmationDrafts(memberId, signal),
      ]);
      return {
        prescriptions,
        drafts: drafts.filter(
          (draft) =>
            draft.draft_type === "refill_request" ||
            draft.draft_type === "consultation_request",
        ),
      };
    },
  );
  const empty =
    (resource.data?.prescriptions.length ?? 0) === 0 &&
    (resource.data?.drafts.length ?? 0) === 0;

  return (
    <div className="grid gap-5">
      <PageHeader
        description="处方是医生记录，确认草稿是系统整理的本地流程状态。页面只展示和解释这些数据，不提交医院、不自动开方。"
        eyebrow="Refill & Consultation"
        title="续方与复诊材料"
      >
        {selectedMember ? (
          <span className="text-sm font-semibold text-[#31534f]">
            当前：{selectedMember.name}
          </span>
        ) : null}
      </PageHeader>

      <AsyncContent
        empty={empty}
        emptyDescription="当前成员没有历史处方，也没有续方或复诊确认草稿。"
        emptyTitle="暂无续方与复诊材料"
        error={membersError ?? resource.error}
        loading={membersLoading || (Boolean(memberId) && resource.loading)}
        onRetry={membersError ? reloadMembers : resource.reload}
      >
        <div className="grid gap-5">
          <section>
            <SectionTitle
              count={resource.data?.prescriptions.length ?? 0}
              title="历史处方"
            />
            {resource.data?.prescriptions.length ? (
              <div className="grid gap-4 xl:grid-cols-2">
                {resource.data.prescriptions.map((prescription) => (
                  <article
                    className="rounded-2xl border border-[#dbe7e3] bg-white p-5 shadow-sm"
                    key={prescription.id}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <h4 className="font-bold text-[#173c38]">
                          {prescription.hospital_name ?? "医院未记录"}
                        </h4>
                        <p className="mt-1 text-xs text-[#71847f]">
                          处方号：{prescription.prescription_no ?? "未记录"}
                        </p>
                      </div>
                      <StatusBadge
                        tone={prescription.status === "active" ? "success" : "neutral"}
                      >
                        {formatStatus(prescription.status)}
                      </StatusBadge>
                    </div>
                    <dl className="mt-4 grid grid-cols-2 gap-4 text-sm">
                      <SmallField
                        label="医生"
                        value={prescription.doctor_name ?? "未记录"}
                      />
                      <SmallField label="开具日期" value={formatDate(prescription.issued_at)} />
                      <SmallField label="有效期至" value={formatDate(prescription.expires_at)} />
                      <SmallField
                        label="医生确认"
                        value={prescription.doctor_confirmation_required ? "需要" : "未标记"}
                      />
                    </dl>
                    <div className="mt-4 grid gap-2">
                      {prescription.medicine_items.map((item, index) => (
                        <p
                          className="rounded-xl bg-[#f4f8f6] px-3 py-2 text-xs leading-5 text-[#475569]"
                          key={`${prescription.id}-medicine-${index}`}
                        >
                          {describeRecord(item)}
                        </p>
                      ))}
                    </div>
                    {prescription.safety_note ? (
                      <p className="mt-4 text-sm leading-6 text-[#92400e]">
                        安全备注：{prescription.safety_note}
                      </p>
                    ) : null}
                  </article>
                ))}
              </div>
            ) : (
              <InlineEmpty text="当前成员没有历史处方。" />
            )}
          </section>

          <section>
            <SectionTitle
              count={resource.data?.drafts.length ?? 0}
              title="待确认流程草稿"
            />
            {resource.data?.drafts.length ? (
              <div className="grid gap-4 xl:grid-cols-2">
                {resource.data.drafts.map((draft) => (
                  <article
                    className="rounded-2xl border border-[#dbe7e3] bg-white p-5 shadow-sm"
                    key={`${draft.draft_type}:${draft.draft_id}`}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <h4 className="font-bold text-[#173c38]">
                        {draft.draft_type === "refill_request" ? "续方草稿" : "复诊草稿"}
                      </h4>
                      <StatusBadge
                        tone={
                          draft.status === "confirmed"
                            ? "success"
                            : draft.status === "rejected"
                              ? "danger"
                              : "warning"
                        }
                      >
                        {formatStatus(draft.status)}
                      </StatusBadge>
                    </div>
                    <p className="mt-3 text-sm leading-6 text-[#475569]">
                      {draft.summary ?? "未填写摘要"}
                    </p>
                    <div className="mt-4 rounded-xl bg-[#fff8e7] px-4 py-3 text-xs leading-5 text-[#854d0e]">
                      外部动作状态：未提交。确认只记录本地状态，不代表医院已受理。
                    </div>
                    <p className="mt-3 break-all font-mono text-[11px] text-[#94a3b8]">
                      source_id: {draft.source_id}
                    </p>
                  </article>
                ))}
              </div>
            ) : (
              <InlineEmpty text="当前成员没有续方或复诊确认草稿。" />
            )}
          </section>
        </div>
      </AsyncContent>
    </div>
  );
}

function SectionTitle({ title, count }: { title: string; count: number }) {
  return (
    <div className="mb-3 flex items-center justify-between">
      <h3 className="text-lg font-bold text-[#173c38]">{title}</h3>
      <span className="text-xs font-semibold text-[#71847f]">{count} 条</span>
    </div>
  );
}

function SmallField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-semibold text-[#71847f]">{label}</dt>
      <dd className="mt-1 text-[#334155]">{value}</dd>
    </div>
  );
}

function InlineEmpty({ text }: { text: string }) {
  return (
    <p className="rounded-2xl border border-dashed border-[#cdded8] bg-white p-5 text-sm text-[#71847f]">
      {text}
    </p>
  );
}
