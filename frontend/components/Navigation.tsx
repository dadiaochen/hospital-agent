"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { navigationItems } from "@/lib/navigation";

export function Navigation() {
  const pathname = usePathname();

  return (
    <nav aria-label="主导航" className="flex min-w-max items-center gap-1">
      {navigationItems.map((item) => {
        const active =
          item.href === "/"
            ? pathname === "/"
            : pathname === item.href || pathname.startsWith(`${item.href}/`);
        const className = `rounded-full px-4 py-2.5 text-sm font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0f766e]/25 ${
          active
            ? "bg-[#dff3ed] text-[#0b655e]"
            : "text-[#475569] hover:bg-[#f1f6f4] hover:text-[#174f49]"
        }`;

        return (
          <Link
            aria-current={active ? "page" : undefined}
            className={className}
            href={item.href}
            key={item.href}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
