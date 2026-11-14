"use client";

import { useEffect, useId, useRef, useState, useSyncExternalStore } from "react";
import { Camera, CloudUpload, FolderOpen, Paperclip, TriangleAlert, X } from "lucide-react";
import { Button } from "./controls";
import { ProofCamera, canUseLiveCamera, currentFix, stampFile } from "./proof-camera";
import { cn } from "@/lib/cn";

/**
 * One way to add files everywhere in the app:
 *   - drag and drop onto the box,
 *   - paste a screenshot (Ctrl+V / Cmd+V),
 *   - Browse: the gallery on a phone, the file explorer on a computer,
 *   - Take photo: the phone's rear camera (shown on touch devices when images are allowed).
 * Files that don't match `accept` are refused with a message in the box.
 */

export const ACCEPT_DOCS = ".pdf,.png,.jpg,.jpeg,.webp,.heic,.heif,.docx,.xlsx,.csv,.txt";
export const ACCEPT_IMAGES = "image/*,.heic,.heif";

export function accepts(file: File, accept: string): boolean {
  const name = file.name.toLowerCase();
  const type = (file.type || "").toLowerCase();
  return accept
    .split(",")
    .map((a) => a.trim().toLowerCase())
    .filter(Boolean)
    .some((a) => (a.startsWith(".") ? name.endsWith(a) : a.endsWith("/*") ? type.startsWith(a.slice(0, -1)) : type === a));
}

const allowsImages = (accept: string) => ["x.jpg", "x.png"].some((n) => accepts(new File([], n, { type: n.endsWith("jpg") ? "image/jpeg" : "image/png" }), accept));

/* ---------- touch device? (Take photo only makes sense there) */
const coarse = typeof window !== "undefined" ? window.matchMedia?.("(pointer: coarse)") : undefined;
const subscribe = (cb: () => void) => {
  coarse?.addEventListener?.("change", cb);
  return () => coarse?.removeEventListener?.("change", cb);
};
export function useTouchDevice() {
  return useSyncExternalStore(subscribe, () => Boolean(coarse?.matches), () => false);
}

/* ---------- paste: the most recently shown drop box on screen takes the screenshot */
type Zone = { el: HTMLElement; take: (files: File[]) => void };
const zones: Zone[] = [];
let listening = false;
function visible(el: HTMLElement) {
  return el.isConnected && el.getClientRects().length > 0;
}
function onPaste(e: ClipboardEvent) {
  const files = Array.from(e.clipboardData?.files ?? []);
  if (!files.length) return; // plain text: leave it alone
  const active = document.activeElement as HTMLElement | null;
  const dialogs = Array.from(document.querySelectorAll<HTMLElement>('[role="dialog"]')).filter(visible);
  const top = dialogs[dialogs.length - 1];
  const candidates = zones.filter((z) => visible(z.el) && (!top || top.contains(z.el)));
  const target = candidates.find((z) => active && z.el.contains(active)) ?? candidates[candidates.length - 1];
  if (!target) return;
  e.preventDefault();
  const stamp = new Date().toISOString().slice(0, 19).replace(/[-:T]/g, "");
  target.take(files.map((f, i) => (/^image\.\w+$/i.test(f.name) || !f.name ? new File([f], `screenshot-${stamp}${files.length > 1 ? `-${i + 1}` : ""}.${(f.type.split("/")[1] || "png").replace("jpeg", "jpg")}`, { type: f.type }) : f)));
}

/** Lets a drop box take pasted screenshots: `take` gets the files when it is the box on screen. */
export function usePasteTarget(ref: React.RefObject<HTMLElement | null>, take: (files: File[]) => void) {
  const latest = useRef(take);
  useEffect(() => {
    latest.current = take;
  });
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const z: Zone = { el, take: (f) => latest.current(f) };
    zones.push(z);
    if (!listening) {
      document.addEventListener("paste", onPaste);
      listening = true;
    }
    return () => {
      zones.splice(zones.indexOf(z), 1);
    };
  }, [ref]);
}

/**
 * The drop box. `children` (previews, the chosen file) render inside it, so dropping onto them works too.
 * `compact` is a single row for panels; the default is a taller box for forms.
 */
export function FileDrop({
  accept = ACCEPT_DOCS,
  multiple = true,
  onFiles,
  busy,
  disabled,
  title,
  hint,
  camera,
  compact,
  browseLabel,
  inputLabel,
  stamp,
  className,
  children,
}: {
  accept?: string;
  multiple?: boolean;
  onFiles: (files: File[]) => void;
  busy?: boolean;
  disabled?: boolean;
  title?: React.ReactNode;
  hint?: React.ReactNode;
  /** Show "Take photo" on phones. Defaults to on when images are accepted. */
  camera?: boolean;
  compact?: boolean;
  browseLabel?: string;
  /** Accessible name of the hidden file input (tests use it). */
  inputLabel?: string;
  /** Photo proof: Take photo opens the full-screen camera and stamps date, time and location (this text is the stamp's label). */
  stamp?: string;
  className?: string;
  children?: React.ReactNode;
}) {
  const touch = useTouchDevice();
  const live = useSyncExternalStore(subscribe, canUseLiveCamera, () => false);
  const [cameraOpen, setCameraOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const browseInput = useRef<HTMLInputElement>(null);
  const cameraInput = useRef<HTMLInputElement>(null);
  const depth = useRef(0);
  const [over, setOver] = useState(false);
  const [error, setError] = useState<string>();
  const hintId = useId();
  const off = disabled || busy;

  function take(list: File[]) {
    if (off || !list.length) return;
    const ok = list.filter((f) => accepts(f, accept));
    const bad = list.filter((f) => !accepts(f, accept));
    setError(bad.length ? `${bad.length === 1 ? `"${bad[0].name}" isn't` : `${bad.length} files aren't`} a supported type.` : undefined);
    if (ok.length) onFiles(multiple ? ok : ok.slice(0, 1));
  }
  usePasteTarget(box, take);
  const pick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    e.target.value = "";
    take(files);
  };
  // The phone's own camera app: stamp what comes back.
  const pickCamera = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    e.target.value = "";
    if (!stamp) return take(files);
    const fix = await currentFix();
    take(await Promise.all(files.map((f) => stampFile(f, stamp, fix))));
  };
  const openCamera = () => (stamp && live ? setCameraOpen(true) : cameraInput.current?.click());

  const cameraOk = camera ?? allowsImages(accept);
  const withCamera = cameraOk && (touch || Boolean(stamp && live));
  const how = touch ? (withCamera ? "Take a photo or choose from your gallery or files" : "Choose from your files") : `Drag ${multiple ? "files" : "a file"} here, paste a screenshot, or browse`;
  return (
    <div
      ref={box}
      onDragEnter={(e) => {
        if (!e.dataTransfer.types.includes("Files")) return;
        e.preventDefault();
        depth.current++;
        setOver(true);
      }}
      onDragOver={(e) => {
        if (e.dataTransfer.types.includes("Files")) e.preventDefault();
      }}
      onDragLeave={() => {
        depth.current = Math.max(0, depth.current - 1);
        if (!depth.current) setOver(false);
      }}
      onDrop={(e) => {
        if (!e.dataTransfer.files?.length) return;
        e.preventDefault();
        depth.current = 0;
        setOver(false);
        take(Array.from(e.dataTransfer.files));
      }}
      aria-describedby={hintId}
      className={cn("rounded-[var(--radius-ctl)] border border-dashed transition-colors duration-150", over ? "border-ink bg-hover" : "border-edge bg-canvas", compact ? "p-2.5" : "p-3.5", disabled && "opacity-60", className)}
    >
      <input ref={browseInput} type="file" accept={accept} multiple={multiple} className="sr-only" tabIndex={-1} aria-label={inputLabel ?? (multiple ? "Upload files" : "Upload a file")} onChange={pick} />
      {cameraOk && <input ref={cameraInput} type="file" accept="image/*" capture="environment" className="sr-only" tabIndex={-1} aria-label="Take a photo" onChange={pickCamera} />}
      <div className={cn("flex gap-3", compact ? "flex-wrap items-center" : "flex-col sm:flex-row sm:items-center")}>
        {!compact && <CloudUpload className="size-6 shrink-0 text-ink-2 max-sm:hidden" strokeWidth={1.6} aria-hidden="true" />}
        <div className={cn("min-w-0 flex-1", compact && "min-w-[min(100%,15rem)]")}>
          {title && <p className="text-[13.5px] font-bold">{title}</p>}
          <p id={hintId} className="text-[12.5px] leading-snug text-ink-3">
            {over ? <span className="font-medium text-ink">Drop to add</span> : how}
            {hint ? <> · {hint}</> : null}
          </p>
        </div>
        <span className="flex shrink-0 flex-wrap gap-2">
          {withCamera && (
            <Button size="sm" variant="primary" icon={Camera} busy={busy} disabled={disabled} onClick={openCamera}>
              Take photo
            </Button>
          )}
          <Button size="sm" variant={withCamera ? "secondary" : "primary"} icon={FolderOpen} busy={busy && !withCamera} disabled={disabled || (busy && withCamera)} onClick={() => browseInput.current?.click()}>
            {browseLabel ?? (touch && allowsImages(accept) ? "Gallery / files" : "Browse")}
          </Button>
        </span>
      </div>
      {error && (
        <p role="alert" className="mt-2 flex items-center gap-1.5 text-[12.5px] text-danger">
          <TriangleAlert className="size-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" /> {error}
        </p>
      )}
      {children}
      {cameraOpen && stamp && (
        <ProofCamera
          label={stamp}
          max={multiple ? 10 : 1}
          onClose={() => setCameraOpen(false)}
          onDone={(files) => {
            setCameraOpen(false);
            take(files);
          }}
          onFallback={() => {
            setCameraOpen(false);
            cameraInput.current?.click();
          }}
        />
      )}
    </div>
  );
}

/** The file picked in a one-file box, with a way to take it out again. */
export function ChosenFile({ file, onRemove }: { file: File; onRemove: () => void }) {
  return (
    <p className="mt-2.5 flex items-center gap-2.5 rounded-[8px] border border-line bg-sheet px-3 py-2 text-[13.5px]">
      <Paperclip className="size-4 shrink-0 text-ink-3" strokeWidth={1.75} aria-hidden="true" />
      <span className="min-w-0 flex-1 truncate font-medium">{file.name}</span>
      <span className="tabular shrink-0 text-[12px] text-ink-3">{file.size < 1024 * 1024 ? `${Math.max(1, Math.round(file.size / 1024))} KB` : `${(file.size / 1024 / 1024).toFixed(1)} MB`}</span>
      <button type="button" onClick={onRemove} aria-label={`Remove ${file.name}`} className="-mr-1 flex size-8 shrink-0 items-center justify-center rounded-full text-ink-2 hover:bg-hover hover:text-ink">
        <X className="size-4" strokeWidth={1.75} />
      </button>
    </p>
  );
}
