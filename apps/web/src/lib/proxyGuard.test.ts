import assert from "node:assert/strict";
import { test } from "node:test";
import { bodyAllowed, readLimited, safePath } from "./proxyGuard.ts";

test("ordinary paths pass and the private ones never do", () => {
  assert.equal(safePath(["drafts", "12"]), "drafts/12");
  assert.equal(safePath(["approvals", "7", "decide"]), "approvals/7/decide");
  assert.equal(safePath(["auth", "me"]), "auth/me");
  for (const bad of [["auth", "login"], ["Auth", "login"], ["auth", "login", "x"], ["webhooks", "lead"], ["tools", "x"], ["public", "r", "abc"], ["Public", "r", "abc"]]) assert.equal(safePath(bad), null, bad.join("/"));
});

test("dot segments and encoded tricks are refused", () => {
  for (const bad of [[".", "auth", "login"], ["..", "health"], ["drafts", ".."], ["a/b"], ["a\\b"], ["%2e"], ["%2e%2e"], ["drafts", "1%2f2"], ["a\u0000b"], [""], []]) {
    assert.equal(safePath(bad), null, JSON.stringify(bad));
  }
});

test("a segment that would become a query, a fragment or a parameter once decoded is refused", () => {
  // the framework decodes a segment before it reaches the guard: "login%3F" arrives as "login?"
  for (const bad of [["auth", "login?"], ["auth", "login#"], ["auth", "login;x"], ["auth", "login "], ["auth", "login\u007f"], ["auth", "login\u0085"], ["drafts", "1?x=1"], ["a#b"], ["a b"], ["a\tb"], ["a;b"]]) {
    assert.equal(safePath(bad), null, JSON.stringify(bad));
  }
  assert.equal(safePath(["drafts", "12"]), "drafts/12");
  assert.equal(safePath(["performance"]), "performance");
});

test("a declared length over the limit is refused before reading", () => {
  assert.equal(bodyAllowed(null, 10), true);
  assert.equal(bodyAllowed("10", 10), true);
  assert.equal(bodyAllowed("11", 10), false);
  assert.equal(bodyAllowed("abc", 10), false);
  assert.equal(bodyAllowed("-5", 10), false);
});

test("a body is cut off at the limit even when it did not say how long it is", async () => {
  const big = new Request("http://x.test/", { method: "POST", body: "x".repeat(50) });
  big.headers.delete("content-length");
  assert.equal(await readLimited(big, 10), null);
  const small = new Request("http://x.test/", { method: "POST", body: "hello" });
  const got = await readLimited(small, 10);
  assert.equal(new TextDecoder().decode(got!), "hello");
});
