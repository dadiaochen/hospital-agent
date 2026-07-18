import type { Metadata } from "next";

import { AppShell } from "@/components/AppShell";
import { MemberProvider } from "@/components/providers/MemberProvider";
import "./globals.css";

export const metadata: Metadata = {
  title: "FamilyHealthAgent",
  description: "Internet hospital chronic refill and family medication management Agent system.",
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

