"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { authKeys, login } from "@/api/auth";
import { ApiRequestError } from "@/api/client";
import { Button, Card, Field, Input } from "@/components/ui";
import { safeNext } from "@/lib/routes";

/*
 * 로그인. 계정은 관리자가 만든다 (스스로 가입하지 않는다).
 * 성공하면 서버가 HttpOnly 쿠키를 주고, 받은 사용자 정보를 캐시에 넣어 둔 채 next(없으면 목록)로 간다.
 * next 는 useSearchParams 대신 주소에서 직접 읽는다 (정적 export 에서 Suspense 경계 없이 쓰려고).
 */

const loginSchema = z.object({
  username: z.string().trim().min(1, "아이디를 입력해 주세요."),
  password: z.string().min(1, "비밀번호를 입력해 주세요."),
});
type LoginValues = z.infer<typeof loginSchema>;

function failureText(error: unknown) {
  if (error instanceof ApiRequestError && (error.status === 401 || error.status === 429)) return error.message;
  if (error instanceof ApiRequestError) return `로그인하지 못했습니다: ${error.message}`;
  return "서버에 연결하지 못했습니다. 서버가 켜져 있는지 확인하고 다시 눌러 주세요.";
}

export default function LoginPage() {
  const router = useRouter();
  const client = useQueryClient();
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginValues>({ resolver: zodResolver(loginSchema), defaultValues: { username: "", password: "" } });

  const signIn = useMutation({
    mutationFn: ({ username, password }: LoginValues) => login(username.toLowerCase(), password),
    onSuccess: (user) => {
      client.setQueryData(authKeys.me, user);
      router.replace(safeNext(new URLSearchParams(window.location.search).get("next")));
    },
  });
  const busy = signIn.isPending || signIn.isSuccess;

  return (
    <main className="flex flex-1 items-center justify-center overflow-y-auto px-4 py-10">
      <Card className="flex w-full max-w-100 flex-col gap-5">
        <div>
          <p className="text-lg font-bold text-ink">MSDS 검수</p>
          <h1 className="text-2xl font-bold">로그인</h1>
          <p className="text-sm text-mut">계정은 관리자에게 받습니다.</p>
        </div>
        <form noValidate className="flex flex-col gap-4" onSubmit={handleSubmit((v) => signIn.mutate(v))}>
          <Field id="username" label="아이디" error={errors.username?.message}>
            <Input
              id="username"
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              autoFocus
              disabled={busy}
              aria-invalid={!!errors.username}
              aria-describedby={errors.username ? "username-error" : undefined}
              {...register("username")}
            />
          </Field>
          <Field id="password" label="비밀번호" error={errors.password?.message}>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              disabled={busy}
              aria-invalid={!!errors.password}
              aria-describedby={errors.password ? "password-error" : undefined}
              {...register("password")}
            />
          </Field>
          {signIn.isError && (
            <p role="alert" className="text-sm break-words text-red">
              {failureText(signIn.error)}
            </p>
          )}
          <Button type="submit" variant="primary" size="lg" disabled={busy} aria-busy={busy}>
            {busy ? "확인 중…" : "로그인"}
          </Button>
        </form>
      </Card>
    </main>
  );
}
