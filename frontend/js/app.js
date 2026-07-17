document.addEventListener("DOMContentLoaded", () => {
  api.get("/health").catch((err) => console.error("Health check failed:", err));
});
