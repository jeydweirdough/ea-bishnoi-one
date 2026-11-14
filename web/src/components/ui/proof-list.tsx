"use client";

import { useState } from "react";
import { Camera, ImageUp, MapPin } from "lucide-react";
import { api, fmtDateTime, invalidate, type ApiError } from "@/lib/api";
import { useToast } from "./feedback";
import { ACCEPT_IMAGES, FileDrop } from "./file-drop";
import { Viewer, shrink } from "./photos";
import { proofMeta, stampPlace, type Proof } from "./proof-camera";

export type { Proof } from "./proof-camera";

/** Uploads one proof photo with how, when and where it was taken. */
export async function uploadProof(url: string, file: File) {
  const meta = proofMeta.get(file) ?? { source: "upload" as const };
  const fd = new FormData();
  fd.set("file", meta.source === "camera" ? file : await shrink(file));
  fd.set("meta", JSON.stringify(meta));
  return api<Proof>(url, { method: "POST", body: fd });
}

/** One line under a proof photo: taken with the camera (when, where) or uploaded from the gallery. */
export function ProofFacts({ p }: { p: Proof }) {
  const m = p.meta ?? { source: "upload" };
  const taken = m.source === "camera";
  const map = m.lat !== undefined && m.lng !== undefined ? `https://www.openstreetmap.org/?mlat=${m.lat}&mlon=${m.lng}#map=18/${m.lat}/${m.lng}` : null;
  return (
    <span className="block text-[12px] leading-snug text-ink-3">
      <span className="flex items-center gap-1 font-medium text-ink-2">
        {taken ? <Camera className="size-3.5" strokeWidth={1.75} aria-hidden="true" /> : <ImageUp className="size-3.5" strokeWidth={1.75} aria-hidden="true" />}
        {taken ? `Taken ${m.taken_at ? fmtDateTime(m.taken_at) : ""}` : `Uploaded ${p.uploaded_at ? fmtDateTime(p.uploaded_at) : ""}`}
      </span>
      {taken && (
        <span className="flex items-center gap-1">
          <MapPin className="size-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
          {map ? (
            <a href={map} target="_blank" rel="noreferrer" className="underline underline-offset-2 hover:text-ink">
              {stampPlace(m.lat, m.lng, m.accuracy_m)}
            </a>
          ) : (
            "Location not shared"
          )}
        </span>
      )}
      {p.uploaded_by && <span className="block">by {p.uploaded_by.name}</span>}
    </span>
  );
}

/**
 * The photos on a transaction, each with when and where it was taken; tap one to see it full size.
 * With `addUrl`, staff can add more: the camera stamps date, time and location on the photo.
 */
export function ProofSection({ proofs, addUrl, label, onAdded, max = 6 }: { proofs: Proof[]; addUrl?: string; label: string; onAdded?: () => void; max?: number }) {
  const toast = useToast();
  const [viewing, setViewing] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  async function add(files: File[]) {
    if (!addUrl) return;
    setBusy(true);
    let n = 0;
    for (const f of files.slice(0, Math.max(0, max - proofs.length))) {
      try {
        await uploadProof(addUrl, f);
        n++;
      } catch (e) {
        toast((e as ApiError).message, "error");
      }
    }
    setBusy(false);
    if (n) {
      toast(n === 1 ? "Photo added" : `${n} photos added`);
      invalidate();
      onAdded?.();
    }
  }
  return (
    <div>
      {proofs.length > 0 ? (
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {proofs.map((p, i) => (
            <li key={p.id} className="min-w-0">
              <button type="button" onClick={() => setViewing(i)} aria-label={`Open photo ${i + 1}`} className="block w-full overflow-hidden rounded-[10px] border border-line bg-canvas">
                {/* eslint-disable-next-line @next/next/no-img-element -- private API image */}
                <img src={p.thumb} alt={`Proof photo ${i + 1}`} loading="lazy" className="aspect-[4/3] w-full object-cover" />
              </button>
              <span className="mt-1.5 block">
                <ProofFacts p={p} />
              </span>
            </li>
          ))}
        </ul>
      ) : (
        !addUrl && <p className="text-[13.5px] text-ink-3">No photos on this one.</p>
      )}
      {addUrl && proofs.length < max && (
        <FileDrop accept={ACCEPT_IMAGES} compact busy={busy} stamp={label} inputLabel="Upload photos" onFiles={add} className={proofs.length ? "mt-3" : undefined} hint={proofs.length ? undefined : "add a photo as proof"} />
      )}
      {viewing !== null && proofs[viewing] && (
        <Viewer photos={proofs.map((p) => ({ ...p, main: false }))} index={viewing} onIndex={setViewing} onClose={() => setViewing(null)} canEdit={false} onChanged={() => undefined} />
      )}
    </div>
  );
}
