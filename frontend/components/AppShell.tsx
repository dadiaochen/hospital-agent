import Link from "next/link";

import { MemberSwitcher } from "@/components/MemberSwitcher";
import { Navigation } from "@/components/Navigation";

type AppShellProps = {
  children: React.ReactNode;
};

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="min-h-screen bg-[#fffdf7] text-ink">
      <header className="border-b border-[#eadfca] bg-[#fffaf0]/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1440px] flex-col gap-4 px-4 py-4 sm:px-6 md:flex-row md:items-center md:justify-between">
          <Link aria-label="返回患者端首页" className="group flex items-center gap-3" href="/">
            <span className="grid h-11 w-11 place-items-center rounded-2xl bg-[#f7b928] text-sm font-black text-[#553507] shadow-sm transition group-hover:-rotate-3">
              FH
            </span>
            <span>
              <span className="block text-xs font-bold uppercase tracking-[0.2em] text-[#b26c09]">
                FamilyHealthAgent
              </span>
              <span className="mt-1 block text-xl font-bold tracking-tight text-[#173c38]">
                家庭健康事务
              </span>
            </span>
          </Link>
          <div className="flex flex-wrap items-center gap-3">
            <span className="hidden rounded-full bg-[#fff0c2] px-3 py-2 text-xs font-semibold text-[#80530b] lg:inline-flex">
              仅生成本地草稿，不执行外部提交
            </span>
            <MemberSwitcher />
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-[1440px] gap-5 px-4 py-5 sm:px-6 lg:grid-cols-[224px_minmax(0,1fr)]">
        <aside className="h-fit rounded-2xl border border-[#eadfca] bg-white p-3 shadow-sm">
          <Navigation />
          <div className="mt-3 rounded-xl bg-[#fff7df] p-3 text-xs leading-5 text-[#80602b]">
            系统只整理信息和生成草稿，不诊断、不开方、不修改医生处方。
          </div>
        </aside>
        <main>{children}</main>
      </div>
    </div>
  );
}
