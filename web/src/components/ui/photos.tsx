"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, Star, Trash2, X, type LucideIcon } from "lucide-react";
import { api, invalidate, useApi, type ApiError } from "@/lib/api";
import { Panel, useToast } from "@/components/ui/feedback";
import { cn } from "@/lib/cn";
import { ACCEPT_IMAGES, FileDrop } from "./file-drop";

export type PhotoOwner = "asset" | "vehicle" | "inventory_item";
type Photo = { id: number; thumb: string; full: string; main: boolean };

const MAX = 8;

/**
 * Shrinks a camera photo on the phone before upload (long side 2000 px, JPEG), so uploads are
 * quick on mobile data. The server re-encodes it again and strips location and camera data.
 * If the browser can't decode the file (e.g. HEIC on some browsers), the original is sent.
 */
export async function shrink(file: File, max = 2000): Promise<File> {
  try {
    const bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
    const k = Math.min(1, max / Math.max(bmp.width, bmp.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bmp.width * k);
    canvas.height = Math.round(bmp.height * k);
    canvas.getContext("2d")!.drawImage(bmp, 0, 0, canvas.width, canvas.height);
    bmp.close();
    const blob = await new Promise<Blob | null>((r) => canvas.toBlob(r, "image/jpeg", 0.85));
    return blob ? new File([blob], "photo.jpg", { type: "image/jpeg" }) : file;
  } catch {
    return file;
  }
}

export async function uploadPhoto(ownerType: PhotoOwner, ownerId: number, file: File) {
  const fd = new FormData();
  fd.set("owner_type", ownerType);
  fd.set("owner_id", String(ownerId));
  fd.set("file", await shrink(file));
  return api<Photo>("/api/v1/photos", { method: "POST", body: fd });
}

/** List thumbnail: the item's main photo, or its icon when it has none. */
export function ItemThumb({ src, icon: Icon, size = "md", className }: { src?: string | null; icon: LucideIcon; size?: "md" | "lg"; className?: string }) {
  const box = size === "lg" ? "size-16 rounded-[12px]" : "size-12 rounded-[10px]";
  if (!src)
    return (
      <span className={cn("flex shrink-0 items-center justify-center border border-line bg-sheet", box, className)} aria-hidden="true">
        <Icon className={size === "lg" ? "size-6" : "size-5"} strokeWidth={1.6} />
      </span>
    );
  return (
    // eslint-disable-next-line @next/next/no-img-element -- private, cookie-protected API image
    <img src={src} alt="" loading="lazy" decoding="async" className={cn("shrink-0 border border-line bg-canvas object-cover", box, className)} />
  );
}

/**
 * The item's photos, like a shop listing: a large main photo, a strip of the others, and
 * (for staff) Take photo / Upload. Tapping a photo opens it full size, where staff can make it
 * the main photo or remove it.
 */
export function PhotoGallery({ ownerType, ownerId, canEdit, onChange }: { ownerType: PhotoOwner; ownerId: number; canEdit: boolean; onChange?: () => void }) {
  const toast = useToast();
  const list = useApi<Photo[]>(`/api/v1/photos?owner_type=${ownerType}&owner_id=${ownerId}`);
  const [busy, setBusy] = useState(false);
  const [viewing, setViewing] = useState<number | null>(null);
  const photos = list.data ?? [];
  const main = photos.find((p) => p.main) ?? photos[0];
  const ordered = main ? [main, ...photos.filter((p) => p.id !== main.id)] : [];

  async function add(files: File[]) {
    const room = MAX - photos.length;
    if (room <= 0) return toast(`An item can have at most ${MAX} photos. Remove one first.`, "error");
    setBusy(true);
    let added = 0;
    for (const f of files.slice(0, room)) {
      try {
        await uploadPhoto(ownerType, ownerId, f);
        added++;
      } catch (e) {
        toast((e as ApiError).message, "error");
      }
    }
    if (files.length > room) toast(`Only ${room} more photo${room === 1 ? "" : "s"} fit. The rest were skipped.`, "error");
    setBusy(false);
    if (added) {
      toast(added === 1 ? "Photo added" : `${added} photos added`);
      list.reload();
      invalidate();
      onChange?.();
    }
  }

  if (!list.data) return <div className="aspect-[4/3] w-full animate-pulse rounded-[var(--radius-panel)] border border-line bg-sheet" aria-hidden="true" />;

  return (
    <Panel title="Photos" meta={photos.length ? `${photos.length}` : undefined}>
      {ordered.length === 0 ? (
        canEdit ? (
          <div className="p-3 sm:p-4">
            <FileDrop accept={ACCEPT_IMAGES} onFiles={add} busy={busy} inputLabel="Upload photos" title="Add a photo" hint="so everyone knows exactly what this item looks like" />
          </div>
        ) : (
          <p className="px-5 py-8 text-center text-[13.5px] text-ink-2">No photo of this item yet.</p>
        )
      ) : (
        <div className="p-3 sm:p-4">
          <button type="button" onClick={() => setViewing(0)} className="block w-full overflow-hidden rounded-[10px] border border-line bg-canvas" aria-label="Open the main photo">
            {/* eslint-disable-next-line @next/next/no-img-element -- private API image */}
            <img src={ordered[0].full} alt="Main photo" className="aspect-[4/3] w-full object-cover" />
          </button>
          {ordered.length > 1 && (
            <ul className="no-scrollbar mt-2 flex gap-2 overflow-x-auto" aria-label="More photos">
              {ordered.slice(1).map((p, i) => (
                <li key={p.id} className="shrink-0">
                  <button type="button" onClick={() => setViewing(i + 1)} aria-label={`Open photo ${i + 2}`} className="block overflow-hidden rounded-[8px] border border-line">
                    {/* eslint-disable-next-line @next/next/no-img-element -- private API image */}
                    <img src={p.thumb} alt="" loading="lazy" className="size-16 object-cover" />
                  </button>
                </li>
              ))}
            </ul>
          )}
          {canEdit && photos.length < MAX && (
            <FileDrop accept={ACCEPT_IMAGES} onFiles={add} busy={busy} compact inputLabel="Upload photos" className="mt-3" />
          )}
        </div>
      )}
      {viewing !== null && ordered[viewing] && (
        <Viewer
          photos={ordered}
          index={viewing}
          onIndex={setViewing}
          onClose={() => setViewing(null)}
          canEdit={canEdit}
          onChanged={() => {
            list.reload();
            invalidate();
            onChange?.();
          }}
        />
      )}
    </Panel>
  );
}

/** Full-screen photo viewer: swipe or arrow keys between photos. */
export function Viewer({ photos, index, onIndex, onClose, canEdit, onChanged }: { photos: Photo[]; index: number; onIndex: (i: number) => void; onClose: () => void; canEdit: boolean; onChanged: () => void }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const touch = useRef<number | null>(null);
  const p = photos[index];
  const go = (d: number) => onIndex((index + d + photos.length) % photos.length);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowRight") onIndex((index + 1) % photos.length);
      if (e.key === "ArrowLeft") onIndex((index - 1 + photos.length) % photos.length);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [index, photos.length, onClose, onIndex]);

  async function act(kind: "main" | "remove") {
    setBusy(true);
    try {
      if (kind === "main") await api(`/api/v1/photos/${p.id}/main`, { method: "POST" });
      else await api(`/api/v1/photos/${p.id}`, { method: "DELETE" });
      toast(kind === "main" ? "Main photo changed" : "Photo removed");
      onChanged();
      onClose();
    } catch (e) {
      toast((e as ApiError).message, "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div role="dialog" aria-modal="true" aria-label={`Photo ${index + 1} of ${photos.length}`} className="fixed inset-0 z-50 flex flex-col bg-black/95 text-white">
      <div className="flex shrink-0 items-center justify-between gap-3 px-3 pt-[max(env(safe-area-inset-top),12px)] pb-2">
        <span className="tabular px-2 text-[13px] text-white/70">
          {index + 1} / {photos.length}
          {p.main ? " · Main photo" : ""}
        </span>
        <button type="button" onClick={onClose} aria-label="Close" className="flex size-11 items-center justify-center rounded-full hover:bg-white/10">
          <X className="size-5" strokeWidth={1.75} />
        </button>
      </div>
      <div
        className="relative flex min-h-0 flex-1 items-center justify-center px-2"
        onTouchStart={(e) => (touch.current = e.touches[0].clientX)}
        onTouchEnd={(e) => {
          if (touch.current === null) return;
          const dx = e.changedTouches[0].clientX - touch.current;
          touch.current = null;
          if (Math.abs(dx) > 50) go(dx < 0 ? 1 : -1);
        }}
      >
        {/* eslint-disable-next-line @next/next/no-img-element -- private API image */}
        <img src={p.full} alt={`Photo ${index + 1}`} className="max-h-full max-w-full object-contain" />
        {photos.length > 1 && (
          <>
            <button type="button" onClick={() => go(-1)} aria-label="Previous photo" className="absolute left-2 hidden size-11 items-center justify-center rounded-full bg-white/10 hover:bg-white/20 sm:flex">
              <ChevronLeft className="size-5" strokeWidth={1.75} />
            </button>
            <button type="button" onClick={() => go(1)} aria-label="Next photo" className="absolute right-2 hidden size-11 items-center justify-center rounded-full bg-white/10 hover:bg-white/20 sm:flex">
              <ChevronRight className="size-5" strokeWidth={1.75} />
            </button>
          </>
        )}
      </div>
      {canEdit && (
        <div className="flex shrink-0 justify-center gap-2 px-3 pt-2 pb-[max(env(safe-area-inset-bottom),14px)]">
          {!p.main && (
            <button type="button" disabled={busy} onClick={() => act("main")} className="inline-flex h-11 items-center gap-2 rounded-[var(--radius-ctl)] bg-white px-4 text-[14px] font-medium text-ink disabled:opacity-60">
              <Star className="size-4" strokeWidth={1.75} aria-hidden="true" /> Make main photo
            </button>
          )}
          <button type="button" disabled={busy} onClick={() => act("remove")} className="inline-flex h-11 items-center gap-2 rounded-[var(--radius-ctl)] border border-white/30 px-4 text-[14px] font-medium text-white hover:bg-white/10 disabled:opacity-60">
            <Trash2 className="size-4" strokeWidth={1.75} aria-hidden="true" /> Remove
          </button>
        </div>
      )}
    </div>
  );
}

/** Photos chosen while creating a record; they are uploaded once the record is saved. */
export function PendingPhotos({ files, onChange, max = MAX, note = "what the item looks like", title = "Photos", showMain = true }: { files: File[]; onChange: (f: File[]) => void; max?: number; note?: string; title?: string; showMain?: boolean }) {
  const [urls, setUrls] = useState<string[]>([]);
  useEffect(() => {
    const u = files.map((f) => URL.createObjectURL(f));
    // eslint-disable-next-line react-hooks/set-state-in-effect -- previews follow the chosen files
    setUrls(u);
    return () => u.forEach((x) => URL.revokeObjectURL(x));
  }, [files]);
  return (
    <FileDrop
      accept={ACCEPT_IMAGES}
      className="mb-5"
      inputLabel="Upload photos"
      disabled={files.length >= max}
      title={
        <>
          {title} <span className="font-normal text-ink-3">· {note}</span>
        </>
      }
      hint={files.length >= max ? `${max} is the most` : undefined}
      onFiles={(f) => onChange([...files, ...f].slice(0, max))}
    >
      {files.length > 0 && (
        <ul className="no-scrollbar mt-3 flex gap-2 overflow-x-auto">
          {urls.map((u, i) => (
            <li key={u} className="relative shrink-0">
              {/* eslint-disable-next-line @next/next/no-img-element -- local preview */}
              <img src={u} alt={`Photo ${i + 1}`} className="size-20 rounded-[8px] border border-line object-cover" />
              {showMain && i === 0 && <span className="absolute bottom-1 left-1 rounded bg-ink px-1.5 text-[11px] font-medium text-white">Main</span>}
              <button
                type="button"
                onClick={() => onChange(files.filter((_, j) => j !== i))}
                aria-label={`Remove ${title === "Photos" ? "photo" : title.toLowerCase()} ${i + 1}`}
                className="absolute -right-1.5 -top-1.5 flex size-7 items-center justify-center rounded-full border border-line bg-sheet text-ink shadow-sm"
              >
                <X className="size-3.5" strokeWidth={2} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </FileDrop>
  );
}
