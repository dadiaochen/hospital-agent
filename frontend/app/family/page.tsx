"use client";

import { AsyncContent } from "@/components/AsyncContent";
import { PageHeader } from "@/components/PageHeader";
import { StatusBadge } from "@/components/StatusBadge";
import { useMember } from "@/components/providers/MemberProvider";
import { api } from "@/lib/api/client";
import type {
  ConfirmationDraft,
  FamilyMember,
  HealthProfile,
  MedicineBoxItem,
  Prescription,
  PurchaseRecord,
} from "@/lib/api/types";
import { formatDate, formatDateTime, formatRelationship, formatStatus } from "@/lib/format";
import { useApiResource } from "@/lib/useApiResource";

function InfoRow({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div>
      <dt className="text-xs font-semibold text-[#71847f]">{label}</dt>
      <dd className="mt-1 text-[#334155]">{value}</dd>
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
          values.map((value, index) => (
            <span
              className={`rounded-full px-2.5 py-1 text-xs font-semibold ${colors[tone]}`}
              key={`${label}-${value}-${index}`}
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

type FamilyOverviewData = {
  profile: {
    member: FamilyMember;
    profile: HealthProfile;
  };
  medicineBox: MedicineBoxItem[];
  prescriptions: Prescription[];
  purchaseRecords: PurchaseRecord[];
  confirmationDrafts: ConfirmationDraft[];
};

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
  const overview = useApiResource<FamilyOverviewData>(
    memberId ? `family-overview:${memberId}` : null,
    async (signal) => {
      if (!memberId) throw new Error("请先选择家庭成员");

      const [profile, medicineBox, prescriptions, purchaseRecords, confirmationDrafts] =
        await Promise.all([
          api.getHealthProfile(memberId, signal),
          api.listMedicineBox(memberId, signal),
          api.listPrescriptions(memberId, signal),
          api.listPurchaseRecords(memberId, signal),
          api.listConfirmationDrafts(memberId, signal),
        ]);

      if (profile.member.id !== memberId) {
        throw new Error("当前成员信息与所选成员不一致");
      }

      return {
        profile,
        medicineBox,
        prescriptions,
        purchaseRecords,
        confirmationDrafts,
      };
    },
  );

  // The member key is part of the resource lifecycle. This extra render guard
  // prevents one frame of the previous member's data before the effect clears it.
  const scopedOverview =
    memberId && overview.data?.profile.member.id === memberId ? overview.data : null;
  const switchingMember = Boolean(memberId && overview.data && !scopedOverview);
  const loading =
    membersLoading || Boolean(memberId && (overview.loading || switchingMember));
  const error = membersError ?? overview.error;
  const retry = membersError
    ? reloadMembers
    : memberId
      ? overview.reload
      : undefined;

  return (
    <div className="grid gap-5">
      <PageHeader
        description="集中查看当前成员的健康档案、正在使用的药物、处方与购药记录。信息按成员分别加载，方便你准备下一次沟通。"
        eyebrow="家庭健康总览"
        title="把家人的健康记录放在一起"
      >
        <div className="flex flex-wrap items-center gap-2 text-sm font-semibold text-[#31534f]">
          <span className="rounded-full bg-[#eef6f3] px-3 py-1.5">
            已添加 {members.length} 位成员
          </span>
          {selectedMember ? (
            <span className="rounded-full border border-[#d7e5e0] bg-white px-3 py-1.5">
              当前：{selectedMember.name}
            </span>
          ) : null}
        </div>
      </PageHeader>

      <AsyncContent
        empty={!selectedMember || !scopedOverview}
        emptyDescription={
          selectedMember
            ? "当前成员还没有可展示的健康资料。"
            : "请先选择一位家庭成员，再查看健康总览。"
        }
        emptyTitle={selectedMember ? "暂时没有健康资料" : "还没有选择家庭成员"}
        error={error}
        loading={loading}
        onRetry={retry}
      >
        {selectedMember && scopedOverview ? (
          <div className="grid gap-5">
            <div className="grid gap-5 xl:grid-cols-[0.72fr_1.28fr]">
              <MemberCard member={selectedMember} />
              <HealthProfileCard profile={scopedOverview.profile.profile} />
            </div>

            <MedicationOverview
              currentMedications={scopedOverview.profile.profile.current_medications}
              medicineBox={scopedOverview.medicineBox}
            />

            <RecordGroups
              confirmationDrafts={scopedOverview.confirmationDrafts}
              prescriptions={scopedOverview.prescriptions}
              purchaseRecords={scopedOverview.purchaseRecords}
            />
          </div>
        ) : null}
      </AsyncContent>
    </div>
  );
}

function MemberCard({ member }: { member: FamilyMember }) {
  return (
    <section className="rounded-2xl border border-[#dbe7e3] bg-white p-5 shadow-sm">
      <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#0f766e]">当前成员</p>
      <div className="mt-4 flex items-center gap-3">
        <span
          aria-hidden="true"
          className="flex h-12 w-12 items-center justify-center rounded-full bg-[#e7f4f0] text-lg font-bold text-[#0f766e]"
        >
          {member.name.slice(0, 1)}
        </span>
        <div>
          <h3 className="text-2xl font-bold text-[#173c38]">{member.name}</h3>
          <p className="mt-1 text-sm text-[#64748b]">{readableRelationship(member.relationship)}</p>
        </div>
      </div>
      <dl className="mt-5 grid gap-4 text-sm sm:grid-cols-2 xl:grid-cols-1">
        <InfoRow label="性别" value={formatGender(member.gender)} />
        <InfoRow label="生日" value={formatDate(member.birthday)} />
        <InfoRow label="常住地" value={member.default_address ?? "未记录"} />
      </dl>
    </section>
  );
}

function HealthProfileCard({ profile }: { profile: HealthProfile }) {
  return (
    <section className="rounded-2xl border border-[#dbe7e3] bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#0f766e]">健康档案</p>
          <h3 className="mt-2 text-xl font-bold text-[#173c38]">健康信息与注意事项</h3>
        </div>
        <span className="text-xs text-[#71847f]">按当前成员展示</span>
      </div>
      <div className="mt-5 grid gap-5 sm:grid-cols-2">
        <TagGroup emptyText="未记录慢病信息" label="慢病记录" values={profile.chronic_disease_tags} />
        <TagGroup emptyText="未记录过敏史" label="过敏史" tone="danger" values={profile.allergies} />
        <TagGroup emptyText="暂无注意事项" label="注意事项" tone="warning" values={profile.safety_notes} />
        <div>
          <p className="text-xs font-semibold text-[#71847f]">健康备注</p>
          <p className="mt-2 text-sm leading-6 text-[#334155]">{profile.health_notes ?? "未记录"}</p>
        </div>
      </div>
    </section>
  );
}

function MedicationOverview({
  currentMedications,
  medicineBox,
}: {
  currentMedications: Array<Record<string, unknown>>;
  medicineBox: MedicineBoxItem[];
}) {
  return (
    <section className="rounded-2xl border border-[#dbe7e3] bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#0f766e]">用药情况</p>
          <h3 className="mt-2 text-xl font-bold text-[#173c38]">当前用药与药箱余量</h3>
        </div>
        <span className="text-xs text-[#71847f]">仅展示已有记录</span>
      </div>

      <div className="mt-5 grid gap-5 xl:grid-cols-2">
        <div>
          <SectionTitle count={currentMedications.length} title="档案中的当前用药" />
          {currentMedications.length > 0 ? (
            <div className="grid gap-3">
              {currentMedications.map((medication, index) => (
                <div
                  className="rounded-xl bg-[#f4f8f6] px-4 py-3 text-sm leading-6 text-[#475569]"
                  key={`current-medication-${index}`}
                >
                  {formatMedicineRecord(medication)}
                </div>
              ))}
            </div>
          ) : (
            <InlineEmpty text="暂未记录当前用药。" />
          )}
        </div>

        <div>
          <SectionTitle count={medicineBox.length} title="药箱余量" />
          {medicineBox.length > 0 ? (
            <div className="grid gap-3">
              {medicineBox.map((medicine) => (
                <MedicineBoxCard item={medicine} key={medicine.id} />
              ))}
            </div>
          ) : (
            <InlineEmpty text="当前成员还没有药箱库存记录。" />
          )}
        </div>
      </div>
    </section>
  );
}

function MedicineBoxCard({ item }: { item: MedicineBoxItem }) {
  return (
    <article className="rounded-xl border border-[#e1ebe7] bg-[#fbfdfc] p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h4 className="font-bold text-[#173c38]">{item.medicine_name}</h4>
          <p className="mt-1 text-xs text-[#71847f]">{item.specification ?? "规格未记录"}</p>
        </div>
        <StatusBadge tone={item.remaining_quantity > 0 ? "success" : "warning"}>
          剩余 {item.remaining_quantity}
        </StatusBadge>
      </div>
      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-xs text-[#64748b]">
        <span>用法：{item.dosage}</span>
        <span>频次：{item.frequency}</span>
        {item.estimated_remaining_days !== null ? (
          <span>预计还可用 {item.estimated_remaining_days} 天</span>
        ) : null}
      </div>
      {item.safety_note ? <p className="mt-3 text-xs leading-5 text-[#92400e]">注意：{item.safety_note}</p> : null}
    </article>
  );
}

function RecordGroups({
  confirmationDrafts,
  prescriptions,
  purchaseRecords,
}: {
  confirmationDrafts: ConfirmationDraft[];
  prescriptions: Prescription[];
  purchaseRecords: PurchaseRecord[];
}) {
  const followUpDrafts = confirmationDrafts.filter(
    (draft) => draft.draft_type === "refill_request" || draft.draft_type === "consultation_request",
  );
  const localDrafts = confirmationDrafts.filter(
    (draft) => draft.draft_type !== "refill_request" && draft.draft_type !== "consultation_request",
  );

  return (
    <section className="grid gap-5">
      <div>
        <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#0f766e]">记录分组</p>
        <h3 className="mt-2 text-xl font-bold text-[#173c38]">处方、复诊与购药记录</h3>
        <p className="mt-2 text-sm text-[#64748b]">
          按记录类型整理，方便你准备下一次沟通。
        </p>
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        <RecordGroup title="处方与复诊记录" count={prescriptions.length + followUpDrafts.length}>
          {prescriptions.map((prescription) => (
            <PrescriptionCard key={prescription.id} prescription={prescription} />
          ))}
          {followUpDrafts.map((draft) => (
            <LocalRecordCard key={`${draft.draft_type}:${draft.draft_id}`} draft={draft} />
          ))}
          {prescriptions.length === 0 && followUpDrafts.length === 0 ? (
            <InlineEmpty text="暂无处方或复诊准备记录。" />
          ) : null}
        </RecordGroup>

        <RecordGroup title="购药与本地记录" count={purchaseRecords.length + localDrafts.length}>
          {purchaseRecords.map((record) => (
            <PurchaseRecordCard key={record.id} record={record} />
          ))}
          {localDrafts.map((draft) => (
            <LocalRecordCard key={`${draft.draft_type}:${draft.draft_id}`} draft={draft} />
          ))}
          {purchaseRecords.length === 0 && localDrafts.length === 0 ? (
            <InlineEmpty text="暂无购药或本地准备记录。" />
          ) : null}
        </RecordGroup>
      </div>
    </section>
  );
}

function RecordGroup({
  title,
  count,
  children,
}: {
  title: string;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-[#dbe7e3] bg-white p-5 shadow-sm">
      <SectionTitle count={count} title={title} />
      <div className="grid gap-3">{children}</div>
    </section>
  );
}

function PrescriptionCard({ prescription }: { prescription: Prescription }) {
  return (
    <article className="rounded-xl border border-[#e1ebe7] bg-[#fbfdfc] p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h4 className="font-bold text-[#173c38]">{prescription.hospital_name ?? "医疗机构未记录"}</h4>
          <p className="mt-1 text-sm text-[#64748b]">
            {prescription.doctor_name ? `医生：${prescription.doctor_name}` : "医生信息未记录"}
          </p>
        </div>
        <StatusBadge tone={prescription.status === "expired" ? "danger" : "success"}>
          {readableStatus(prescription.status)}
        </StatusBadge>
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
        <InfoRow label="开具日期" value={formatDate(prescription.issued_at)} />
        <InfoRow label="有效期至" value={formatDate(prescription.expires_at)} />
        <InfoRow label="处方编号" value={prescription.prescription_no ?? "未记录"} />
        <InfoRow label="医生确认" value={prescription.doctor_confirmation_required ? "需要" : "未标记"} />
      </dl>
      <div className="mt-4 grid gap-2">
        {prescription.medicine_items.length > 0 ? (
          prescription.medicine_items.map((item, index) => (
            <p
              className="rounded-lg bg-[#f4f8f6] px-3 py-2 text-xs leading-5 text-[#475569]"
              key={`${prescription.id}-medicine-${index}`}
            >
              {formatMedicineRecord(item)}
            </p>
          ))
        ) : (
          <p className="text-xs text-[#71847f]">处方药品未记录。</p>
        )}
      </div>
      {prescription.safety_note ? <p className="mt-3 text-xs leading-5 text-[#92400e]">注意：{prescription.safety_note}</p> : null}
    </article>
  );
}

function PurchaseRecordCard({ record }: { record: PurchaseRecord }) {
  return (
    <article className="rounded-xl border border-[#e1ebe7] bg-[#fbfdfc] p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h4 className="font-bold text-[#173c38]">{record.medicine_name}</h4>
          <p className="mt-1 text-sm text-[#64748b]">{record.pharmacy_name ?? "药店未记录"}</p>
        </div>
        <span className="text-sm font-bold text-[#0f766e]">× {record.quantity}</span>
      </div>
      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-xs text-[#71847f]">
        <span>购买日期：{formatDate(record.purchased_at)}</span>
        <span>渠道：{readablePurchaseChannel(record.purchase_channel)}</span>
        {record.dosage ? <span>用法：{record.dosage}</span> : null}
        {record.frequency ? <span>频次：{record.frequency}</span> : null}
      </div>
    </article>
  );
}

function LocalRecordCard({ draft }: { draft: ConfirmationDraft }) {
  return (
    <article className="rounded-xl border border-[#e1ebe7] bg-[#fbfdfc] p-4">
      <div className="flex items-start justify-between gap-3">
        <h4 className="font-bold text-[#173c38]">{draftTitle(draft.draft_type)}</h4>
        <StatusBadge
          tone={
            draft.status === "confirmed"
              ? "success"
              : draft.status === "rejected"
                ? "danger"
                : "warning"
          }
        >
          {readableStatus(draft.status)}
        </StatusBadge>
      </div>
      <p className="mt-3 text-sm leading-6 text-[#475569]">{readableDraftSummary(draft)}</p>
      <p className="mt-3 text-xs text-[#71847f]">创建时间：{formatDateTime(draft.created_at)}</p>
    </article>
  );
}

function SectionTitle({ title, count }: { title: string; count: number }) {
  return (
    <div className="mb-3 flex items-center justify-between gap-3">
      <h3 className="text-base font-bold text-[#173c38]">{title}</h3>
      <span className="text-xs font-semibold text-[#71847f]">{count} 条</span>
    </div>
  );
}

function InlineEmpty({ text }: { text: string }) {
  return (
    <p className="rounded-xl border border-dashed border-[#cdded8] bg-[#fbfdfc] p-4 text-sm text-[#71847f]">
      {text}
    </p>
  );
}

function formatMedicineRecord(record: Record<string, unknown>): string {
  const medicineName = getRecordText(record, ["medicine_name", "medicineName", "name"]);
  const details = [
    getRecordText(record, ["specification", "规格"]),
    getRecordText(record, ["dosage", "用法"]),
    getRecordText(record, ["frequency", "频次"]),
    getRecordText(record, ["quantity", "数量"]),
  ].filter((value): value is string => Boolean(value));

  return [medicineName ?? "用药记录", ...details].join(" · ");
}

function getRecordText(record: Record<string, unknown>, keys: string[]): string | null {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value.trim()) return value.trim();
    if (typeof value === "number" || typeof value === "boolean") return String(value);
  }
  return null;
}

function readableRelationship(value: string): string {
  const labels: Record<string, string> = {
    self: "本人",
    father: "父亲",
    mother: "母亲",
    spouse: "配偶",
    child: "子女",
  };
  const formatted = labels[value] ?? formatRelationship(value);
  return formatted === value ? "家庭成员" : formatted;
}

function formatGender(value: string | null): string {
  if (value === "male") return "男";
  if (value === "female") return "女";
  return value ?? "未记录";
}

function readableStatus(value: string): string {
  const labels: Record<string, string> = {
    valid: "有效",
    active: "有效",
    expired: "已过期",
    draft: "待确认",
    confirmed: "已确认（本地）",
    rejected: "已拒绝",
    needs_confirmation: "待确认",
    completed: "已完成",
  };
  const formatted = labels[value] ?? formatStatus(value);
  return formatted === value ? "状态未记录" : formatted;
}

function readablePurchaseChannel(value: string | null): string {
  const labels: Record<string, string> = {
    online: "线上",
    offline: "线下",
    delivery: "配送",
    pickup: "自提",
    demo: "记录",
  };
  return value ? labels[value] ?? value : "未记录";
}

function draftTitle(type: ConfirmationDraft["draft_type"]): string {
  const labels: Record<ConfirmationDraft["draft_type"], string> = {
    refill_request: "续方准备",
    consultation_request: "复诊准备",
    pharmacy_option: "购药准备",
    reminder_create: "提醒准备",
  };
  return labels[type];
}

function readableDraftSummary(draft: ConfirmationDraft): string {
  const summary = draft.summary?.trim();
  if (!summary) return "已整理一条准备记录。";

  if (/local refill draft|refill draft for run|续方申请草稿/i.test(summary)) {
    return "已整理续方准备材料，等待你的确认。";
  }
  if (/local reminder draft|reminder draft for run|提醒草稿/i.test(summary)) {
    return "已整理用药提醒准备内容，等待你的确认。";
  }
  if (/local pharmacy draft|pharmacy draft for run|购药草稿/i.test(summary)) {
    return "已整理购药准备内容，等待你的确认。";
  }
  if (/run[_\s-]?id|task[_\s-]?id|source[_\s-]?id|trace|tool[_\s-]?name/i.test(summary)) {
    return "已整理相关准备内容，等待你的确认。";
  }
  return summary;
}
