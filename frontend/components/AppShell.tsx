import Link from "next/link";

import { MemberSwitcher } from "@/components/MemberSwitcher";
import { Navigation } from "@/components/Navigation";

type AppShellProps = {
  children: React.ReactNode;
};

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="min-h-screen bg-[#f7fbf9] text-[#173c38]">
      <header className="sticky top-0 z-30 border-b border-[#dbe9e4] bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1360px] flex-col gap-3 px-4 py-3 sm:px-6 lg:flex-row lg:items-center lg:gap-8 lg:px-8">
          <Link aria-label="返回家庭健康助手首页" className="group flex shrink-0 items-center gap-3" href="/">
            <span className="grid h-10 w-10 place-items-center rounded-2xl bg-[#0f766e] text-sm font-black text-white shadow-sm transition group-hover:bg-[#115e59]">
              FH
            </span>
            <span>
              <span className="block text-lg font-bold tracking-tight text-[#173c38]">
                家庭健康助手
              </span>
              <span className="hidden text-xs text-[#7b918b] sm:block">
                陪你整理家人的健康事务
              </span>
            </span>
          </Link>

          <div className="min-w-0 flex-1 overflow-x-auto">
            <Navigation />
          </div>

          <div className="flex shrink-0 items-center justify-between gap-3 sm:justify-end">
            <MemberSwitcher />
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-[1360px] px-4 py-5 sm:px-6 lg:px-8 lg:py-7">
        <main className="min-w-0">{children}</main>
      </div>
    </div>
  );
}
