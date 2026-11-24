export interface Piece { text: string; op: "same" | "add" | "del" }

/** Word level difference between two texts (longest common subsequence). Small texts only, which is all a post is. */
export function wordDiff(a: string, b: string): Piece[] {
  const x: string[] = a.split(/(\s+)/).filter(Boolean);
  const y: string[] = b.split(/(\s+)/).filter(Boolean);
  if (x.length * y.length > 250_000) return [{ text: b, op: "add" }];
  const n = x.length, m = y.length;
  const w = m + 1;
  const t = new Array<number>((n + 1) * w).fill(0);
  const at = (i: number, j: number) => t[i * w + j] ?? 0;
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) t[i * w + j] = x[i] === y[j] ? at(i + 1, j + 1) + 1 : Math.max(at(i + 1, j), at(i, j + 1));
  const out: Piece[] = [];
  const push = (text: string, op: Piece["op"]) => { const l = out[out.length - 1]; if (l && l.op === op) l.text += text; else out.push({ text, op }); };
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (x[i] === y[j]) { push(x[i] ?? "", "same"); i++; j++; }
    else if (at(i + 1, j) >= at(i, j + 1)) { push(x[i] ?? "", "del"); i++; }
    else { push(y[j] ?? "", "add"); j++; }
  }
  while (i < n) push(x[i++] ?? "", "del");
  while (j < m) push(y[j++] ?? "", "add");
  return out;
}
