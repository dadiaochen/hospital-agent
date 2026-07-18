import { MemberSwitcher } from "@/components/MemberSwitcher";
import { Navigation } from "@/components/Navigation";

type AppShellProps = {
  children: React.ReactNode;
};

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="min-h-screen bg-[#f4f8f6] text-ink">
      <header className="border-b border-[#d9e5e1] bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1440px] flex-col gap-4 px-4 py-4 sm:px-6 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-clinic">
              FamilyHealthAgent
            </p>
            <h1 className="mt-1 text-xl font-bold tracking-tight text-[#173c38]">
              家庭健康事务管理台
            </h1>
          </div>
          <MemberSwitcher />
        </div>
      </header>

      <div className="mx-auto grid max-w-[1440px] gap-5 px-4 py-5 sm:px-6 lg:grid-cols-[224px_minmax(0,1fr)]">
        <aside className="h-fit rounded-2xl border border-[#dbe7e3] bg-white p-3 shadow-sm">
          <Navigation />
          <div className="mt-3 rounded-xl bg-[#f1f7f4] p-3 text-xs leading-5 text-[#52706b]">
            系统只整理信息和生成草稿，不诊断、不开方、不修改医生处方。
          </div>
        </aside>
        <main>{children}</main>
      </div>
    </div>
  );
}
