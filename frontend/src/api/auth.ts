/*
 * 로그인과 사용자 관리 (백엔드 msds/api/routers/auth.py, 명세 6.1).
 * 토큰은 서버가 HttpOnly 쿠키로 준다. 응답 본문의 access_token 은 화면이 쓰지 않는다 (스크립트가 토큰을 들고 있지 않게).
 */
import { queryOptions } from "@tanstack/react-query";
import { z } from "zod";
import { apiFetch, requestJson } from "./client";

export const ROLES = ["admin", "reviewer"] as const;
export type Role = (typeof ROLES)[number];
export const ROLE_LABEL: Record<Role, string> = { admin: "관리자", reviewer: "검토자" };

export const userSchema = z.object({
  id: z.number(),
  username: z.string(),
  display_name: z.string(),
  role: z.enum(ROLES),
  is_active: z.boolean(),
});
export type User = z.infer<typeof userSchema>;

const sessionSchema = z.object({ user: userSchema, expires_in: z.number() });
const userListSchema = z.object({ items: z.array(userSchema) });

/** 서버 규칙과 같게 둔다 (msds/auth/users.py). 서버가 다시 확인한다 */
export const USERNAME_PATTERN = /^[a-z0-9_.-]{3,40}$/;
export const DISPLAY_MAX = 40;
export const PASSWORD_MIN = 8;
export const PASSWORD_MAX = 128;

export const authKeys = {
  me: ["auth", "me"] as const,
  users: ["auth", "users"] as const,
};

/** 지금 로그인한 사람. 401 이면 로그인 전이다 (AuthGate 가 로그인 화면으로 보낸다) */
export const meQuery = () =>
  queryOptions({
    queryKey: authKeys.me,
    queryFn: ({ signal }) => requestJson(userSchema, "/api/auth/me", { signal }),
    staleTime: 5 * 60_000,
    retry: false,
  });

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export async function login(username: string, password: string): Promise<User> {
  const session = await requestJson(sessionSchema, "/api/auth/login", json("POST", { username, password }));
  return session.user;
}

/** 이미 나간 상태여도 204 다. 연결이 끊겨도 화면은 로그인 화면으로 간다 */
export async function logout() {
  await apiFetch("/api/auth/logout", { method: "POST" }).catch(() => undefined);
}

export const usersQuery = () =>
  queryOptions({
    queryKey: authKeys.users,
    queryFn: ({ signal }) => requestJson(userListSchema, "/api/users", { signal }).then((r) => r.items),
  });

export type NewUser = { username: string; display_name: string; password: string; role: Role };
export const createUser = (body: NewUser) => requestJson(userSchema, "/api/users", json("POST", body));

export type UserChange = Partial<{ display_name: string; role: Role; is_active: boolean; password: string }>;
export const changeUser = (id: number, body: UserChange) => requestJson(userSchema, `/api/users/${id}`, json("PATCH", body));
