import { useRef, useState } from "react";

const MAX = 6;

/** Photo picker with thumbnails. onChange(files: File[]) */
export default function PhotoPicker({ files, onChange }) {
  const inputRef = useRef(null);
  const [err, setErr] = useState("");

  const addFiles = (list) => {
    setErr("");
    const next = [...files, ...Array.from(list)].slice(0, MAX);
    const bad = next.find(
      (f) => !/\.(jpe?g|png|webp)$/i.test(f.name) || f.size > 8 * 1024 * 1024
    );
    if (bad) {
      setErr(`${bad.name}: jpg/png/webp only, max 8 MB`);
      return;
    }
    onChange(next);
  };

  const remove = (i) => onChange(files.filter((_, idx) => idx !== i));

  return (
    <div>
      <div className="row" style={{ gap: 8 }}>
        {files.map((f, i) => (
          <div key={i} style={{ position: "relative" }}>
            <img
              src={URL.createObjectURL(f)}
              alt={f.name}
              style={{ width: 64, height: 64, objectFit: "cover", borderRadius: 8 }}
            />
            <button
              type="button"
              className="danger"
              onClick={() => remove(i)}
              style={{
                position: "absolute", top: -6, right: -6,
                width: 20, height: 20, padding: 0, borderRadius: "50%",
                fontSize: 11, lineHeight: "20px",
              }}
            >
              ×
            </button>
          </div>
        ))}
        {files.length < MAX && (
          <button
            type="button"
            className="secondary"
            onClick={() => inputRef.current?.click()}
            style={{ width: 64, height: 64, fontSize: 22 }}
            title="Add photos"
          >
            📷
          </button>
        )}
      </div>
      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        multiple
        hidden
        onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }}
      />
      {err && <div className="error">{err}</div>}
      <div className="muted" style={{ marginTop: 4 }}>
        {files.length}/{MAX} photos — used by AI grading
      </div>
    </div>
  );
}
