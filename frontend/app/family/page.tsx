"use client";

import { AsyncContent } from "@/components/AsyncContent";
import { PageHeader } from "@/components/PageHeader";
import { useMember } from "@/components/providers/MemberProvider";
import { api } from "@/lib/api/client";
import { describeRecord, formatDate, formatRelationship } from "@/lib/format";
import { useApiResource } from "@/lib/useApiResource";

export default function FamilyPage() {
  const {
    selectedMemberId,
    selectedMember,
    members,
    loading: membersLoading,
    error: membersError,
    reload: reloadMembers,
  } = useMember();
  const memberId = selectedMemberId;
  const profile = useApiResource(
    memberId ? `health-profile:${memberId}` : null,
    (signal) => {
      if (!memberId) throw new Error("请先选择家庭成员");
      return api.getHealthProfile(memberId, signal);
    },
  );

  return (
    <div className="grid gap-5">
      <PageHeader
        description="查看当前家庭成员的基础信息、慢病标签、过敏史和安全备注。切换成员后，健康档案会重新从 API 加载。"
        eyebrow="Family Profile"
        title="家庭成员与健康档案"
      >
        <span className="rounded-full bg-[#eef6f3] px-3 py-1.5 text-sm font-semibold text-[#31534f]">
          共 {members.length} 位成员
        </span>
      </PageHeader>

      <AsyncContent
        empty={!selectedMember || !profile.data}
        emptyDescription="请先运行 seed，确保 demo user 下存在家庭成员和健康档案。"
        emptyTitle="没有可展示的健康档案"
        error={membersError ?? profile.error}
        loading={membersLoading || (Boolean(memberId) && profile.loading)}
        onRetry={membersError ? reloadMembers : profile.reload}
      >
        {selectedMember && profile.data ? (
          <div className="grid gap-4 xl:grid-cols-[0.72fr_1.28fr]">
            <section className="rounded-2xl border border-[#dbe7e3] bg-white p-5 shadow-sm">
              <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#0f766e]">
                当前成员
              </p>
              <h3 className="mt-3 text-2xl font-bold text-[#173c38]">
                {selectedMember.name}
              </h3>
              <dl className="mt-5 grid gap-4 text-sm">
                <InfoRow
                  label="关系"
                  value={formatRelationship(selectedMember.relationship)}
                />
                <InfoRow label="性别" value={selectedMember.gender ?? "未记录"} />
                <InfoRow label="生日" value={formatDate(selectedMember.birthday)} />
                <InfoRow
                  label="默认地址"
                  value={selectedMember.default_address ?? "未记录"}
                />
                <InfoRow label="member_id" value={selectedMember.id} mono />
              </dl>
            </section>

            <div className="grid gap-4">
              <section className="rounded-2xl border border-[#dbe7e3] bg-white p-5 shadow-sm">
                <h3 className="font-bold text-[#173c38]">健康标签与安全信息</h3>
                <div className="mt-4 grid gap-4 sm:grid-cols-2">
                  <TagGroup
                    emptyText="未记录慢病标签"
                    label="慢病标签"
                    values={profile.data.profile.chronic_disease_tags}
                  />
                  <TagGroup
                    emptyText="未记录过敏史"
                    label="过敏史"
                    tone="danger"
                    values={profile.data.profile.allergies}
                  />
                  <TagGroup
                    emptyText="暂无安全备注"
                    label="安全备注"
                    tone="warning"
                    values={profile.data.profile.safety_notes}
                  />
                  <div>
                    <p className="text-xs font-semibold text-[#71847f]">健康备注</p>
                    <p className="mt-2 text-sm leading-6 text-[#334155]">
                      {profile.data.profile.health_notes ?? "未记录"}
                    </p>
                  </div>
                </div>
              </section>

              <section className="rounded-2xl border border-[#dbe7e3] bg-white p-5 shadow-sm">
                <h3 className="font-bold text-[#173c38]">当前用药（档案记录）</h3>
                <div className="mt-4 grid gap-3">
                  {profile.data.profile.current_medications.length > 0 ? (
                    profile.data.profile.current_medications.map((medication, index) => (
                      <div
                        className="rounded-xl bg-[#f4f8f6] px-4 py-3 text-sm leading-6 text-[#475569]"
                        key={`${selectedMember.id}-medication-${index}`}
                      >
                        {describeRecord(medication)}
                      </div>
                    ))
                  ) : (
                    <p className="text-sm text-[#71847f]">未记录当前用药。</p>
                  )}
                </div>
              </section>
            </div>
          </div>
        ) : null}
      </AsyncContent>
    </div>
  );
}

function InfoRow({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <dt className="text-xs font-semibold text-[#71847f]">{label}</dt>
      <dd className={`mt-1 text-[#334155] ${mono ? "break-all font-mono text-xs" : ""}`}>
        {value}
      </dd>
    </div>
  );
}

function TagGroup({
  label,
  values,
  emptyText,
  tone = "default",
}: {
  label: string;
  values: string[];
  emptyText: string;
  tone?: "default" | "warning" | "danger";
}) {
  const colors = {
    default: "bg-[#e4f4ef] text-[#0f665f]",
    warning: "bg-[#fff3cd] text-[#854d0e]",
    danger: "bg-[#fee2e2] text-[#991b1b]",
  };
  return (
    <div>
      <p className="text-xs font-semibold text-[#71847f]">{label}</p>
      <div className="mt-2 flex flex-wrap gap-2">
        {values.length > 0 ? (
          values.map((value) => (
            <span
              className={`rounded-full px-2.5 py-1 text-xs font-semibold ${colors[tone]}`}
              key={value}
            >
              {value}
            </span>
          ))
        ) : (
          <span className="text-sm text-[#94a3b8]">{emptyText}</span>
        )}
      </div>
    </div>
  );
}
