import { PagePanel } from "@/components/PagePanel";

export default function PurchasePlansPage() {
  return (
    <PagePanel
      title="购药方案"
      description="展示药店库存、邮寄配送、自取方式和用户确认后的购药计划。"
      items={["药店自取", "邮寄配送", "库存充足", "库存不足"]}
    />
  );
}

