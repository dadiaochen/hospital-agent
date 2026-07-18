export const navigationItems = [
  { href: "/", label: "总览" },
  { href: "/family", label: "家庭成员" },
  { href: "/medicine-box", label: "家庭药箱" },
  { href: "/refill-plans", label: "续方与复诊" },
  { href: "/reminders", label: "提醒任务" },
  { href: "/purchase-plans", label: "购药信息" },
  { href: "/knowledge", label: "知识检索" },
  { href: "/agent-runs", label: "执行记录" },
  { href: "/agent", label: "Agent 对话（3B）" },
];

export const mvpScenarios = [
  {
    title: "父亲降压药续方",
    status: "可生成本地草稿",
    boundary: "整理处方、药箱和购药记录，关键动作仍等待用户确认。",
  },
  {
    title: "母亲复诊材料整理",
    status: "可查看资料来源",
    boundary: "展示历史处方和待确认草稿，不替医生判断病情。",
  },
  {
    title: "母亲用药提醒",
    status: "只展示确认草稿",
    boundary: "提醒写入前必须有用户确认，当前不做外部推送。",
  },
  {
    title: "高风险用药请求",
    status: "运行时安全拦截",
    boundary: "不提供加减药建议，引导医生介入并保留安全来源。",
  },
];

