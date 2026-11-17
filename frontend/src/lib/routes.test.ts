/* node --test 로 돈다 (pnpm test). */
import assert from "node:assert/strict";
import { test } from "node:test";
import { routes, safeNext } from "./routes.ts";

test("로그인 뒤 돌아갈 곳은 이 사이트 안의 경로만 받는다", () => {
  assert.equal(safeNext("/review/?doc=U-1&tab=hazard"), "/review/?doc=U-1&tab=hazard");
  for (const bad of [null, undefined, "", "https://evil.example", "//evil.example/x", "/\\evil.example", "javascript:alert(1)"]) {
    assert.equal(safeNext(bad), "/", String(bad));
  }
  assert.equal(safeNext("/login/?next=/x"), "/"); // 로그인 화면으로 되돌아가 맴돌지 않는다
});

test("로그인 주소는 돌아갈 곳이 있을 때만 next 를 단다", () => {
  assert.equal(routes.login(), "/login/");
  assert.equal(routes.login("/"), "/login/");
  assert.equal(routes.login("/extract/?doc=U-1"), "/login/?next=%2Fextract%2F%3Fdoc%3DU-1");
});
