import { PagePanel } from "@/components/PagePanel";

export default function FamilyPage() {
  return (
    <PagePanel
      title="家庭成员与健康档案"
      description="第二阶段会落库 users、family_members、health_profiles，第三阶段接入列表、创建和详情接口。"
      items={["本人：普通健康档案", "父亲：高血压长期用药", "母亲：睡眠问题 / 中医复诊"]}
    />
  );
}

