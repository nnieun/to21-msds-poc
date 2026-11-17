import type { Metadata } from "next";
import type { ReactNode } from "react";
import { AuthGate } from "@/components/shell/auth-gate";
import { QueryProvider } from "@/providers/query-provider";
import "./globals.css";

export const metadata: Metadata = {
  title: "MSDS 검수",
  description: "MSDS 추출값 검수 화면",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko">
      <body>
        <QueryProvider>
          <AuthGate>{children}</AuthGate>
        </QueryProvider>
      </body>
    </html>
  );
}
