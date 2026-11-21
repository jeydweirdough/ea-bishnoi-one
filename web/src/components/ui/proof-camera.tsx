"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Camera, CameraOff, Check, MapPin, MapPinOff, RotateCcw, SwitchCamera, X } from "lucide-react";

/**
 * Photo proof for transactions. The in-app camera fills the screen, takes several shots in a row, and
 * stamps each one with the date, time and (if the person allows it) the location, burned into the
 * picture like a timestamp camera. If the browser can't open the camera (no permission, no HTTPS),
 * the phone's own camera opens instead and the stamp is added after.
 * Photos chosen from the gallery are not stamped: they are marked "uploaded", not "taken".
 */

export type ProofMeta = { source: "camera" | "upload"; taken_at?: string; lat?: number; lng?: number; accuracy_m?: number };
export type Proof = { id: number; thumb: string; full: string; meta: ProofMeta; uploaded_by?: { name: string } | null; uploaded_at?: string };

/** What each chosen file is: read when uploading. */
export const proofMeta = new WeakMap<File, ProofMeta>();

type Fix = { lat: number; lng: number; accuracy: number } | null;

function useLocation(on: boolean) {
  const [fix, setFix] = useState<Fix>(null);
  const [state, setState] = useState<"waiting" | "ok" | "off">("waiting");
  useEffect(() => {
    if (!on) return;
    if (!("geolocation" in navigator)) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- no location on this device
      setState("off");
      return;
    }
    const id = navigator.geolocation.watchPosition(
      (p) => {
        setFix({ lat: p.coords.latitude, lng: p.coords.longitude, accuracy: p.coords.accuracy });
        setState("ok");
      },
      () => setState("off"),
      { enableHighAccuracy: true, maximumAge: 10000, timeout: 20000 },
    );
    return () => navigator.geolocation.clearWatch(id);
  }, [on]);
  return { fix, state };
}

const two = (n: number) => String(n).padStart(2, "0");
export function stampTime(d: Date) {
  const off = -d.getTimezoneOffset();
  const tz = `GMT${off >= 0 ? "+" : "−"}${Math.floor(Math.abs(off) / 60)}${off % 60 ? `:${two(Math.abs(off) % 60)}` : ""}`;
  return `${d.toLocaleDateString("en-PH", { weekday: "short", year: "numeric", month: "short", day: "numeric" })} · ${d.toLocaleTimeString("en-PH", { hour: "numeric", minute: "2-digit", second: "2-digit" })} (${tz})`;
}
export function stampPlace(lat?: number, lng?: number, acc?: number) {
  if (lat === undefined || lng === undefined) return "Location not shared";
  return `${Math.abs(lat).toFixed(5)}° ${lat >= 0 ? "N" : "S"}, ${Math.abs(lng).toFixed(5)}° ${lng >= 0 ? "E" : "W"}${acc ? ` · ±${Math.round(acc)} m` : ""}`;
}

/** Draws the picture with the stamp band at the bottom and returns a JPEG file with its details. */
async function stamped(src: CanvasImageSource, w: number, h: number, label: string, fix: Fix, at = new Date()): Promise<File> {
  const k = Math.min(1, 2560 / Math.max(w, h));
  const cw = Math.round(w * k);
  const ch = Math.round(h * k);
  const c = document.createElement("canvas");
  c.width = cw;
  c.height = ch;
  const g = c.getContext("2d")!;
  g.drawImage(src, 0, 0, cw, ch);
  const fs = Math.max(14, Math.round(Math.min(cw, ch) * 0.034));
  const lines = [stampTime(at), stampPlace(fix?.lat, fix?.lng, fix?.accuracy), `Executive Admin · ${label}`];
  const pad = Math.round(fs * 0.8);
  const band = pad * 2 + fs * 1.35 * lines.length;
  const grad = g.createLinearGradient(0, ch - band - fs * 2, 0, ch);
  grad.addColorStop(0, "rgba(0,0,0,0)");
  grad.addColorStop(0.35, "rgba(0,0,0,0.55)");
  grad.addColorStop(1, "rgba(0,0,0,0.78)");
  g.fillStyle = grad;
  g.fillRect(0, ch - band - fs * 2, cw, band + fs * 2);
  g.fillStyle = "#fff";
  g.textBaseline = "alphabetic";
  lines.forEach((t, i) => {
    g.font = `${i === 0 ? 700 : 500} ${i === 0 ? fs : Math.round(fs * 0.86)}px Poppins, system-ui, sans-serif`;
    g.fillText(t, pad, ch - band + pad + fs * 1.35 * (i + 0.85), cw - pad * 2);
  });
  const blob = await new Promise<Blob | null>((r) => c.toBlob(r, "image/jpeg", 0.9));
  const stamp = at.toISOString().slice(0, 19).replace(/[-:T]/g, "");
  const f = new File([blob!], `proof-${stamp}.jpg`, { type: "image/jpeg" });
  proofMeta.set(f, { source: "camera", taken_at: at.toISOString(), ...(fix ? { lat: fix.lat, lng: fix.lng, accuracy_m: Math.round(fix.accuracy) } : {}) });
  return f;
}

/** An ordinary photo (item photos, documents): no stamp, no location. Drawn through a canvas, so hidden photo data is left behind. */
async function plain(src: CanvasImageSource, w: number, h: number, at = new Date()): Promise<File> {
  const k = Math.min(1, 2560 / Math.max(w, h));
  const c = document.createElement("canvas");
  c.width = Math.round(w * k);
  c.height = Math.round(h * k);
  c.getContext("2d")!.drawImage(src, 0, 0, c.width, c.height);
  const blob = await new Promise<Blob | null>((r) => c.toBlob(r, "image/jpeg", 0.9));
  const f = new File([blob!], `photo-${at.toISOString().slice(0, 19).replace(/[-:T]/g, "")}.jpg`, { type: "image/jpeg" });
  proofMeta.set(f, { source: "camera", taken_at: at.toISOString() });
  return f;
}

/** A photo from the phone's own camera app, stamped after it comes back. */
export async function stampFile(file: File, label: string, fix: Fix): Promise<File> {
  try {
    const bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
    const f = await stamped(bmp, bmp.width, bmp.height, label, fix);
    bmp.close();
    return f;
  } catch {
    proofMeta.set(file, { source: "camera", taken_at: new Date().toISOString() });
    return file;
  }
}

export const canUseLiveCamera = () => typeof navigator !== "undefined" && Boolean(navigator.mediaDevices?.getUserMedia) && typeof window !== "undefined" && window.isSecureContext;

/** Why the in-app camera couldn't start, in plain words. */
function cameraProblem(e: unknown): string {
  const name = (e as { name?: string })?.name;
  if (name === "NotAllowedError" || name === "SecurityError") return "Camera access is blocked for this site. Allow the camera in your browser's site settings (the icon next to the address), then tap Try again.";
  if (name === "NotFoundError" || name === "OverconstrainedError") return "No camera was found on this device.";
  if (name === "NotReadableError" || name === "AbortError") return "Another app is using the camera. Close it, then tap Try again.";
  return "The camera couldn't start. Tap Try again.";
}

/**
 * The full-screen camera. With a `label` (photo proof) each shot is stamped with date, time and location;
 * without one (item photos, documents) it takes plain photos and doesn't ask for the location.
 */
export function ProofCamera({ label, max, onDone, onClose, onFallback }: { label?: string; max: number; onDone: (files: File[]) => void; onClose: () => void; onFallback: () => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const [facing, setFacing] = useState<"environment" | "user">("environment");
  const [shots, setShots] = useState<{ file: File; url: string }[]>([]);
  const [flash, setFlash] = useState(false);
  const [now, setNow] = useState(() => new Date());
  const [ready, setReady] = useState(false);
  const [problem, setProblem] = useState<string>();
  const [attempt, setAttempt] = useState(0);
  const { fix, state } = useLocation(Boolean(label));
  const fallback = useRef(onFallback);
  useEffect(() => {
    fallback.current = onFallback;
  });

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    let off = false;
    navigator.mediaDevices
      .getUserMedia({ audio: false, video: { facingMode: { ideal: facing }, width: { ideal: 4096 }, height: { ideal: 3072 } } })
      .then((s) => {
        if (off) return s.getTracks().forEach((t) => t.stop());
        stream.current = s;
        if (video.current) {
          video.current.srcObject = s;
          void video.current.play().then(() => setReady(true));
        }
      })
      // Stay in the app and say what's wrong; the phone's camera app is only used if the person asks for it.
      .catch((e) => !off && setProblem(cameraProblem(e)));
    return () => {
      off = true;
      stream.current?.getTracks().forEach((t) => t.stop());
      stream.current = null;
      setReady(false);
    };
  }, [facing, attempt]);

  useEffect(() => {
    document.body.style.overflow = "hidden";
    // Escape closes the camera only, not the form behind it.
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
    };
    document.addEventListener("keydown", onKey, true);
    return () => {
      document.body.style.overflow = "";
      document.removeEventListener("keydown", onKey, true);
    };
  }, [onClose]);

  const shoot = useCallback(async () => {
    const v = video.current;
    if (!v || !v.videoWidth || shots.length >= max) return;
    setFlash(true);
    setTimeout(() => setFlash(false), 120);
    const f = label ? await stamped(v, v.videoWidth, v.videoHeight, label, fix) : await plain(v, v.videoWidth, v.videoHeight);
    setShots((cur) => [...cur, { file: f, url: URL.createObjectURL(f) }]);
  }, [fix, label, max, shots.length]);

  useEffect(() => () => shots.forEach((s) => URL.revokeObjectURL(s.url)), [shots]);

  return (
    <div role="dialog" aria-modal="true" aria-label="Camera" className="fixed inset-0 z-[60] flex flex-col bg-black text-white">
      <div className="relative min-h-0 flex-1 overflow-hidden">
        <video ref={video} playsInline muted className="absolute inset-0 size-full object-cover" aria-label="Camera preview" />
        {flash && <div className="absolute inset-0 bg-white/70" aria-hidden="true" />}
        <div className="absolute inset-x-0 top-0 flex items-center justify-between gap-2 bg-gradient-to-b from-black/60 to-transparent px-3 pt-[max(env(safe-area-inset-top),12px)] pb-6">
          <button type="button" onClick={onClose} aria-label="Close the camera" className="flex size-11 items-center justify-center rounded-full bg-black/40">
            <X className="size-5" strokeWidth={1.75} />
          </button>
          <span className="rounded-full bg-black/40 px-3 py-1 text-[12.5px] font-medium">{label ?? "Camera"}</span>
          <button type="button" onClick={() => setFacing((f) => (f === "environment" ? "user" : "environment"))} aria-label="Switch camera" className="flex size-11 items-center justify-center rounded-full bg-black/40">
            <SwitchCamera className="size-5" strokeWidth={1.75} />
          </button>
        </div>
        {/* What will be stamped on the photo */}
        {label && (
        <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/75 to-transparent px-4 pt-10 pb-3 text-[13px] leading-snug">
          <p className="font-bold">{stampTime(now)}</p>
          <p className="flex items-center gap-1.5 text-white/85">
            {state === "off" ? <MapPinOff className="size-3.5" strokeWidth={2} aria-hidden="true" /> : <MapPin className="size-3.5" strokeWidth={2} aria-hidden="true" />}
            {state === "waiting" ? "Finding your location…" : stampPlace(fix?.lat, fix?.lng, fix?.accuracy)}
          </p>
        </div>
        )}
        {!ready && !problem && <p className="absolute inset-0 flex items-center justify-center text-[14px] text-white/70">Opening the camera…</p>}
        {problem && (
          <div role="alert" className="absolute inset-0 flex flex-col items-center justify-center gap-4 px-6 text-center">
            <CameraOff className="size-8 text-white/80" strokeWidth={1.6} aria-hidden="true" />
            <p className="max-w-[30ch] text-[14.5px] leading-snug">{problem}</p>
            <div className="flex flex-wrap justify-center gap-2">
              <button
                type="button"
                onClick={() => {
                  setProblem(undefined);
                  setAttempt((n) => n + 1);
                }}
                className="inline-flex h-11 items-center gap-1.5 rounded-full bg-white px-5 text-[14px] font-bold text-black"
              >
                <RotateCcw className="size-4" strokeWidth={2.25} aria-hidden="true" /> Try again
              </button>
              <button type="button" onClick={() => fallback.current()} className="inline-flex h-11 items-center rounded-full border border-white/40 px-5 text-[14px] font-medium">
                Use phone camera
              </button>
            </div>
          </div>
        )}
      </div>
      <div className="flex shrink-0 items-center justify-between gap-3 px-4 pt-3 pb-[max(env(safe-area-inset-bottom),16px)]">
        <ul className="no-scrollbar flex min-w-0 flex-1 gap-1.5 overflow-x-auto" aria-label="Photos taken">
          {shots.map((s, i) => (
            <li key={s.url} className="relative shrink-0">
              {/* eslint-disable-next-line @next/next/no-img-element -- local preview */}
              <img src={s.url} alt={`Shot ${i + 1}`} className="size-12 rounded-[8px] border border-white/30 object-cover" />
              <button type="button" onClick={() => setShots((cur) => cur.filter((_, j) => j !== i))} aria-label={`Remove shot ${i + 1}`} className="absolute -right-1.5 -top-1.5 flex size-5 items-center justify-center rounded-full bg-white text-black">
                <X className="size-3" strokeWidth={2.5} />
              </button>
            </li>
          ))}
        </ul>
        <button type="button" onClick={shoot} disabled={!ready || shots.length >= max} aria-label="Take the photo" className="flex size-[72px] shrink-0 items-center justify-center rounded-full border-4 border-white bg-white/20 transition-transform active:scale-95 disabled:opacity-40">
          <Camera className="size-7" strokeWidth={1.75} />
        </button>
        <span className="flex min-w-0 flex-1 justify-end">
          <button
            type="button"
            disabled={!shots.length}
            onClick={() => onDone(shots.map((s) => s.file))}
            className="inline-flex h-11 items-center gap-1.5 rounded-full bg-white px-4 text-[14px] font-bold text-black disabled:opacity-40"
          >
            <Check className="size-4" strokeWidth={2.5} aria-hidden="true" /> Done{shots.length ? ` (${shots.length})` : ""}
          </button>
        </span>
      </div>
    </div>
  );
}

/** The fix to stamp on a photo from the phone's own camera (best effort, a few seconds at most). */
export function currentFix(): Promise<Fix> {
  return new Promise((resolve) => {
    if (!("geolocation" in navigator)) return resolve(null);
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ lat: p.coords.latitude, lng: p.coords.longitude, accuracy: p.coords.accuracy }),
      () => resolve(null),
      { enableHighAccuracy: true, maximumAge: 30000, timeout: 6000 },
    );
  });
}
