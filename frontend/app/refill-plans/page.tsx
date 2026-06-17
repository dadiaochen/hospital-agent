import { PagePanel } from "@/components/PagePanel";

export default function RefillPlansPage() {
  return (
    <PagePanel
      title="复诊续方 / 补货方案"
      description="展示 Agent 生成的待确认方案，包括处方有效性、剩余药量、药店库存和复诊申请草稿。"
      items={["父亲降压药续方方案", "母亲中医复诊材料", "需要医生确认", "用户确认状态"]}
    />
  );
}

