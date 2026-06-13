// Image helpers for the return flow.
//
// Two jobs, in this order (order matters):
//   1. extractMetadata(file) — read EXIF from the ORIGINAL file *before* we touch
//      it. Canvas compression strips EXIF, so this must happen first. The fields
//      we forward feed the backend's fraud checks (camera make/model, capture
//      time, software, original dimensions).
//   2. compressImage(file) — shrink large photos for faster uploads. We DON'T
//      compress images that are already small / low-resolution, so we never
//      degrade a genuinely low-quality photo further.

import exifr from "exifr";

const MAX_DIM = 1600; // longest edge (px) after compression
const QUALITY = 0.8; // JPEG quality
const SKIP_BELOW_BYTES = 300 * 1024; // tiny files: never worth compressing
const KEEP_JPEG_BELOW_BYTES = 1.5 * 1024 * 1024; // already-small JPEGs: leave as-is

// EXIF tags forwarded to the backend (names match grading/metadata.py lookups).
const EXIF_TAGS = [
  "Make",
  "Model",
  "Software",
  "DateTimeOriginal",
  "CreateDate",
  "ModifyDate",
  "DateTime",
  "ExifImageWidth",
  "ExifImageHeight",
  "Orientation",
];

function serialize(v) {
  if (v instanceof Date) return Number.isNaN(v.getTime()) ? null : v.toISOString();
  return v;
}

async function decodeDimensions(file) {
  try {
    const bitmap = await createImageBitmap(file);
    const dims = { width: bitmap.width, height: bitmap.height };
    bitmap.close?.();
    return dims;
  } catch {
    return {};
  }
}

export async function extractMetadata(file) {
  const meta = {
    name: file.name,
    type: file.type || "",
    size: file.size,
    lastModified: file.lastModified || null,
  };

  // EXIF is best-effort. Its ABSENCE (e.g. PNG screenshots, downloaded images)
  // is itself a useful signal the backend can act on, so we don't fail here.
  try {
    const tags = await exifr.parse(file, { pick: EXIF_TAGS });
    if (tags) {
      for (const [k, val] of Object.entries(tags)) {
        const s = serialize(val);
        if (s !== null && s !== undefined) meta[k] = s;
      }
    }
  } catch {
    /* no EXIF */
  }

  // True decoded dimensions are more reliable than EXIF width/height tags.
  const dims = await decodeDimensions(file);
  if (dims.width) {
    meta.originalWidth = dims.width;
    meta.originalHeight = dims.height;
  }
  return meta;
}

function isJpeg(type, name) {
  return /jpe?g/i.test(type || "") || /\.jpe?g$/i.test(name || "");
}

export async function compressImage(file, dims) {
  const longest = Math.max(dims?.width || 0, dims?.height || 0);

  // Skip: tiny files, or already-modest JPEGs — don't degrade low-quality images.
  if (file.size <= SKIP_BELOW_BYTES) return file;
  if (
    longest &&
    longest <= MAX_DIM &&
    isJpeg(file.type, file.name) &&
    file.size <= KEEP_JPEG_BELOW_BYTES
  ) {
    return file;
  }

  let bitmap;
  try {
    bitmap = await createImageBitmap(file);
  } catch {
    return file; // undecodable -> upload the original untouched
  }

  const scale = longest > MAX_DIM ? MAX_DIM / longest : 1;
  const w = Math.round(bitmap.width * scale);
  const h = Math.round(bitmap.height * scale);
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(bitmap, 0, 0, w, h);
  bitmap.close?.();

  const blob = await new Promise((resolve) =>
    canvas.toBlob(resolve, "image/jpeg", QUALITY),
  );
  if (!blob || blob.size >= file.size) return file; // no win -> keep original

  const base = file.name.replace(/\.[^.]+$/, "");
  return new File([blob], `${base}.jpg`, {
    type: "image/jpeg",
    lastModified: Date.now(),
  });
}

/** Read metadata (pre-compression) then compress. Returns {file, metadata}. */
export async function preparePhoto(file) {
  const metadata = await extractMetadata(file);
  const dims = metadata.originalWidth
    ? { width: metadata.originalWidth, height: metadata.originalHeight }
    : await decodeDimensions(file);
  const out = await compressImage(file, dims);
  return { file: out, metadata };
}
