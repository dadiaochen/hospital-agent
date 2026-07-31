"use client";

import { AsyncContent } from "@/components/AsyncContent";
import { PageHeader } from "@/components/PageHeader";
import { useMember } from "@/components/providers/MemberProvider";
import { StatusBadge } from "@/components/StatusBadge";
import { api } from "@/lib/api/client";
import { describeRecord, formatDateTime, formatStatus } from "@/lib/format";
import { useApiResource } from "@/lib/useApiResource";

export default function RemindersPage() {
  const {
    selectedMemberId,
    selectedMember,
    loading: membersLoading,
    error: membersError,
    reload: reloadMembers,
  } = useMember();
  const memberId = selectedMemberId;
  const reminders = useApiResource(
    memberId ? `reminders:${memberId}` : null,
    async (signal) => {
      if (!memberId) throw new Error("请先选择家庭成员");
      const drafts = await api.listConfirmationDrafts(memberId, signal);
      return drafts.filter((draft) => draft.draft_type === "reminder_create");
    },
  );

  return (
    <div className="grid gap-5">
      <PageHeader
        description="提醒页面只读取 reminder_create 类型的本地草稿。未确认草稿不会被描述成已创建提醒，项目当前也没有接入短信或推送服务。"
        eyebrow="Reminder Drafts"
        title="用药与复诊提醒"
      >
        {selectedMember ? (
          <span className="text-sm font-semibold text-[#31534f]">
            当前：{selectedMember.name}
          </span>
        ) : null}
      </PageHeader>

      <AsyncContent
        empty={(reminders.data?.length ?? 0) === 0}
        emptyDescription="当前成员没有提醒草稿。后续可由 Agent 生成草稿，再由用户确认。"
        emptyTitle="暂无提醒草稿"
        error={membersError ?? reminders.error}
        loading={membersLoading || (Boolean(memberId) && reminders.loading)}
        onRetry={membersError ? reloadMembers : reminders.reload}
      >
        <div className="grid gap-4 xl:grid-cols-2">
          {reminders.data?.map((reminder) => (
            <article
              className="rounded-2xl border border-[#dbe7e3] bg-white p-5 shadow-sm"
              key={reminder.draft_id}
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-xs font-bold uppercase tracking-[0.14em] text-[#0f766e]">
                    Reminder Draft
                  </p>
                  <h3 className="mt-2 font-bold text-[#173c38]">
                    {reminder.summary ?? "未命名提醒草稿"}
                  </h3>
                </div>
                <StatusBadge
                  tone={
                    reminder.status === "confirmed"
                      ? "success"
                      : reminder.status === "rejected"
                        ? "danger"
                        : "warning"
                  }
                >
                  {formatStatus(reminder.status)}
                </StatusBadge>
              </div>

              <dl className="mt-5 grid grid-cols-2 gap-4 text-sm">
                <ReminderField
                  label="需要人工确认"
                  value={reminder.need_human_confirmation ? "是" : "否"}
                />
                <ReminderField
                  label="本地确认已记录"
                  value={reminder.local_confirmation_recorded ? "是" : "否"}
                />
                <ReminderField
                  label="创建时间"
                  value={formatDateTime(reminder.created_at)}
                />
                <ReminderField label="外部状态" value="未提交" />
              </dl>

              <div className="mt-4 rounded-xl bg-[#f4f8f6] px-4 py-3 text-sm leading-6 text-[#475569]">
                {describeRecord(reminder.content)}
              </div>
              <p className="mt-3 break-all font-mono text-[11px] text-[#94a3b8]">
                source_id: {reminder.source_id}
              </p>
            </article>
          ))}
        </div>
      </AsyncContent>
    </div>
  );
}

function ReminderField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-semibold text-[#71847f]">{label}</dt>
      <dd className="mt-1 text-[#334155]">{value}</dd>
    </div>
  );
}
