import { useState } from "react";
import { LuMoon, LuSun, LuUser, LuCode } from "react-icons/lu";
import type { LangInfo, Progress } from "../types";
import { LuFlame, LuTrophy } from "react-icons/lu";

export type Page = "playground" | "learn" | "challenges" | "progress";

export function TopNav({ langs, lang, onLang, theme, onTheme, page, onPage, progress }: { langs: LangInfo[]; lang: string; onLang: (l: string) => void; theme: string; onTheme: () => void; page: Page; onPage: (p: Page) => void; progress: Progress | null }) {
  const [menu, setMenu] = useState(false);
  return (
    <header className="topnav">
      <div className="logo"><span className="logo-mark"><LuCode /></span><span>CodeVerse <b>AI</b></span></div>
      <nav aria-label="Main">
        {([["playground", "Playground"], ["learn", "Learn"], ["challenges", "Challenges"], ["progress", "Progress"]] as const).map(([k, n]) => (
          <a key={k} role="link" tabIndex={0} data-testid={`nav-${k}`} className={page === k ? "on" : ""} aria-current={page === k ? "page" : undefined}
            onClick={() => onPage(k)} onKeyDown={(e) => e.key === "Enter" && onPage(k)}>{n}</a>
        ))}
      </nav>
      <div className="nav-right">
        {progress && <span className="xpchip" data-testid="xp-chip" title="XP and day streak"><LuTrophy /> {progress.xp} XP <LuFlame /> {progress.streak}</span>}
        <select value={lang} onChange={(e) => onLang(e.target.value)} aria-label="Language" data-testid="lang-select">
          {langs.map((l) => <option key={l.id} value={l.id} disabled={l.status !== "available"}>{l.name}{l.status !== "available" ? " — coming soon" : ""}</option>)}
        </select>
        <button className="icon-btn" onClick={onTheme} aria-label="Toggle theme" data-testid="theme-toggle">{theme === "dark" ? <LuSun /> : <LuMoon />}</button>
        <div className="profile">
          <button className="icon-btn" onClick={() => setMenu(!menu)} aria-label="Profile menu"><LuUser /></button>
          {menu && <div className="menu"><b>Guest</b><span>Single local user. Progress is saved on this machine; accounts are not built yet.</span></div>}
        </div>
      </div>
    </header>
  );
}
