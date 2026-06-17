import { PagePanel } from "@/components/PagePanel";

export default function KnowledgePage() {
  return (
    <PagePanel
      title="SOP / 知识库"
      description="第一版计划使用关键词检索，输出必须带知识来源，后续预留向量检索接口。"
      items={["复诊续方 SOP", "用药提醒模板", "人工确认规则", "医疗安全边界规则"]}
    />
  );
}

