export function formatMoney(value) {
  const n = typeof value === "string" ? parseFloat(value) : value;
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: 2,
  }).format(n);
}

export function formatDate(value) {
  return new Date(value).toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export const STATUS_STYLES = {
  SUCCESS: "bg-emerald-50 text-emerald-700 border-emerald-200",
  COMPLETED: "bg-emerald-50 text-emerald-700 border-emerald-200",
  PENDING: "bg-amber-50 text-amber-700 border-amber-200",
  PROCESSING: "bg-blue-50 text-blue-700 border-blue-200",
  CREATED: "bg-slate-50 text-slate-700 border-slate-200",
  FAILED: "bg-rose-50 text-rose-700 border-rose-200",
  CANCELLED: "bg-slate-50 text-slate-500 border-slate-200",
};

export function StatusBadgeClasses(status) {
  return STATUS_STYLES[status] || STATUS_STYLES.CREATED;
}
