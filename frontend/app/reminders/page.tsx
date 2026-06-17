import { PagePanel } from "@/components/PagePanel";

export default function RemindersPage() {
  return (
    <PagePanel
      title="用药提醒与复诊提醒"
      description="用于管理每天早晚用药提醒、补货提醒和复诊提醒，创建动作必须经过用户确认。"
      items={["母亲早晚用药提醒", "父亲补货提醒", "复诊任务", "提醒状态"]}
    />
  );
}

