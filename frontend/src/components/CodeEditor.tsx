import { useEffect, useMemo, useRef } from "react";
import { tokenize } from "../highlight";

export const LINE_H = 24;
const PAD = 12;

type Props = {
  value: string; onChange: (v: string) => void;
  activeLine: number | null;          // 1-based line currently executing (null when not running)
  errorLine: number | null;
  stale: boolean;                      // true when the code was edited after the trace was recorded
  selectedLine: number | null; onSelectLine: (n: number | null) => void;
};

export function CodeEditor({ value, onChange, activeLine, errorLine, stale, selectedLine, onSelectLine }: Props) {
  const scroller = useRef<HTMLDivElement>(null);
  const ta = useRef<HTMLTextAreaElement>(null);
  const lines = useMemo(() => value.split("\n"), [value]);
  const tokens = useMemo(() => lines.map(tokenize), [lines]);
  const maxLen = Math.max(24, ...lines.map((l) => l.length)) + 6;
  const tracing = activeLine != null && !stale;

  useEffect(() => {          // keep the executing line visible, smoothly
    const sc = scroller.current;
    if (!sc || !tracing) return;
    const top = PAD + (activeLine! - 1) * LINE_H;
    if (top < sc.scrollTop + LINE_H || top + LINE_H > sc.scrollTop + sc.clientHeight - LINE_H)
      sc.scrollTo({ top: Math.max(0, top - sc.clientHeight / 2), behavior: "smooth" });
  }, [activeLine, tracing]);

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    const el = e.currentTarget;
    const { selectionStart: s, selectionEnd: en } = el;
    if (e.key === "Tab") {
      e.preventDefault();
      if (e.shiftKey) {                       // dedent current line
        const ls = value.lastIndexOf("\n", s - 1) + 1;
        const m = /^ {1,4}/.exec(value.slice(ls));
        if (m) { el.setSelectionRange(ls, ls + m[0].length); el.setRangeText("", ls, ls + m[0].length, "end"); onChange(el.value); }
      } else { el.setRangeText("    ", s, en, "end"); onChange(el.value); }
    } else if (e.key === "Enter") {
      e.preventDefault();
      const ls = value.lastIndexOf("\n", s - 1) + 1;
      const line = value.slice(ls, s);
      const indent = /^ */.exec(line)![0] + (/:\s*$/.test(line) ? "    " : "");
      el.setRangeText("\n" + indent, s, en, "end"); onChange(el.value);
    }
  }

  const h = lines.length * LINE_H + PAD * 2;
  return (
    <div className="editor" ref={scroller} data-testid="editor">
      <div className="editor-inner" style={{ height: h }}>
        <div className="gutter" style={{ height: h, paddingTop: PAD }}>
          {lines.map((_, i) => (
            <div key={i} role="button" data-testid={`gutter-${i + 1}`} title="Click to select this line, then ask the tutor to explain it" onClick={() => onSelectLine(selectedLine === i + 1 ? null : i + 1)}
              className={"gn" + (activeLine === i + 1 && tracing ? " on" : "") + (errorLine === i + 1 ? " err" : "") + (selectedLine === i + 1 ? " sel" : "")} style={{ height: LINE_H }}>
              {activeLine === i + 1 && tracing ? <span className="arrow">▶</span> : null}{i + 1}
            </div>
          ))}
        </div>
        <div className="codearea" style={{ width: `${maxLen}ch` }}>
          {tracing && <div key={activeLine} className="active-bar" data-fly-src="line" data-testid="active-bar" style={{ top: PAD + (activeLine! - 1) * LINE_H, height: LINE_H }} />}
          {selectedLine != null && selectedLine <= lines.length && <div className="sel-bar" data-testid="sel-bar" style={{ top: PAD + (selectedLine - 1) * LINE_H, height: LINE_H }} />}
          {errorLine != null && <div className="error-bar" style={{ top: PAD + (errorLine - 1) * LINE_H, height: LINE_H }} />}
          <pre className="hl" aria-hidden style={{ paddingTop: PAD }}>
            {tokens.map((tk, i) => (
              <div key={i} className={"cl" + (tracing && activeLine !== i + 1 ? " dim" : "")} style={{ height: LINE_H }}>
                {tk.map((t, j) => <span key={j} className={"t-" + t.t}>{t.s}</span>)}{"​"}
              </div>
            ))}
          </pre>
          <textarea ref={ta} className="ta" spellCheck={false} autoCapitalize="off" autoCorrect="off" wrap="off"
            aria-label="Code editor" data-testid="editor-input"
            value={value} onChange={(e) => onChange(e.target.value)} onKeyDown={onKeyDown}
            style={{ height: h, paddingTop: PAD, lineHeight: `${LINE_H}px` }} />
        </div>
      </div>
    </div>
  );
}
