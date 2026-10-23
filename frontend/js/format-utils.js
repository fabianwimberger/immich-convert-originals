/** Shared formatting for anything that shows a run outcome: the live log on
 * the Convert tab and the History detail table render the same statuses. */

const STATUS_LABELS = {
  processing: "Processing…",
  success: "Converted",
  partial_success: "Converted, cleanup needed",
  saved_local: "Saved locally",
  dry_run_preview: "Would convert",
  skipped: "Skipped",
  failed_download: "Failed: download",
  failed_transcode: "Failed: transcode",
  failed_upload: "Failed: upload",
  failed_copy: "Failed: metadata copy",
  failed_verification: "Failed: verification",
  failed_error: "Failed: unexpected error",
};

const RUN_STATUS_LABELS = {
  queued: "Queued",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
};

function prettyStatus(status) {
  return STATUS_LABELS[status] || status.replace(/_/g, " ");
}

function prettyRunStatus(status) {
  return RUN_STATUS_LABELS[status] || status;
}

/** Kennfarbe status class for one asset outcome. */
function statusClass(status) {
  if (status === "processing") return "status status--run";
  if (
    status === "success" ||
    status === "partial_success" ||
    status === "saved_local" ||
    status === "dry_run_preview"
  ) {
    return "status status--ok";
  }
  if (status && status.startsWith("failed")) return "status status--fail";
  return "status";
}

/** Kennfarbe status class for a run's own state. */
function runStatusClass(status) {
  if (status === "running" || status === "queued") return "status status--run";
  if (status === "completed") return "status status--ok";
  if (status === "failed" || status === "cancelled") return "status status--fail";
  return "status";
}

/** Format label from the filename, falling back to the MIME subtype. */
function formatOf(asset) {
  const name = asset.original_file_name || "";
  const ext = name.includes(".") ? name.split(".").pop() : "";
  if (ext && ext.length <= 5) return ext.toUpperCase();
  const subtype = (asset.original_mime_type || "").split("/").pop();
  return (subtype || asset.type || "").toUpperCase();
}

/** Short date for asset tiles; the API returns ISO strings. */
function shortDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function fmtBytes(n) {
  if (!n && n !== 0) return "";
  if (Math.abs(n) < 1024) return `${n} B`;
  const units = ["KB", "MB", "GB"];
  let val = n;
  let i = -1;
  do {
    val /= 1024;
    i++;
  } while (Math.abs(val) >= 1024 && i < units.length - 1);
  return `${val.toFixed(1)} ${units[i]}`;
}

function savedLabel(inputBytes, outputBytes) {
  if (!inputBytes) return "";
  const saved = inputBytes - outputBytes;
  const pct = ((saved / inputBytes) * 100).toFixed(0);
  return `${fmtBytes(saved)} (${pct}%)`;
}
