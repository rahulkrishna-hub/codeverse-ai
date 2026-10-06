// Tiny single-line Python tokenizer for the editor overlay (multi-line strings are not tracked).
const KW = new Set("False None True and as assert break class continue def del elif else except finally for from global if import in is lambda nonlocal not or pass raise return try while with yield".split(" "));
const BI = new Set("print len range int str float bool list dict set tuple input abs min max sum sorted enumerate zip map filter round type isinstance".split(" "));
export type Tok = { t: "kw" | "bi" | "str" | "num" | "com" | "fn" | "op" | "id" | "ws"; s: string };

export function tokenize(line: string): Tok[] {
  const out: Tok[] = [];
  const re = /(\s+)|(#.*$)|("(?:\\.|[^"\\])*"?|'(?:\\.|[^'\\])*'?)|(\b\d+(?:\.\d+)?\b)|([A-Za-z_]\w*)|([^\sA-Za-z_\d]+)/gy;
  let m: RegExpExecArray | null;
  while (re.lastIndex < line.length && (m = re.exec(line))) {
    if (m[1]) out.push({ t: "ws", s: m[1] });
    else if (m[2]) out.push({ t: "com", s: m[2] });
    else if (m[3]) out.push({ t: "str", s: m[3] });
    else if (m[4]) out.push({ t: "num", s: m[4] });
    else if (m[5]) {
      const w = m[5]; const rest = line.slice(re.lastIndex);
      const prev = out.filter((x) => x.t !== "ws").at(-1);
      out.push({ t: KW.has(w) ? "kw" : prev?.s === "def" ? "fn" : BI.has(w) ? "bi" : /^\s*\(/.test(rest) ? "fn" : "id", s: w });
    } else out.push({ t: "op", s: m[6] });
  }
  return out;
}
