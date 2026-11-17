"use client";

import { AppHeader } from "@/components/shell/app-header";
import { PageMain } from "@/components/shell/layout";
import { NewUserForm, UserTable } from "@/components/admin/users";
import { useCurrentUser } from "@/lib/reviewer";

const WIDTH = "max-w-280";

/** 사용자 관리 (관리자만). 서버도 관리자가 아니면 403 으로 막는다 */
export default function UsersPage() {
  const me = useCurrentUser();
  return (
    <>
      <AppHeader width={WIDTH} />
      <PageMain width={WIDTH} className="gap-8 pt-10">
        <section>
          <h1 className="text-2xl font-bold">사용자 관리</h1>
          <p className="text-mut">검수 기록에는 로그인한 사람의 이름이 남습니다. 계정을 막으면 그 사람은 바로 로그아웃됩니다.</p>
        </section>
        {me && me.role !== "admin" ? (
          <p role="alert" className="text-red">
            관리자만 볼 수 있는 화면입니다.
          </p>
        ) : (
          <>
            <NewUserForm />
            <UserTable />
          </>
        )}
      </PageMain>
    </>
  );
}
