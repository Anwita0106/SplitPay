import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import { CheckCircle2, CircleAlert, Info, X } from "lucide-react";

const ToastContext = createContext(null);

const TONES = {
  success: { icon: CheckCircle2, box: "border-emerald-100 text-emerald-700", icon_: "text-emerald-600" },
  error: { icon: CircleAlert, box: "border-rose-100 text-rose-700", icon_: "text-rose-600" },
  info: { icon: Info, box: "border-blue-100 text-blue-700", icon_: "text-blue-600" },
};

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id) => setToasts((list) => list.filter((t) => t.id !== id)), []);

  const push = useCallback(
    (type, message, ms = 4500) => {
      const id = nextId.current++;
      setToasts((list) => [...list.slice(-3), { id, type, message }]);
      if (ms) setTimeout(() => dismiss(id), ms);
    },
    [dismiss]
  );

  const api = useMemo(
    () => ({
      success: (m, ms) => push("success", m, ms),
      error: (m, ms) => push("error", m, ms ?? 7000),
      info: (m, ms) => push("info", m, ms),
    }),
    [push]
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[70] flex w-[min(92vw,22rem)] flex-col gap-2" aria-live="polite">
        {toasts.map((t) => {
          const tone = TONES[t.type] || TONES.info;
          const Icon = tone.icon;
          return (
            <div
              key={t.id}
              role={t.type === "error" ? "alert" : "status"}
              className={`pointer-events-auto animate-scale-in flex items-start gap-3 rounded-2xl border bg-white px-4 py-3 text-sm font-semibold shadow-lg ${tone.box}`}
            >
              <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${tone.icon_}`} />
              <p className="flex-1 leading-5">{t.message}</p>
              <button onClick={() => dismiss(t.id)} className="rounded-lg p-0.5 text-slate-400 hover:bg-slate-100" aria-label="Dismiss">
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside <ToastProvider>");
  return ctx;
}
