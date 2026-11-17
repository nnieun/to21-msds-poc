"use client";

/*
 * 검토자 = 로그인한 사람. 기록에 남는 이름은 서버가 로그인 정보로 정한다 (본문의 reviewer 는 서버가 쓰지 않는다).
 * 화면은 표시와 옛 대역(judgment-mock)을 위해 같은 이름을 보낸다.
 * AuthGate 안에서는 늘 로그인한 뒤라 빈 값이 아니다. 로그인 정보를 받기 전에만 빈 값이다.
 */
import { useQuery } from "@tanstack/react-query";
import { meQuery, type User } from "@/api/auth";

export function useCurrentUser(): User | undefined {
  return useQuery(meQuery()).data;
}

/** 지금 검토자 이름 (로그인한 사람의 표시 이름) */
export function useReviewer() {
  return useCurrentUser()?.display_name ?? "";
}
