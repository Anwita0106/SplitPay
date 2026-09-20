/** Turn any axios/FastAPI error into one human sentence (never an object or array). */
export function getErrorMessage(err, fallback = "Something went wrong. Please try again.") {
  const detail = err?.response?.data?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail) && detail.length) {
    // FastAPI validation errors: [{ loc: ["body", "total_amount"], msg: "Value error, ..." }]
    return detail
      .map((d) => {
        const field = Array.isArray(d.loc) ? d.loc.filter((x) => x !== "body").join(" › ") : "";
        const msg = String(d.msg || "").replace(/^Value error, /, "");
        return field ? `${field}: ${msg}` : msg;
      })
      .join(" ");
  }
  if (err && !err.response) return "Can't reach the server. Check your connection and try again.";
  return fallback;
}

export const getErrorCode = (err) => err?.response?.data?.code;
export const getErrorExtra = (err) => err?.response?.data?.extra;
