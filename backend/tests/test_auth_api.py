"""로그인(JWT)과 권한. 실제 로그인 흐름을 거친다 (다른 API 시험은 auth_user.sign_in 으로 건너뛴다).

DB 없이 메모리 사용자 저장소로 돈다. PostgreSQL 저장소는 같은 메서드를 SQL로 구현한다 (msds.auth.users).
"""
import json
import jwt
import pytest
from fastapi.testclient import TestClient

from msds.api import extract_app, judge_app
from msds.auth import security
from msds.auth.security import AuthSettings, TokenError, decode, hash_password, issue_access, verify_password
from msds.auth.setup import LoginThrottle, ensure_admin_from_env
from msds.auth.users import MemoryUserStore
from msds.service import pipeline
from msds.service.store import DocumentStore

SECRET = "s" * 40
SETTINGS = AuthSettings(secret=SECRET)
PDF = b"%PDF-1.7\n% fake\n"
DOC = {"doc": {"doc_id": "x"}, "msds": [{"product": {"name": "젯소"}}]}


class Worker:
    def start(self): pass
    def stop(self, timeout=None): pass
    def submit(self, doc_id): pass


@pytest.fixture
def users():
    store = MemoryUserStore()
    store.create("admin", "관리자", hash_password("admin-pass-1"), "admin")
    store.create("kim", "김검수", hash_password("kim-pass-12"), "reviewer")
    return store


@pytest.fixture
def app(tmp_path, users):
    return extract_app.create_app(store=DocumentStore(tmp_path / "service"), worker=Worker(),
                                  pages_dir=tmp_path / "pages", static_dir=None,
                                  users=users, auth_settings=SETTINGS)


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def login(client, username="kim", password="kim-pass-12"):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r


# ── 토큰과 비밀번호 ──

def test_password_hash_round_trip():
    h = hash_password("correct horse")
    assert h.startswith("$argon2") and verify_password(h, "correct horse")
    assert not verify_password(h, "wrong") and not verify_password("not-a-hash", "x")


def test_token_type_signature_and_expiry_are_checked(users):
    user = users.find("kim")[0]
    token = issue_access(SETTINGS, user)
    assert decode(SETTINGS, token, "access")["user_id"] == user.id
    with pytest.raises(TokenError):
        decode(SETTINGS, token, "refresh")                       # access 를 refresh 로 못 쓴다
    with pytest.raises(TokenError):
        decode(AuthSettings(secret="x" * 40), token, "access")   # 다른 키로 서명한 토큰
    expired = jwt.encode({"sub": "2", "type": "access", "jti": "a", "iss": security.ISSUER,
                          "iat": 0, "exp": 1}, SECRET, algorithm="HS256")
    with pytest.raises(TokenError, match="만료"):
        decode(SETTINGS, expired, "access")
    none_alg = jwt.encode({"sub": "2", "type": "access"}, key=None, algorithm="none")
    with pytest.raises(TokenError):
        decode(SETTINGS, none_alg, "access")                     # 서명 없는 토큰


def test_short_secret_rejected_and_db_mode_requires_secret(monkeypatch):
    with pytest.raises(ValueError):
        AuthSettings(secret="short")
    monkeypatch.delenv(security.SECRET_ENV, raising=False)
    with pytest.raises(RuntimeError, match="MSDS_JWT_SECRET"):
        AuthSettings.from_env(require_secret=True)
    settings, ephemeral = AuthSettings.from_env(require_secret=False)
    assert ephemeral and len(settings.secret) >= 32


# ── 로그인이 필요한 곳 ──

def test_api_needs_login_but_health_and_login_do_not(client):
    assert client.get("/api/health").status_code == 200
    r = client.get("/api/documents")
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"
    assert client.post("/api/documents?filename=a.pdf", content=PDF).status_code == 401
    assert client.get("/api/auth/me").status_code == 401


def test_login_sets_httponly_cookies_and_bearer_also_works(app, client):
    r = login(client)
    body = r.json()
    assert body["user"] == {"id": 2, "username": "kim", "display_name": "김검수", "role": "reviewer", "is_active": True}
    cookies = r.headers.get_list("set-cookie")
    access = next(c for c in cookies if c.startswith("msds_access="))
    refresh = next(c for c in cookies if c.startswith("msds_refresh="))
    assert "httponly" in access.lower() and "samesite=strict" in access.lower() and "path=/" in access.lower()
    assert "path=/api/auth" in refresh.lower()                   # refresh 는 토큰 갱신 경로에만 간다
    assert client.get("/api/auth/me").json()["username"] == "kim"  # 쿠키로
    bare = TestClient(app)                                         # 쿠키 없이 Bearer 로
    assert bare.get("/api/documents").status_code == 401
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    assert bare.get("/api/documents", headers=headers).status_code == 200


def test_wrong_password_and_unknown_user_look_the_same(client):
    a = client.post("/api/auth/login", json={"username": "kim", "password": "nope-nope"})
    b = client.post("/api/auth/login", json={"username": "ghost", "password": "nope-nope"})
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_repeated_failures_lock_the_username(client):
    for _ in range(5):
        assert client.post("/api/auth/login", json={"username": "kim", "password": "bad-pass"}).status_code == 401
    r = client.post("/api/auth/login", json={"username": "kim", "password": "kim-pass-12"})
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0
    login(client, "admin", "admin-pass-1")   # 다른 아이디는 막히지 않는다


def test_throttle_unlocks_after_wait():
    now = [0.0]
    t = LoginThrottle(max_failures=2, lock_seconds=10, clock=lambda: now[0])
    t.failed("a"); t.failed("a")
    assert t.locked_for("a") == 10
    now[0] = 11
    assert t.locked_for("a") == 0
    t.failed("a")
    assert t.locked_for("a") == 0   # 잠금이 풀린 뒤에는 실패 수를 처음부터 센다


# ── 기록에 남는 이름은 로그인한 사람 ──

def test_reviewer_in_body_cannot_impersonate(client, app):
    login(client)
    doc = client.post("/api/documents?filename=a.pdf", content=PDF).json()
    assert doc["created_by"] == "kim"
    assert client.get("/api/documents").json()["items"][0]["created_by"] == "kim"
    store = app.state.store
    out, checks = pipeline.result_paths(store, doc["id"])
    out.parent.mkdir(parents=True)
    checks.parent.mkdir(parents=True)
    out.write_text(json.dumps(DOC, ensure_ascii=False), encoding="utf-8")
    checks.write_text("{}", encoding="utf-8")
    store.apply(doc["id"], {"type": "done", "summary": {}})
    body = {"msds_index": 0, "path": "product.name", "action": "confirm", "reviewer": "관리자"}
    assert client.put(f"/api/documents/{doc['id']}/review/fields", json=body).status_code == 200
    without_name = {k: v for k, v in body.items() if k != "reviewer"}
    assert client.put(f"/api/documents/{doc['id']}/review/fields", json=without_name).status_code == 200
    log = store.load_review(doc["id"])["log"]
    assert [e["reviewer"] for e in log] == ["김검수", "김검수"]


# ── 역할 ──

def test_reviewer_cannot_use_admin_endpoints(client):
    login(client)
    doc = client.post("/api/documents?filename=a.pdf", content=PDF).json()["id"]
    assert client.post(f"/api/documents/{doc}/results/persist").status_code == 403
    assert client.post(f"/api/documents/{doc}/handoffs").status_code == 403
    assert client.get("/api/users").status_code == 403
    assert client.post("/api/users", json={"username": "x1", "display_name": "x", "password": "12345678"}).status_code == 403


def test_admin_manages_users(client):
    login(client, "admin", "admin-pass-1")
    new = {"username": "Park", "display_name": "박검수", "password": "park-pass-1"}
    r = client.post("/api/users", json=new)
    assert r.status_code == 201 and r.json()["username"] == "park" and r.json()["role"] == "reviewer"
    assert client.post("/api/users", json=new).status_code == 409
    assert client.post("/api/users", json={**new, "username": "p2", "password": "short"}).status_code == 422
    assert [u["username"] for u in client.get("/api/users").json()["items"]] == ["admin", "kim", "park"]
    me = client.get("/api/auth/me").json()["id"]
    assert client.patch(f"/api/users/{me}", json={"role": "reviewer"}).status_code == 409   # 자기 자신
    assert client.patch(f"/api/users/{r.json()['id']}", json={"display_name": "박 검수"}).json()["display_name"] == "박 검수"
    assert client.patch("/api/users/999", json={"is_active": False}).status_code == 404


def test_role_change_and_deactivation_apply_to_existing_tokens(client, users):
    token = login(client).json()["access_token"]
    users.update(users.find("kim")[0].id, is_active=False)
    assert client.get("/api/documents", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "kim", "password": "kim-pass-12"}).status_code == 401


# ── refresh 회전과 로그아웃 ──

def test_refresh_rotates_and_reuse_revokes_everything(app, client):
    first = login(client).cookies["msds_refresh"]
    r = client.post("/api/auth/refresh")
    assert r.status_code == 200
    second = r.cookies["msds_refresh"]
    assert second != first
    bare = TestClient(app)
    reuse = bare.post("/api/auth/refresh", headers={"Cookie": f"msds_refresh={first}"})
    assert reuse.status_code == 401
    assert any(c.startswith("msds_refresh=") and "max-age=0" in c.lower() for c in reuse.headers.get_list("set-cookie"))
    # 이미 쓴 토큰이 다시 왔으므로 새 토큰도 끊긴다 (훔친 토큰 대비)
    assert bare.post("/api/auth/refresh", headers={"Cookie": f"msds_refresh={second}"}).status_code == 401


def test_logout_revokes_refresh_and_clears_cookies(client):
    login(client)
    r = client.post("/api/auth/logout")
    assert r.status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/refresh").status_code == 401
    assert client.post("/api/auth/logout").status_code == 204   # 이미 나갔어도 된다


def test_access_token_cannot_refresh(app, client):
    token = login(client).json()["access_token"]
    bare = TestClient(app)
    assert bare.post("/api/auth/refresh", headers={"Cookie": f"msds_refresh={token}"}).status_code == 401


# ── 판정 API와 첫 관리자 ──

def test_embedded_judge_router_needs_login(tmp_path, users, monkeypatch):
    monkeypatch.setenv("MSDS_JUDGE_IN_EXTRACT_APP", "1")
    monkeypatch.setattr(judge_app, "attach", lambda app: setattr(app.state, "judge_workers", object()))
    monkeypatch.setattr(judge_app, "detach", lambda app: None)
    app = extract_app.create_app(store=DocumentStore(tmp_path), worker=Worker(), static_dir=None,
                                 users=users, auth_settings=SETTINGS)
    with TestClient(app) as c:
        assert c.get("/api/judgments/summary?job_ids=").status_code == 401
        login(c)
        assert c.get("/api/judgments/summary").status_code == 422   # 로그인하면 원래 검사까지 간다


def test_first_admin_from_env_is_created_once(monkeypatch):
    store = MemoryUserStore()
    monkeypatch.setenv("MSDS_ADMIN_USERNAME", "root")
    monkeypatch.setenv("MSDS_ADMIN_PASSWORD", "root-pass-1")
    ensure_admin_from_env(store)
    ensure_admin_from_env(store)
    assert [(u.username, u.role) for u in store.list()] == [("root", "admin")]
    monkeypatch.setenv("MSDS_ADMIN_PASSWORD", "short")
    ensure_admin_from_env(store)   # 이미 있으면 비밀번호를 바꾸지 않는다
    assert verify_password(store.find("root")[1], "root-pass-1")
