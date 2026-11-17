"use client";

/*
 * 모든 화면 앞의 로그인 확인. 정적 export 라 서버(미들웨어)에서 막을 수 없어 브라우저에서 확인한다.
 * 실제로 막는 것은 API 다 (로그인 없이 부르면 401). 이 문은 그 전에 로그인 화면으로 보내 줄 뿐이다.
 *   - /login 은 그대로 보여 준다
 *   - 그 밖의 화면은 GET /api/auth/me 가 성공해야 그린다. 401 이면 지금 주소를 next 로 달고 로그인 화면으로 간다
 *   - 어느 API 든 갱신까지 실패하면(SIGNED_OUT) 캐시를 비우고 로그인 화면으로 간다
 *   - 로그인해 있는 동안 access 토큰(30분)이 끊기기 전에 미리 갱신한다.
 *     PDF 뷰어·새 탭 PDF 는 이 입구를 거치지 않고 쿠키만 쓰므로, 미리 갱신해 두어야 끊기지 않는다
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { meQuery } from "@/api/auth";
import { ApiRequestError, SIGNED_OUT, notifySignedOut, refreshSession } from "@/api/client";
import { Button, Spinner } from "@/components/ui";
import { routes } from "@/lib/routes";

/** 서버 기본 access 수명(30분)보다 넉넉히 앞서 갱신한다 */
const REFRESH_EVERY_MS = 20 * 60_000;

const isPublic = (pathname: string) => pathname.replace(/\/$/, "") === "/login";
const here = () => `${window.location.pathname}${window.location.search}`;

export function AuthGate({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const open = isPublic(pathname);
  const router = useRouter();
  const client = useQueryClient();
  // 로그인 화면으로 가는 중: 그 사이 me 를 다시 묻지 않게 한다 (묻으면 401 → 또 SIGNED_OUT)
  const [leaving, setLeaving] = useState(false);
  const me = useQuery({ ...meQuery(), enabled: !open && !leaving });

  useEffect(() => {
    if (open) setLeaving(false);
  }, [open]);

  useEffect(() => {
    if (open) return;
    const onSignedOut = () => {
      setLeaving(true);
      client.clear();
      router.replace(routes.login(here()));
    };
    window.addEventListener(SIGNED_OUT, onSignedOut);
    return () => window.removeEventListener(SIGNED_OUT, onSignedOut);
  }, [open, client, router]);

  const unauthorized = me.error instanceof ApiRequestError && me.error.status === 401;
  useEffect(() => {
    if (!open && unauthorized && !leaving) notifySignedOut();
  }, [open, unauthorized, leaving]);

  const signedIn = !!me.data;
  useEffect(() => {
    if (open || !signedIn) return;
    const timer = window.setInterval(() => {
      void refreshSession().then((ok) => ok || notifySignedOut());
    }, REFRESH_EVERY_MS);
    return () => window.clearInterval(timer);
  }, [open, signedIn]);

  if (open) return <>{children}</>;
  if (me.data && !leaving) return <>{children}</>;
  if (me.isError && !unauthorized) {
    return (
      <Centered>
        <p role="alert" className="text-red">
          로그인 정보를 확인하지 못했습니다. 서버가 켜져 있는지 확인해 주세요.
        </p>
        <Button onClick={() => void me.refetch()}>다시 확인</Button>
      </Centered>
    );
  }
  return (
    <Centered>
      <Spinner label="로그인 확인 중" />
    </Centered>
  );
}

function Centered({ children }: { children: ReactNode }) {
  return <main className="flex flex-1 flex-col items-center justify-center gap-3 px-4 text-center">{children}</main>;
}
