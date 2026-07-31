"use client";

import { AsyncContent } from "@/components/AsyncContent";
import { PageHeader } from "@/components/PageHeader";
import { useMember } from "@/components/providers/MemberProvider";
import { StatusBadge } from "@/components/StatusBadge";
import { api } from "@/lib/api/client";
import { formatDate } from "@/lib/format";
import { useApiResource } from "@/lib/useApiResource";

export default function MedicineBoxPage() {
  const {
    selectedMemberId,
    selectedMember,
    loading: membersLoading,
    error: membersError,
    reload: reloadMembers,
  } = useMember();
  const memberId = selectedMemberId;
  const box = useApiResource(memberId ? `medicine-box:${memberId}` : null, (signal) => {
    if (!memberId) throw new Error("请先选择家庭成员");
    return api.listMedicineBox(memberId, signal);
  });

  return (
    <div className="grid gap-5">
      <PageHeader
        description="库存来自当前成员的 medicine-box API。页面展示剩余数量、预计可用天数和安全备注，不根据库存自行修改剂量。"
        eyebrow="Medicine Box"
        title="家庭药箱"
      >
        {selectedMember ? (
          <span className="text-sm font-semibold text-[#31534f]">
            {selectedMember.name}的药箱
          </span>
        ) : null}
      </PageHeader>

      <AsyncContent
        empty={(box.data?.length ?? 0) === 0}
        emptyDescription="当前成员没有药箱记录；切换成员或检查 seed 数据。"
        emptyTitle="药箱暂时是空的"
        error={membersError ?? box.error}
        loading={membersLoading || (Boolean(memberId) && box.loading)}
        onRetry={membersError ? reloadMembers : box.reload}
      >
        <div className="grid gap-4 xl:grid-cols-2">
          {box.data?.map((item) => {
            const remainingRatio =
              item.total_quantity > 0
                ? Math.max(
                    0,
                    Math.min(100, (item.remaining_quantity / item.total_quantity) * 100),
                  )
                : 0;
            const lowStock =
              item.estimated_remaining_days !== null &&
              item.estimated_remaining_days <= 7;
            return (
              <article
                className="rounded-2xl border border-[#dbe7e3] bg-white p-5 shadow-sm"
                key={item.id}
              >
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h3 className="text-lg font-bold text-[#173c38]">
                      {item.medicine_name}
                    </h3>
                    <p className="mt-1 text-sm text-[#71847f]">
                      {item.specification ?? "规格未记录"}
                    </p>
                  </div>
                  <StatusBadge tone={lowStock ? "warning" : "success"}>
                    {lowStock ? "库存偏低" : "库存正常"}
                  </StatusBadge>
                </div>

                <div className="mt-5">
                  <div className="flex items-end justify-between gap-3 text-sm">
                    <span className="text-[#64748b]">剩余数量</span>
                    <strong className="text-xl text-[#173c38]">
                      {item.remaining_quantity}
                      <span className="ml-1 text-xs font-medium text-[#71847f]">
                        / {item.total_quantity}
                      </span>
                    </strong>
                  </div>
                  <div className="mt-2 h-2 overflow-hidden rounded-full bg-[#edf2f0]">
                    <div
                      className={`h-full rounded-full ${lowStock ? "bg-[#d97706]" : "bg-[#0f766e]"}`}
                      style={{ width: `${remainingRatio}%` }}
                    />
                  </div>
                </div>

                <dl className="mt-5 grid grid-cols-2 gap-4 text-sm">
                  <BoxField label="用法" value={item.dosage} />
                  <BoxField label="频次" value={item.frequency} />
                  <BoxField
                    label="预计剩余"
                    value={
                      item.estimated_remaining_days === null
                        ? "无法估算"
                        : `${item.estimated_remaining_days} 天`
                    }
                  />
                  <BoxField label="购入日期" value={formatDate(item.purchased_at)} />
                </dl>

                {item.safety_note ? (
                  <p className="mt-5 rounded-xl bg-[#fff8e7] px-4 py-3 text-sm leading-6 text-[#854d0e]">
                    安全备注：{item.safety_note}
                  </p>
                ) : null}
              </article>
            );
          })}
        </div>
      </AsyncContent>
    </div>
  );
}

function BoxField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-semibold text-[#71847f]">{label}</dt>
      <dd className="mt-1 text-[#334155]">{value}</dd>
    </div>
  );
}
