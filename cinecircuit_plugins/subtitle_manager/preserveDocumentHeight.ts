// Reused unchanged from host frontend/src/dialogDocumentHeight.ts; no host edits.
/** Keep a short background document from following keyboard viewport shrink.
 * This does not set dialog geometry, move scroll position or handle input. */
export function preserveDialogDocumentHeight(initialHeight?: number): () => void {
  if (!initialHeight || !window.matchMedia?.("(max-width: 959px)").matches
    || !(/iP(?:hone|ad|od)/.test(navigator.userAgent)
      || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1))) return () => {};
  const targets = [document.documentElement, document.body].map((element) => ({
    element,
    value: element.style.getPropertyValue("min-height"),
    priority: element.style.getPropertyPriority("min-height"),
  }));
  let applied = "";
  let width = window.innerWidth;
  function restore() {
    for (const { element, value, priority } of targets) {
      // Respect unrelated changes made by another owner while the modal is open.
      if (element.style.getPropertyValue("min-height") !== applied
        || element.style.getPropertyPriority("min-height") !== "important") continue;
      if (value) element.style.setProperty("min-height", value, priority);
      else element.style.removeProperty("min-height");
    }
  }
  function apply(height: number) {
    applied = `${Math.ceil(height)}px`;
    targets.forEach(({ element }) => element.style.setProperty("min-height", applied, "important"));
  }
  function resize() {
    if (width === window.innerWidth) return; // Keyboard height changes must not lower the floor.
    width = window.innerWidth;
    restore();
    if (window.matchMedia("(max-width: 959px)").matches) {
      apply(Math.max(window.innerHeight, document.body.scrollHeight, document.documentElement.clientHeight));
    }
  }
  apply(initialHeight);
  window.addEventListener("resize", resize, { passive: true });
  return () => {
    window.removeEventListener("resize", resize);
    restore();
  };
}
