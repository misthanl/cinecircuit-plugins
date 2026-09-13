/** Read the host shell's actual edges, including iOS safe-area padding. */
export function trackWorkspaceBounds(root: HTMLElement) {
  let frame = 0;
  const observed = new Set<Element>();
  const observer = new ResizeObserver(schedule);
  function update() {
    frame = 0;
    for (const [selector, property, edge] of [
      [".mobile-shell-bar", "--subtitle-workspace-top", "top"],
      [".mobile-shell-dock", "--subtitle-workspace-bottom", "bottom"],
    ] as const) {
      const element = document.querySelector<HTMLElement>(selector);
      if (!element || !element.getClientRects().length) {
        root.style.removeProperty(property);
        continue;
      }
      if (!observed.has(element)) { observed.add(element); observer.observe(element); }
      const rect = element.getBoundingClientRect();
      const inset = edge === "top" ? rect.bottom + 12 : window.innerHeight - rect.top + 6;
      root.style.setProperty(property, `${Math.max(0, inset)}px`);
    }
  }
  function schedule() {
    if (!frame) frame = requestAnimationFrame(update);
  }
  const additions = new MutationObserver(schedule);
  additions.observe(document.body, { childList: true, subtree: true });
  window.addEventListener("resize", schedule, { passive: true });
  window.visualViewport?.addEventListener("resize", schedule, { passive: true });
  update();
  return () => {
    cancelAnimationFrame(frame);
    observer.disconnect();
    additions.disconnect();
    window.removeEventListener("resize", schedule);
    window.visualViewport?.removeEventListener("resize", schedule);
  };
}
