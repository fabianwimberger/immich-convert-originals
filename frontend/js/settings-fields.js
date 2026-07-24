/** Presentation-only metadata for Settings/run-override fields: rendered as
 * a hint line under each input. Validation bounds are enforced server-side
 * (see backend/app/models/schemas.py); these mirror them for display, they
 * don't re-implement them. */
const SETTINGS_FIELDS = {
  asset_types: {
    description: "Which asset types a filtered run considers by default.",
    default: "Images + Videos",
  },
  include_archived: {
    description: "Include assets Immich has archived.",
    default: "off",
  },
  include_deleted: {
    description: "Include assets already in Immich's trash.",
    default: "off",
  },
  convert_image_formats: {
    description:
      "Image formats a run will touch at all -- anything unchecked is left untouched and skipped before download.",
    default: "all of the below",
  },
  image_target_format: {
    description:
      "Output image container. JPEG sources get a lossless bit-exact repack only when targeting JXL -- HEIC/AVIF have no equivalent, so JPEG sources targeting those go through a normal re-encode instead.",
    default: "JPEG XL (JXL)",
  },
  image_distance: {
    description:
      "JPEG XL distance: 0 = mathematically lossless, 1 = visually lossless, higher = smaller files with more quality loss. JPEG sources always use a lossless repack regardless of this value.",
    default: "1.0",
    example: "e.g. 1.5 for noticeably smaller PNG/HEIC/WebP output",
  },
  image_distance_retry: {
    description: "Distance used if the first pass came out larger than the original.",
    default: "2.0",
  },
  image_quality_heic: {
    description: "HEIC quality (ImageMagick -quality) -- higher is better and larger.",
    default: "80",
  },
  image_quality_heic_retry: {
    description: "Quality used if the first pass came out larger than the original.",
    default: "60",
  },
  image_quality_avif: {
    description: "AVIF quality (ImageMagick -quality) -- higher is better and larger.",
    default: "75",
  },
  image_quality_avif_retry: {
    description: "Quality used if the first pass came out larger than the original.",
    default: "55",
  },
  video_crf: {
    description: "AV1 quality via SVT-AV1 -- lower is better quality and larger files.",
    default: "36",
    example: "e.g. 30 for near-lossless, 40 for smaller files",
  },
  video_crf_retry: {
    description: "CRF used if the first pass came out larger than the original.",
    default: "40",
  },
  video_preset: {
    description:
      "SVT-AV1 speed/quality tradeoff -- lower is slower to encode but smaller/better output.",
    default: "4",
    example: "e.g. 6-8 for faster encodes on modest hardware",
  },
  video_max_dimension: {
    description:
      "Caps the shorter side (width or height) in pixels; aspect ratio is preserved. 0 disables scaling.",
    default: "0 (disabled)",
    example: "e.g. 1080 to cap 4K video down to 1080p",
  },
  video_audio_bitrate: {
    description: "Opus audio bitrate, ffmpeg format.",
    default: "64k",
    example: "e.g. 96k, 128k",
  },
  enable_retry: {
    description:
      "If a converted file comes out larger than the original, automatically retry once with more compression instead of keeping the larger file.",
    default: "on",
  },
  accept_retry_output: {
    description:
      "If the retry pass is still larger than the original, keep it anyway instead of skipping the asset.",
    default: "off",
  },
  allow_larger: {
    description:
      "Skip the larger-output check entirely and keep whatever the first pass produces, even if it's bigger than the original.",
    default: "off",
  },
  concurrency: {
    description: "How many assets are downloaded/transcoded/uploaded in parallel per run.",
    default: "2",
    example: "e.g. 4-8 if your Immich server and disk can keep up",
  },
};

/** "Default: X -- description (example)" hint markup for a field, or "" if
 * the field has no metadata (e.g. it isn't a knob worth explaining). */
function fieldHint(name) {
  const f = SETTINGS_FIELDS[name];
  if (!f) return "";
  const parts = [`Default: ${f.default}`, f.description];
  if (f.example) parts.push(f.example);
  return `<small class="field-hint">${parts.join(" -- ")}</small>`;
}

/** [value, label] pairs for the image-format allow-list checkbox group. */
const IMAGE_FORMAT_OPTIONS = [
  ["jpg", "JPEG"],
  ["png", "PNG"],
  ["webp", "WebP"],
  ["heic", "HEIC"],
  ["avif", "AVIF"],
  ["tiff", "TIFF"],
  ["gif", "GIF"],
  ["bmp", "BMP"],
];

/** Renders the image-format allow-list as a checkbox group; selectedCsv is
 * the current comma-separated value (e.g. "jpg,png,heic"). */
function renderFormatCheckboxes(idPrefix, selectedCsv) {
  const selected = new Set(selectedCsv.split(","));
  return IMAGE_FORMAT_OPTIONS.map(
    ([value, label]) =>
      `<label class="checkbox-inline"><input type="checkbox" data-format="${value}" id="${idPrefix}-${value}" ${selected.has(value) ? "checked" : ""} /> ${label}</label>`
  ).join("");
}

/** Reads a format checkbox group back into a comma-separated string. */
function readFormatCheckboxes(root, idPrefix) {
  return IMAGE_FORMAT_OPTIONS.filter(([value]) =>
    root.querySelector(`#${idPrefix}-${value}`).checked
  )
    .map(([value]) => value)
    .join(",");
}
