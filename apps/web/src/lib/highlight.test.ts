import assert from "node:assert/strict";
import { test } from "node:test";
import { buildSpans, codePoints, segments } from "./highlight.ts";

const flag = (start: number, end: number) => ({ kind: "banned_phrase", start, end, text: "", message: "m" });

test("a mark after an emoji sits on the right word", () => {
  const text = "Hi \u{1F600} we leverage synergy now"; // the emoji is 2 UTF-16 units but 1 position for the API
  const start = Array.from("Hi \u{1F600} we ").length; // the API's position of "leverage"
  const out = segments(text, buildSpans(codePoints(text).length, [], [flag(start, start + "leverage".length)], []));
  assert.deepEqual(out.map((s) => [s.text, Boolean(s.span)]), [["Hi \u{1F600} we ", false], ["leverage", true], [" synergy now", false]]);
  assert.notEqual(text.slice(start, start + 8), "leverage", "slicing the string by those positions would be wrong");
});

test("several emoji before a mark do not shift it", () => {
  const text = "\u{1F600}\u{1F600}\u{1F600}\u{1F600} unlock the value";
  const start = 5;
  const out = segments(text, buildSpans(codePoints(text).length, [], [flag(start, start + 6)], []));
  assert.equal(out.find((s) => s.span)?.text, "unlock");
});

test("plain text, no marks, and marks outside the text", () => {
  assert.deepEqual(segments("plain", []), [{ text: "plain" }]);
  assert.deepEqual(buildSpans(5, [], [flag(3, 99), flag(-1, 2), flag(2, 2)], []), []);
  assert.equal(segments("\u{1F600}", []).map((s) => s.text).join(""), "\u{1F600}");
});

test("overlapping marks keep the first and the text is never lost", () => {
  const text = "one two three four";
  const spans = buildSpans(codePoints(text).length, [], [flag(0, 7), flag(4, 13)], []);
  assert.equal(spans.length, 1);
  assert.equal(segments(text, spans).map((s) => s.text).join(""), text);
});
