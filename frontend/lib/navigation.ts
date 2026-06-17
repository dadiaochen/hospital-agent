export const navigationItems = [
  { href: "/", label: "总览" },
  { href: "/agent", label: "Agent" },
  { href: "/family", label: "家庭成员" },
  { href: "/medicine-box", label: "家庭药箱" },
  { href: "/refill-plans", label: "续方方案" },
  { href: "/purchase-plans", label: "购药方案" },
  { href: "/reminders", label: "提醒任务" },
  { href: "/agent-runs", label: "执行记录" },
  { href: "/knowledge", label: "知识库" },
];

export const mvpScenarios = [
  {
    title: "父亲降压药续方",
    status: "待实现 Agent 流程",
    boundary: "生成续方材料和补货方案，等待用户确认。",
  },
  {
    title: "母亲中医复诊材料",
    status: "待实现材料整理",
    boundary: "整理历史信息，不替医生判断病情。",
  },
  {
    title: "母亲用药提醒",
    status: "待实现确认后创建",
    boundary: "提醒创建前必须确认计划。",
  },
  {
    title: "高风险用药调整拦截",
    status: "待实现安全策略",
    boundary: "不回答加减药建议，提示医生介入。",
  },
];

