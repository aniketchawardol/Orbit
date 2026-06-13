import { useEffect, useRef, useState } from "react";
import { preparePhoto } from "../lib/image";

const MAX = 6;
const NAME_RE = /\.(jpe?g|png|webp)$/i;
const MAX_BYTES = 8 * 1024 * 1024;

/** Photo picker with thumbnails.
 *  onChange(files: File[])      — compressed files, ready to upload.
 *  onMetadata(metas: object[])? — per-file EXIF/metadata read BEFORE compression,
 *                                 index-aligned with files (return fraud checks).
 */
export default function PhotoPicker({ files, onChange, onMetadata }) {
  const inputRef = useRef(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [metas, setMetas] = useState([]);

  // Re-sync metadata if the parent clears files externally (e.g. after submit).
  useEffect(() => {
    if (files.length === 0 && metas.length) setMetas([]);
  }, [files.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const addFiles = async (list) => {
    setErr("");
    const room = Math.max(0, MAX - files.length);
    const slice = Array.from(list).slice(0, room);
    if (slice.length === 0) return;

    // Validate originals (size/type) before spending effort on compression.
    const bad = slice.find((f) => !NAME_RE.test(f.name) || f.size > MAX_BYTES);
    if (bad) {
      setErr(`${bad.name}: jpg/png/webp only, max 8 MB`);
      return;
    }

    setBusy(true);
    try {
      const prepared = await Promise.all(slice.map((f) => preparePhoto(f)));
      const nextFiles = [...files, ...prepared.map((p) => p.file)];
      const nextMetas = [...metas, ...prepared.map((p) => p.metadata)];
      setMetas(nextMetas);
      onChange(nextFiles);
      onMetadata?.(nextMetas);
    } catch {
      setErr("Could not process one of the images. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  const remove = (i) => {
    const nextFiles = files.filter((_, idx) => idx !== i);
    const nextMetas = metas.filter((_, idx) => idx !== i);
    setMetas(nextMetas);
    onChange(nextFiles);
    onMetadata?.(nextMetas);
  };

  return (
    <div>
      <div className="row" style={{ gap: 8 }}>
        {files.map((f, i) => (
          <div key={i} style={{ position: "relative" }}>
            <img
              src={URL.createObjectURL(f)}
              alt={f.name}
              style={{
                width: 64,
                height: 64,
                objectFit: "cover",
                borderRadius: 8,
              }}
            />
            <button
              type="button"
              className="danger"
              aria-label="remove photo"
              onClick={() => remove(i)}
              style={{
                position: "absolute",
                top: -6,
                right: -6,
                width: 20,
                height: 20,
                padding: 0,
                borderRadius: "50%",
                fontSize: 11,
                lineHeight: "20px",
              }}
            >
              <span aria-hidden>Remove</span>
            </button>
          </div>
        ))}
        {files.length < MAX && (
          <button
            type="button"
            className="secondary"
            onClick={() => inputRef.current?.click()}
            style={{ width: 64, height: 64 }}
            title="Add photos"
            disabled={busy}
          >
            {busy ? "…" : "Add"}
          </button>
        )}
      </div>
      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        multiple
        hidden
        onChange={(e) => {
          addFiles(e.target.files);
          e.target.value = "";
        }}
      />
      {err && <div className="error">{err}</div>}
      <div className="muted" style={{ marginTop: 4 }}>
        {files.length}/{MAX} photos — used by AI grading
      </div>
    </div>
  );
}
