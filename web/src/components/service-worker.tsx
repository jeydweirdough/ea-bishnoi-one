"use client";

import { useEffect } from "react";

const BUILD = process.env.NEXT_PUBLIC_BUILD_ID;

/** True while someone is mid-task (a dialog or the camera is open, or they're typing), so a reload would lose their work. */
const busy = () => Boolean(document.querySelector('[role="dialog"], [role="alertdialog"]')) || (document.activeElement instanceof HTMLElement && document.activeElement.matches("input, textarea, select, [contenteditable]"));

export function ServiceWorker() {
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;
    if (process.env.NODE_ENV !== "production") return;
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {
      /* offline support is progressive; the app works without it */
    });
  }, []);

  // After a deploy, a tab or installed app that stayed open keeps running the old code. Check when the app comes
  // back to the screen (and every 15 minutes) and reload onto the new build, but never in the middle of a task.
  useEffect(() => {
    if (process.env.NODE_ENV !== "production" || !BUILD) return;
    let stale = false;
    const check = async () => {
      if (document.visibilityState !== "visible") return;
      if (!stale) {
        try {
          const r = await fetch("/app-version", { cache: "no-store" });
          stale = r.ok && (await r.json()).build !== BUILD;
        } catch {
          return;
        }
      }
      if (stale && !busy()) location.reload();
    };
    document.addEventListener("visibilitychange", check);
    const t = setInterval(check, 15 * 60 * 1000);
    return () => {
      document.removeEventListener("visibilitychange", check);
      clearInterval(t);
    };
  }, []);
  return null;
}
