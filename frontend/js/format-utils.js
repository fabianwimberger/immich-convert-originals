/** Shared formatting for anything that shows a run outcome: the live log on
 * the Convert tab and the History detail table render the same statuses. */

const STATUS_LABELS = {
  processing: "Processing…",
  success: "Converted",
  partial_success: "Converted (cleanup needed)",
  dry_run_preview: "Would convert",
  skipped: "Skipped",
  failed_download: "Failed: download",
  failed_transcode: "Failed: transcode",
  failed_upload: "Failed: upload",
  failed_copy: "Failed: metadata copy",
  failed_verification: "Failed: verification",
  failed_error: "Failed: unexpected error",
};

function prettyStatus(status) {
  return STATUS_LABELS[status] || status.replace(/_/g, " ");
}

function statusTextClass(status) {
  if (status === "processing") return "status-pending";
  if (status === "success" || status === "partial_success" || status === "dry_run_preview") {
    return "status-ok";
  }
  if (status && status.startsWith("failed")) return "status-error";
  return "placeholder";
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
