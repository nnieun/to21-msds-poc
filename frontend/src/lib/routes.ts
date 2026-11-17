/*
 * 화면 주소. 정적 export 라 문서 번호는 경로가 아니라 ?doc= 으로 넘긴다
 * (빌드할 때 문서 목록을 알 수 없어 동적 경로를 미리 만들 수 없다).
 */

export const REVIEW_TABS = [
  { id: "hazard", label: "2항 유해성·위험성" },
  { id: "regulation", label: "15항 법적 규제" },
  { id: "components", label: "성분별 요약" },
  { id: "history", label: "검토 이력" },
  { id: "values", label: "추출값" },
] as const;

export type ReviewTab = (typeof REVIEW_TABS)[number]["id"];

export function isReviewTab(v: string | null): v is ReviewTab {
  return REVIEW_TABS.some((t) => t.id === v);
}

function withDoc(path: string, doc: string, extra?: Record<string, string>) {
  const q = new URLSearchParams({ doc, ...extra });
  return `${path}?${q.toString()}`;
}

/** 로그인 뒤 돌아갈 곳. 이 사이트 안의 경로만 받는다 (//다른곳 이나 http: 로 내보내지 않게) */
export function safeNext(next: string | null | undefined) {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return "/";
  return next.startsWith("/login") ? "/" : next;
}

export const routes = {
  home: () => "/",
  login: (next?: string) => (next && safeNext(next) !== "/" ? `/login/?${new URLSearchParams({ next })}` : "/login/"),
  users: () => "/admin/users/",
  extract: (doc: string, page?: number) => withDoc("/extract/", doc, page ? { page: String(page) } : undefined),
  reviewMode: (doc: string) => withDoc("/review/mode/", doc),
  review: (doc: string, tab: ReviewTab = "hazard", extra?: Record<string, string>) => withDoc("/review/", doc, { tab, ...extra }),
  save: (doc: string) => withDoc("/save/", doc),
};
