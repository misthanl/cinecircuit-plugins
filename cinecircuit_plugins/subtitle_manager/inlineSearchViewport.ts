import { preserveDialogDocumentHeight } from "./preserveDocumentHeight";

/** Apply the host's document-height fix to inline editors without opening a modal. */
export function createInlineSearchViewport() {
  let release: (() => void) | undefined;
  let restingHeight = 0;
  let focused = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  function restore() {
    if (focused || !release) return;
    if (window.visualViewport && window.visualViewport.height < restingHeight - 120) return;
    release();
    release = undefined;
    window.visualViewport?.removeEventListener("resize", restore);
    window.removeEventListener("resize", restore);
  }
  return {
    focus() {
      focused = true;
      clearTimeout(timer);
      if (release) return;
      restingHeight = window.innerHeight;
      release = preserveDialogDocumentHeight(Math.max(restingHeight, document.body.scrollHeight, document.documentElement.clientHeight));
      window.visualViewport?.addEventListener("resize", restore, { passive: true });
      window.addEventListener("resize", restore, { passive: true });
    },
    blur() {
      focused = false;
      timer = setTimeout(restore, 250);
    },
    dispose() {
      clearTimeout(timer);
      release?.();
      release = undefined;
      window.visualViewport?.removeEventListener("resize", restore);
      window.removeEventListener("resize", restore);
    },
  };
}
