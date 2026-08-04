import type { Metadata } from "next";

import { AppShell } from "@/components/AppShell";
import { MemberProvider } from "@/components/providers/MemberProvider";
import "./globals.css";

export const metadata: Metadata = {
  title: "家庭健康助手",
  description: "帮助你整理家庭健康事务、报告和用药记录。",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>
        <MemberProvider>
          <AppShell>{children}</AppShell>
        </MemberProvider>
      </body>
    </html>
  );
}

