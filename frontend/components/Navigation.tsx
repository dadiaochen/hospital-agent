"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { navigationItems } from "@/lib/navigation";

export function Navigation() {
  const pathname = usePathname();

  return (
    <nav aria-label="主导航" className="grid gap-1.5">
      {navigationItems.map((item) => {
        const active =
          item.href === "/"
            ? pathname === "/"
            : pathname === item.href || pathname.startsWith(`${item.href}/`);
        return (
          <Link
            className={`rounded-lg px-3 py-2.5 text-sm font-medium transition ${
              active
                ? "bg-[#dff3ed] text-[#0b655e]"
                : "text-[#475569] hover:bg-[#f1f6f4] hover:text-[#174f49]"
            }`}
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
