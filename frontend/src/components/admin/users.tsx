"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import {
  DISPLAY_MAX,
  PASSWORD_MAX,
  PASSWORD_MIN,
  ROLES,
  ROLE_LABEL,
  USERNAME_PATTERN,
  authKeys,
  changeUser,
  createUser,
  usersQuery,
  type Role,
  type User,
  type UserChange,
} from "@/api/auth";
import { ApiRequestError } from "@/api/client";
import { Button, Card, Dialog, Field, Input, Skeleton, StatusLabel, Table, TableHead } from "@/components/ui";
import { useCurrentUser } from "@/lib/reviewer";

/*
 * 사용자 관리 화면의 두 칸: 새 사용자 만들기, 사용자 표.
 * 입력 규칙은 서버(msds/auth/users.py)와 같게 미리 확인하고, 서버가 거절하면 그 문장을 그대로 보여 준다
 * (예: 마지막 관리자를 막으려 하면 409).
 */

const displayName = z.string().trim().min(1, "이름을 입력해 주세요.").max(DISPLAY_MAX, `이름은 ${DISPLAY_MAX}자 이내로 입력해 주세요.`);
const password = z
  .string()
  .min(PASSWORD_MIN, `비밀번호는 ${PASSWORD_MIN}자 이상이어야 합니다.`)
  .max(PASSWORD_MAX, `비밀번호는 ${PASSWORD_MAX}자 이내로 입력해 주세요.`);

const newUserSchema = z.object({
  username: z
    .string()
    .trim()
    .toLowerCase()
    .regex(USERNAME_PATTERN, "아이디는 영문 소문자·숫자·_ . - 로 3~40자입니다."),
  display_name: displayName,
  password,
  role: z.enum(ROLES),
});
type NewUserInput = z.input<typeof newUserSchema>;
type NewUserValues = z.output<typeof newUserSchema>;

const errorText = (error: unknown) =>
  error instanceof ApiRequestError ? error.message : "저장하지 못했습니다. 서버가 켜져 있는지 확인해 주세요.";

const selectClass = "min-h-10 rounded-md border border-field-line bg-white px-2.5 text-ink disabled:bg-tint";

export function NewUserForm() {
  const client = useQueryClient();
  const [done, setDone] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<NewUserInput, unknown, NewUserValues>({
    resolver: zodResolver(newUserSchema),
    defaultValues: { username: "", display_name: "", password: "", role: "reviewer" },
  });
  const create = useMutation({
    mutationFn: createUser,
    onSuccess: (user) => {
      setDone(`${user.display_name}(${user.username}) 계정을 만들었습니다.`);
      reset();
      return client.invalidateQueries({ queryKey: authKeys.users });
    },
  });

  return (
    <Card className="flex flex-col gap-4">
      <h2 className="text-lg font-bold">새 사용자</h2>
      <form
        noValidate
        className="grid gap-4 md:grid-cols-[1fr_1fr_1fr_auto_auto] md:items-start"
        onSubmit={handleSubmit((v) => {
          setDone(null);
          create.mutate(v);
        })}
      >
        <Field id="new-username" label="아이디" hint="로그인할 때 씁니다" error={errors.username?.message}>
          <Input
            id="new-username"
            autoComplete="off"
            autoCapitalize="none"
            spellCheck={false}
            aria-invalid={!!errors.username}
            aria-describedby={errors.username ? "new-username-error" : "new-username-hint"}
            {...register("username")}
          />
        </Field>
        <Field id="new-display" label="이름" hint="기록에 남는 이름" error={errors.display_name?.message}>
          <Input
            id="new-display"
            autoComplete="off"
            aria-invalid={!!errors.display_name}
            aria-describedby={errors.display_name ? "new-display-error" : "new-display-hint"}
            {...register("display_name")}
          />
        </Field>
        <Field id="new-password" label="첫 비밀번호" hint={`${PASSWORD_MIN}자 이상`} error={errors.password?.message}>
          <Input
            id="new-password"
            type="password"
            autoComplete="new-password"
            aria-invalid={!!errors.password}
            aria-describedby={errors.password ? "new-password-error" : "new-password-hint"}
            {...register("password")}
          />
        </Field>
        <Field id="new-role" label="역할">
          <select id="new-role" className={selectClass} {...register("role")}>
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {ROLE_LABEL[r]}
              </option>
            ))}
          </select>
        </Field>
        <Button type="submit" variant="primary" size="lg" className="md:mt-6" disabled={create.isPending}>
          {create.isPending ? "만드는 중…" : "만들기"}
        </Button>
      </form>
      {create.isError && (
        <p role="alert" className="text-sm break-words text-red">
          {errorText(create.error)}
        </p>
      )}
      {done && (
        <p role="status" className="text-sm text-grn">
          {done}
        </p>
      )}
    </Card>
  );
}

export function UserTable() {
  const users = useQuery(usersQuery());
  if (users.isPending) return <Skeleton className="w-2/3" />;
  if (users.isError) {
    return (
      <div role="alert" className="flex flex-col items-start gap-2 text-sm">
        <p className="text-red">{errorText(users.error)}</p>
        <Button onClick={() => void users.refetch()}>다시 불러오기</Button>
      </div>
    );
  }
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-lg font-bold">사용자 {users.data.length}명</h2>
      <Table>
        <TableHead>
          <span className="w-40">아이디</span>
          <span className="w-40">이름</span>
          <span className="w-28">역할</span>
          <span className="w-20">상태</span>
          <span className="flex-1 text-right">관리</span>
        </TableHead>
        {users.data.map((u) => (
          <UserRow key={u.id} user={u} />
        ))}
      </Table>
    </section>
  );
}

function UserRow({ user }: { user: User }) {
  const client = useQueryClient();
  const me = useCurrentUser();
  const self = me?.id === user.id;
  const [dialog, setDialog] = useState<"name" | "password" | null>(null);
  const change = useMutation({
    mutationFn: (body: UserChange) => changeUser(user.id, body),
    onSuccess: (updated) => {
      setDialog(null);
      // 자기 이름을 바꿨으면 머리줄도 바뀌게 한다
      if (self) client.setQueryData(authKeys.me, updated);
      return client.invalidateQueries({ queryKey: authKeys.users });
    },
  });

  return (
    <div className="flex flex-wrap items-center gap-3 border-b border-line2 px-4 py-2.5 last:border-b-0">
      <span className="w-40 truncate font-mono text-sm" title={user.username}>
        {user.username}
        {self && <span className="ml-1 text-mut">(나)</span>}
      </span>
      <span className="w-40 truncate" title={user.display_name}>
        {user.display_name}
      </span>
      <span className="w-28">
        <label className="sr-only" htmlFor={`role-${user.id}`}>
          {user.username} 역할
        </label>
        <select
          id={`role-${user.id}`}
          className={selectClass}
          value={user.role}
          disabled={self || change.isPending}
          title={self ? "자기 역할은 바꿀 수 없습니다" : undefined}
          onChange={(e) => change.mutate({ role: e.target.value as Role })}
        >
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {ROLE_LABEL[r]}
            </option>
          ))}
        </select>
      </span>
      <span className="w-20">
        <StatusLabel tone={user.is_active ? "success" : "neutral"}>{user.is_active ? "사용 중" : "막힘"}</StatusLabel>
      </span>
      <span className="flex flex-1 flex-wrap justify-end gap-1">
        <Button variant="link" disabled={change.isPending} onClick={() => setDialog("name")}>
          이름 바꾸기
        </Button>
        <Button variant="link" disabled={change.isPending} onClick={() => setDialog("password")}>
          비밀번호 다시 정하기
        </Button>
        {!self && (
          <Button variant="link" disabled={change.isPending} onClick={() => change.mutate({ is_active: !user.is_active })}>
            {user.is_active ? "막기" : "다시 쓰게 하기"}
          </Button>
        )}
      </span>
      {change.isError && !dialog && (
        <p role="alert" className="w-full text-sm break-words text-red">
          {errorText(change.error)}
        </p>
      )}
      <ChangeDialog
        user={user}
        kind={dialog}
        pending={change.isPending}
        error={dialog && change.isError ? errorText(change.error) : null}
        onClose={() => {
          setDialog(null);
          change.reset();
        }}
        onSave={(body) => change.mutate(body)}
      />
    </div>
  );
}

const dialogSchemas = {
  name: z.object({ value: displayName }),
  password: z.object({ value: password }),
};

function ChangeDialog({
  user,
  kind,
  pending,
  error,
  onClose,
  onSave,
}: {
  user: User;
  kind: "name" | "password" | null;
  pending: boolean;
  error: string | null;
  onClose: () => void;
  onSave: (body: UserChange) => void;
}) {
  const [draft, setDraft] = useState("");
  const [invalid, setInvalid] = useState<string | null>(null);
  const formId = `user-${user.id}-form`;
  const inputId = `user-${user.id}-value`;
  const isName = kind === "name";

  const close = () => {
    setDraft("");
    setInvalid(null);
    onClose();
  };
  const submit = () => {
    if (!kind) return;
    const parsed = dialogSchemas[kind].safeParse({ value: draft });
    if (!parsed.success) return setInvalid(parsed.error.issues[0]?.message ?? "값을 확인해 주세요.");
    setInvalid(null);
    onSave(isName ? { display_name: parsed.data.value } : { password: parsed.data.value });
  };
  const shown = invalid ?? error;

  return (
    <Dialog
      open={kind !== null}
      onClose={close}
      title={isName ? `${user.username} 이름 바꾸기` : `${user.username} 비밀번호 다시 정하기`}
      actions={
        <>
          <Button onClick={close}>취소</Button>
          <Button variant="primary" type="submit" form={formId} disabled={pending}>
            {pending ? "저장 중…" : "저장"}
          </Button>
        </>
      }
    >
      <form
        id={formId}
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <Field
          id={inputId}
          label={isName ? "이름" : "새 비밀번호"}
          hint={isName ? "앞으로의 기록에 이 이름이 남습니다." : "바꾸면 그 사람은 모든 곳에서 로그아웃됩니다."}
          error={shown ?? undefined}
        >
          <Input
            id={inputId}
            type={isName ? "text" : "password"}
            autoComplete={isName ? "off" : "new-password"}
            value={draft}
            aria-invalid={!!shown}
            aria-describedby={shown ? `${inputId}-error` : `${inputId}-hint`}
            onFocus={() => {
              if (isName && !draft) setDraft(user.display_name);
            }}
            onChange={(e) => {
              setDraft(e.target.value);
              setInvalid(null);
            }}
          />
        </Field>
      </form>
    </Dialog>
  );
}
