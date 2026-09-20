import { CircleAlert, RefreshCw } from "lucide-react";

/** Loading skeleton block, reusing the existing `.skeleton` shimmer. */
export function PageSkeleton({ rows = 3, className = "h-24" }) {
  return (
    <div className="space-y-4" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className={`skeleton rounded-3xl ${className}`} />
      ))}
    </div>
  );
}

/** Friendly error panel with a retry button. */
export function ErrorState({ message, onRetry }) {
  return (
    <div className="rounded-3xl border border-rose-100 bg-rose-50 p-8 text-center">
      <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-white text-rose-600">
        <CircleAlert className="h-6 w-6" />
      </div>
      <p className="mt-3 text-sm font-bold text-rose-700">{message || "Something went wrong."}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-4 inline-flex items-center gap-2 rounded-xl bg-slate-950 px-4 py-2.5 text-xs font-black text-white hover:bg-slate-800"
        >
          <RefreshCw className="h-3.5 w-3.5" /> Try again
        </button>
      )}
    </div>
  );
}
