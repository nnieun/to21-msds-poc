-- 로그인 사용자와 refresh 토큰. 서비스 DB(msds_service)의 auth 스키마.
-- scripts/auth_migrate.py 가 적용한다. 몇 번 돌려도 된다(IF NOT EXISTS).
-- extract·judge 와 FK로 묶지 않는다: 검수 기록의 reviewer·saved_by 는 기록 당시 이름을 그대로 남기는 이력 값이다.
BEGIN;

CREATE SCHEMA IF NOT EXISTS auth;

CREATE TABLE IF NOT EXISTS auth.users (
    user_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE CHECK (username ~ '^[a-z0-9_.-]{3,40}$'),
    -- 검수·판정 기록에 남는 이름. 기록 칸 제한(추출 40자, 판정 50자) 중 작은 쪽에 맞춘다
    display_name  TEXT NOT NULL CHECK (length(btrim(display_name)) BETWEEN 1 AND 40),
    password_hash TEXT NOT NULL CHECK (password_hash LIKE '$argon2%'),
    role          TEXT NOT NULL CHECK (role IN ('admin', 'reviewer')),
    is_active     BOOLEAN NOT NULL DEFAULT true,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at TIMESTAMPTZ
);

-- 토큰 원문은 저장하지 않고 jti(토큰 번호)만 남긴다. 한 번 쓰면 revoked_at 을 채운다(회전).
CREATE TABLE IF NOT EXISTS auth.refresh_tokens (
    jti        TEXT PRIMARY KEY CHECK (jti ~ '^[0-9a-f]{32}$'),
    user_id    BIGINT NOT NULL REFERENCES auth.users (user_id),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS refresh_tokens_user_idx ON auth.refresh_tokens (user_id) WHERE revoked_at IS NULL;

COMMIT;
