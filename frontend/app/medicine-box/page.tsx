import { PagePanel } from "@/components/PagePanel";

export default function MedicineBoxPage() {
  return (
    <PagePanel
      title="家庭药箱"
      description="用于管理药品名称、规格、购买数量、用法用量、购买时间和预计剩余天数。"
      items={["降压药库存与剩余天数", "中药疗程进度", "补货提醒草稿", "药箱条目详情"]}
    />
  );
}

