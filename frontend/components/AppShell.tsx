import Link from "next/link";

import { navigationItems } from "@/lib/navigation";

type AppShellProps = {
  children: React.ReactNode;
};

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="min-h-screen bg-[#f7faf9] text-ink">
      <header className="border-b border-[#d9e5e1] bg-white">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-5 py-5 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-sm font-medium text-clinic">FamilyHealthAgent</p>
            <h1 className="text-2xl font-semibold tracking-normal">家庭健康事务管理控制台</h1>
          </div>
          <div className="rounded-md border border-[#d9e5e1] px-3 py-2 text-sm text-[#475569]">
            Phase 1 Skeleton
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-7xl gap-6 px-5 py-6 lg:grid-cols-[220px_1fr]">
        <nav className="h-fit rounded-md border border-[#d9e5e1] bg-white p-3">
          <div className="grid gap-1">
            {navigationItems.map((item) => (
              <Link
                className="rounded-md px-3 py-2 text-sm font-medium text-[#334155] hover:bg-mist hover:text-clinic"
                href={item.href}
                key={item.href}
              >
                {item.label}
              </Link>
            ))}
          </div>
        </nav>
        <main>{children}</main>
      </div>
    </div>
  );
}

