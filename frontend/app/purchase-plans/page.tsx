"use client";

import { FormEvent, useState } from "react";

import { AsyncContent } from "@/components/AsyncContent";
import { PageHeader } from "@/components/PageHeader";
import { useMember } from "@/components/providers/MemberProvider";
import { StatusBadge } from "@/components/StatusBadge";
import { api } from "@/lib/api/client";
import type { PharmacyInventoryItem } from "@/lib/api/types";
import { formatDate } from "@/lib/format";
import { useApiResource } from "@/lib/useApiResource";

export default function PurchasePlansPage() {
  const {
    selectedMemberId,
    selectedMember,
    loading: membersLoading,
    error: membersError,
    reload: reloadMembers,
  } = useMember();
  const memberId = selectedMemberId;
  const purchaseRecords = useApiResource(
    memberId ? `purchase-records:${memberId}` : null,
    (signal) => {
      if (!memberId) throw new Error("请先选择家庭成员");
      return api.listPurchaseRecords(memberId, signal);
    },
  );
  const [medicineName, setMedicineName] = useState("");
  const [city, setCity] = useState("");
  const [inventory, setInventory] = useState<PharmacyInventoryItem[] | null>(null);
  const [inventoryError, setInventoryError] = useState<string | null>(null);
  const [inventoryLoading, setInventoryLoading] = useState(false);

  async function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setInventoryLoading(true);
    setInventoryError(null);
    try {
      setInventory(await api.searchPharmacyInventory(medicineName, city));
    } catch (error) {
      setInventory(null);
      setInventoryError(
        error instanceof Error ? error.message : "库存查询失败，请稍后重试",
      );
    } finally {
      setInventoryLoading(false);
    }
  }

  return (
    <div className="grid gap-5">
      <PageHeader
        description="左侧历史记录按当前成员隔离；药店库存是公开候选信息，需要主动输入药品名或城市查询。页面不提供下单能力。"
        eyebrow="Purchase Information"
        title="购药记录与库存候选"
      />

      <div className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
        <section>
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-lg font-bold text-[#173c38]">历史购药记录</h3>
            <span className="text-xs font-semibold text-[#71847f]">
              {selectedMember?.name ?? "未选择成员"}
            </span>
          </div>
          <AsyncContent
            empty={(purchaseRecords.data?.length ?? 0) === 0}
            emptyDescription="当前成员还没有购药历史记录。"
            error={membersError ?? purchaseRecords.error}
            loading={membersLoading || (Boolean(memberId) && purchaseRecords.loading)}
            onRetry={membersError ? reloadMembers : purchaseRecords.reload}
          >
            <div className="grid gap-3">
              {purchaseRecords.data?.map((record) => (
                <article
                  className="rounded-2xl border border-[#dbe7e3] bg-white p-4 shadow-sm"
                  key={record.id}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <h4 className="font-bold text-[#173c38]">
                        {record.medicine_name}
                      </h4>
                      <p className="mt-1 text-sm text-[#64748b]">
                        {record.pharmacy_name ?? "药店未记录"}
                      </p>
                    </div>
                    <span className="text-sm font-bold text-[#0f766e]">
                      × {record.quantity}
                    </span>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-xs text-[#71847f]">
                    <span>日期：{formatDate(record.purchased_at)}</span>
                    <span>渠道：{record.purchase_channel ?? "未记录"}</span>
                    <span>用法：{record.dosage ?? "未记录"}</span>
                  </div>
                </article>
              ))}
            </div>
          </AsyncContent>
        </section>

        <section>
          <h3 className="mb-3 text-lg font-bold text-[#173c38]">药店库存查询</h3>
          <form
            className="rounded-2xl border border-[#dbe7e3] bg-white p-5 shadow-sm"
            onSubmit={handleSearch}
          >
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="grid gap-1.5 text-sm font-semibold text-[#31534f]">
                药品名
                <input
                  className="rounded-lg border border-[#cdded8] px-3 py-2.5 font-normal outline-none focus:border-[#0f766e]"
                  onChange={(event) => setMedicineName(event.target.value)}
                  placeholder="例如：苯磺酸氨氯地平片"
                  value={medicineName}
                />
              </label>
              <label className="grid gap-1.5 text-sm font-semibold text-[#31534f]">
                城市
                <input
                  className="rounded-lg border border-[#cdded8] px-3 py-2.5 font-normal outline-none focus:border-[#0f766e]"
                  onChange={(event) => setCity(event.target.value)}
                  placeholder="例如：上海"
                  value={city}
                />
              </label>
            </div>
            <button
              className="mt-4 rounded-lg bg-[#0f766e] px-4 py-2.5 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-60"
              disabled={inventoryLoading}
              type="submit"
            >
              {inventoryLoading ? "查询中..." : "查询库存"}
            </button>
          </form>

          <div className="mt-3">
            {inventoryError ? (
              <p className="rounded-xl border border-[#fecaca] bg-[#fff8f7] p-4 text-sm text-[#991b1b]">
                {inventoryError}
              </p>
            ) : inventory === null ? (
              <p className="rounded-xl border border-dashed border-[#cdded8] bg-white p-5 text-sm text-[#71847f]">
                输入药品名或城市后开始查询。库存仅供流程准备，不代表已锁定或已下单。
              </p>
            ) : inventory.length === 0 ? (
              <p className="rounded-xl border border-dashed border-[#cdded8] bg-white p-5 text-sm text-[#71847f]">
                没有匹配的库存记录。
              </p>
            ) : (
              <div className="grid gap-3">
                {inventory.map((item) => (
                  <article
                    className="rounded-2xl border border-[#dbe7e3] bg-white p-4 shadow-sm"
                    key={item.inventory_id}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <h4 className="font-bold text-[#173c38]">
                          {item.pharmacy_name}
                        </h4>
                        <p className="mt-1 text-sm text-[#64748b]">
                          {item.city} · {item.medicine_name}
                        </p>
                      </div>
                      <StatusBadge tone={item.stock_quantity > 0 ? "success" : "warning"}>
                        库存 {item.stock_quantity}
                      </StatusBadge>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2 text-xs">
                      {item.supports_delivery ? <StatusBadge>支持配送</StatusBadge> : null}
                      {item.supports_pickup ? <StatusBadge>支持自提</StatusBadge> : null}
                    </div>
                    {item.safety_note ? (
                      <p className="mt-3 text-xs leading-5 text-[#92400e]">
                        {item.safety_note}
                      </p>
                    ) : null}
                  </article>
                ))}
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
