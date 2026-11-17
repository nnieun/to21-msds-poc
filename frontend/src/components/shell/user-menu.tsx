"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ROLE_LABEL, logout } from "@/api/auth";
import { Button } from "@/components/ui";
import { useCurrentUser } from "@/lib/reviewer";
import { routes } from "@/lib/routes";

/** 머리줄 오른쪽: 로그인한 사람(기록에 남는 이름), 관리자면 사용자 관리, 로그아웃 */
export function UserMenu() {
  const user = useCurrentUser();
  const client = useQueryClient();
  const router = useRouter();
  const [leaving, setLeaving] = useState(false);
  if (!user) return null;

  const signOut = async () => {
    setLeaving(true);
    await logout();
    client.clear();
    router.replace(routes.login());
  };

  return (
    <div className="flex items-center gap-2 text-mut">
      <span>{ROLE_LABEL[user.role]}</span>
      <strong className="font-medium text-ink" title={`아이디 ${user.username}`}>
        {user.display_name}
      </strong>
      {user.role === "admin" && (
        <Link href={routes.users()} className="px-1.5 py-1 font-medium">
          사용자 관리
        </Link>
      )}
      {/* link 모양이 md 크기의 최소 높이를 물려받지 않도록 머리줄 높이에 맞춘다 */}
      <Button variant="link" className="min-h-0" disabled={leaving} onClick={() => void signOut()}>
        {leaving ? "나가는 중…" : "로그아웃"}
      </Button>
    </div>
  );
}
