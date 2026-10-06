/** Animate a value chip from one element's rect to another's (Web Animations API). */
export function flyChip(from: DOMRect, to: DOMRect, text: string, speed: number) {
  const el = document.createElement("div");
  el.className = "fly-chip"; el.textContent = text; el.setAttribute("data-testid", "fly-chip");
  document.body.appendChild(el);
  const w = el.offsetWidth;
  const x1 = from.left + from.width / 2 - w / 2, y1 = from.top + from.height / 2 - 12;
  const x2 = to.left + 16, y2 = to.top + to.height / 2 - 12;
  const dur = Math.max(250, 900 / Math.min(speed, 3));
  const a = el.animate(
    [{ transform: `translate(${x1}px,${y1}px) scale(1)`, opacity: 0 },
     { transform: `translate(${x1}px,${y1}px) scale(1.15)`, opacity: 1, offset: 0.15 },
     { transform: `translate(${(x1 + x2) / 2}px,${Math.min(y1, y2) - 40}px) scale(1.1)`, opacity: 1, offset: 0.6 },
     { transform: `translate(${x2}px,${y2}px) scale(0.8)`, opacity: 0.2 }],
    { duration: dur, easing: "cubic-bezier(.4,0,.2,1)", fill: "forwards" });
  a.onfinish = a.oncancel = () => el.remove();
}
