/*
 * 추출 API 호출의 공통 입구. 모든 응답은 여기서 스키마로 parse 한 뒤에 돌려준다.
 * 실패는 두 가지로 나눈다:
 *   - ApiRequestError: 서버가 4xx·5xx 로 거절함 (본문은 ApiError 모양)
 *   - ApiContractError: 서버는 성공했는데 응답 모양이 계약(schemas.ts)과 다름 → 어느 쪽 버그인지 바로 보이게
 *
 * 로그인: 서버가 준 HttpOnly 쿠키(msds_access)를 매 요청에 실어 보낸다. 토큰은 스크립트가 만지지 않는다.
 * 401 이 오면 refresh 쿠키로 한 번 갱신해 같은 요청을 다시 보낸다. 그래도 401 이면 로그인이 끝난 것이라
 * SIGNED_OUT 을 알린다 (AuthGate 가 로그인 화면으로 보낸다).
 */
import type { z } from "zod";
import { apiErrorSchema } from "./schemas";

/**
 * API 주소 앞부분. 정적 export 라 빌드할 때 값이 박힌다.
 * 비워 두면 같은 출처(/api/...)로 부른다. 개발 중에 FastAPI 를 따로 띄우면 NEXT_PUBLIC_API_BASE 로 넘긴다.
 */
const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

export class ApiRequestError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
}

export class ApiContractError extends Error {
  constructor(
    readonly path: string,
    readonly issues: z.core.$ZodIssue[],
  ) {
    super(`응답 모양이 계약과 다릅니다: ${path} (${issues.map((i) => i.path.join(".") || "(최상위)").join(", ")})`);
    this.name = "ApiContractError";
  }
}

/** 다시 물어도 결과가 같은 실패: 4xx 와 계약 위반. 연결 끊김·5xx 는 나아질 수 있다 */
export function isPermanentError(error: unknown) {
  return (error instanceof ApiRequestError && error.status < 500) || error instanceof ApiContractError;
}

export function apiUrl(path: string, query?: Record<string, string>) {
  const q = query ? `?${new URLSearchParams(query).toString()}` : "";
  return `${BASE}${path}${q}`;
}

/**
 * FastAPI 오류 본문 { detail } 을 ApiRequestError 로 바꾼다.
 * detail 이 문장이면 그대로, 판정 API 의 객체면 그 message, 422 의 항목 목록이면 "어디: 무엇" 을 이어 붙인다.
 * code 는 http_<상태> 또는 validation.
 */
export async function toRequestError(res: Response): Promise<ApiRequestError> {
  const body: unknown = await res.json().catch(() => null);
  const parsed = apiErrorSchema.safeParse(body);
  if (!parsed.success) return new ApiRequestError(res.status, "unknown", `서버가 ${res.status} 로 응답했습니다.`);
  const { detail } = parsed.data;
  if (typeof detail === "string") return new ApiRequestError(res.status, `http_${res.status}`, detail);
  if (!Array.isArray(detail)) return new ApiRequestError(res.status, `http_${res.status}`, detail.message);
  const message = detail.map((d) => `${d.loc.join(".")}: ${d.msg}`).join("; ");
  return new ApiRequestError(res.status, "validation", message);
}

/** 로그인이 끝났다는 알림 (refresh 도 거절됨). 같은 탭 안에서만 쓴다 */
export const SIGNED_OUT = "msds:signed-out";

/** 이 경로들의 401 은 "아이디·비밀번호가 틀림"이나 "갱신 실패"라 다시 갱신하지 않는다 */
const NO_RETRY = ["/api/auth/login", "/api/auth/refresh", "/api/auth/logout"];

const REFRESHED_AT = "msds.auth.refreshed-at";
/** 다른 탭이 이 시간 안에 갱신했으면 쿠키가 이미 새것이라 또 갱신하지 않는다 */
const FRESH_MS = 10_000;

const readStamp = () => {
  try {
    return Number(window.localStorage.getItem(REFRESHED_AT) ?? 0);
  } catch {
    return 0;
  }
};
const writeStamp = () => {
  try {
    window.localStorage.setItem(REFRESHED_AT, String(Date.now()));
  } catch {
    // 저장소를 못 쓰면 탭끼리 갱신을 나누지 못할 뿐이다
  }
};

let refreshing: Promise<boolean> | null = null;

/**
 * refresh 쿠키로 새 토큰 쌍을 받는다. 동시에 여러 요청이 401 을 받아도 한 번만 보낸다.
 * 서버는 이미 쓴 refresh 가 다시 오면 훔친 것으로 보고 모두 끊으므로, 탭 여러 개가 같은 쿠키로
 * 동시에 갱신하지 않도록 브라우저 잠금(Web Locks)으로 차례를 세우고 방금 갱신했으면 건너뛴다.
 */
export function refreshSession(): Promise<boolean> {
  const run = async () => {
    if (Date.now() - readStamp() < FRESH_MS) return true;
    const ok = await fetch(apiUrl("/api/auth/refresh"), { method: "POST", credentials: "include" })
      .then((r) => r.ok)
      .catch(() => false);
    if (ok) writeStamp();
    return ok;
  };
  const queued = async (): Promise<boolean> =>
    typeof navigator !== "undefined" && navigator.locks ? await navigator.locks.request("msds-auth-refresh", run) : run();
  const task =
    refreshing ??
    queued().finally(() => {
      refreshing = null;
    });
  refreshing = task;
  return task;
}

export function notifySignedOut() {
  window.dispatchEvent(new Event(SIGNED_OUT));
}

/**
 * 로그인 쿠키를 실어 보내는 fetch. 401 이면 한 번 갱신해 다시 보낸다.
 * 다시 보낼 수 있도록 body 는 문자열·Blob·File 만 쓴다 (스트림은 한 번 읽으면 끝난다).
 */
export async function apiFetch(path: string, init?: RequestInit & { query?: Record<string, string> }): Promise<Response> {
  const { query, ...rest } = init ?? {};
  const url = apiUrl(path, query);
  const send = () => fetch(url, { credentials: "include", ...rest });
  let res = await send();
  if (res.status === 401 && !NO_RETRY.some((p) => path.startsWith(p))) {
    if (await refreshSession()) res = await send();
    if (res.status === 401) notifySignedOut();
  }
  return res;
}

/** JSON 을 받아 schema 로 확인한다. 실패는 위 두 오류 중 하나로 던진다. */
export async function requestJson<S extends z.ZodType>(
  schema: S,
  path: string,
  init?: RequestInit & { query?: Record<string, string> },
): Promise<z.infer<S>> {
  const res = await apiFetch(path, {
    ...init,
    headers: { Accept: "application/json", ...init?.headers },
  });
  if (!res.ok) throw await toRequestError(res);

  const parsed = schema.safeParse(await res.json());
  if (!parsed.success) throw new ApiContractError(path, parsed.error.issues);
  return parsed.data;
}
