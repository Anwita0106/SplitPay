import { Bot, CheckCircle2, History, Loader2, Send, Sparkles, UserRound, Wrench, Check, X, WalletCards } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { useToast } from "../context/ToastContext.jsx";
import api from "../services/api.js";
import { getErrorMessage } from "../utils/errors";

const suggestions = [
  "Who owes me money?",
  "Who do I owe right now?",
  "How much have I spent across my groups?",
  "Show me my recent settlements.",
  "Summarize my group balances.",
];

// The card's lifecycle: pending -> confirming -> confirmed | cancelled | failed | expired
function DraftFooter({ state, error, expiresAt, onConfirm, onCancel, confirmLabel, confirmClass, icon: Icon }) {
  const expired = state === "pending" && expiresAt && new Date(expiresAt).getTime() < Date.now();
  if (state === "confirmed") return <p className="mt-3 flex items-center gap-2 rounded-xl border border-emerald-100 bg-emerald-50 px-3 py-2 text-xs font-bold text-emerald-700"><CheckCircle2 className="h-4 w-4" /> Confirmed and saved.</p>;
  if (state === "cancelled") return <p className="mt-3 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-bold text-slate-500">Cancelled — nothing was changed.</p>;
  if (state === "failed") return <p className="mt-3 rounded-xl border border-rose-100 bg-rose-50 px-3 py-2 text-xs font-bold text-rose-700">Not saved: {error || "something changed since this draft was prepared."} Ask again for a fresh draft.</p>;
  if (expired) return <p className="mt-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-bold text-amber-700 dark:text-amber-300">This draft expired. Ask again to get a fresh one.</p>;
  const busy = state === "confirming";
  return (
    <>
      <div className="mt-3 flex gap-2">
        <button disabled={busy} onClick={onConfirm} className={`inline-flex flex-1 items-center justify-center gap-2 rounded-xl px-3 py-2.5 text-xs font-black disabled:opacity-50 ${confirmClass}`}>{busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Icon className="h-3.5 w-3.5" />} {busy ? "Saving…" : confirmLabel}</button>
        <button disabled={busy} onClick={onCancel} className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-xs font-bold text-slate-600 disabled:opacity-50 dark:border-white/10 dark:bg-white/5 dark:text-slate-300"><X className="h-3.5 w-3.5" /> Cancel</button>
      </div>
      <p className="mt-2 text-[10px] font-semibold text-slate-400">Nothing is saved until you confirm.</p>
    </>
  );
}

function ExpenseDraftCard({ draft, state, error, onConfirm, onCancel }) {
  const participants = draft.participants || [];
  return (
    <div className="mt-3 rounded-2xl border border-blue-200 bg-blue-50/70 p-4 dark:border-blue-400/20 dark:bg-blue-400/10">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[10px] font-black uppercase tracking-[.14em] text-blue-600 dark:text-blue-300">Expense draft</p>
          <h3 className="mt-1 font-serif text-xl font-bold text-slate-950 dark:text-white">{draft.expense.description}</h3>
          <p className="text-sm text-slate-500 dark:text-slate-400">{draft.group_name} · paid by {draft.paid_by_name}</p>
        </div>
        <p className="text-xl font-black text-slate-950 dark:text-white">₹{Number(draft.expense.total_amount).toFixed(2)}</p>
      </div>
      <div className="mt-3 divide-y divide-blue-200/70 rounded-xl border border-blue-200/70 bg-white/70 dark:divide-white/10 dark:border-white/10 dark:bg-white/5">
        {participants.map((p) => <div key={p.user_id} className="flex items-center justify-between px-3 py-2 text-sm"><span className="font-semibold text-slate-700 dark:text-slate-200">{p.name}</span><span className="font-bold text-slate-950 dark:text-white">₹{Number(p.amount).toFixed(2)}</span></div>)}
      </div>
      {draft.assumptions?.length > 0 && <ul className="mt-2 space-y-0.5 text-[11px] text-slate-500 dark:text-slate-400">{draft.assumptions.map((a) => <li key={a}>• {a}</li>)}</ul>}
      <DraftFooter state={state} error={error} expiresAt={draft.expires_at} onConfirm={onConfirm} onCancel={onCancel} confirmLabel="Confirm expense" confirmClass="bg-slate-950 text-white dark:bg-white dark:text-slate-950" icon={Check} />
    </div>
  );
}

function SettlementDraftCard({ draft, state, error, onConfirm, onCancel }) {
  return (
    <div className="mt-3 rounded-2xl border border-emerald-200 bg-emerald-50/70 p-4 dark:border-emerald-400/20 dark:bg-emerald-400/10">
      <div className="flex items-start justify-between gap-3">
        <div><p className="text-[10px] font-black uppercase tracking-[.14em] text-emerald-600 dark:text-emerald-300">Settlement draft</p><h3 className="mt-1 font-serif text-xl font-bold text-slate-950 dark:text-white">{draft.from_name} → {draft.to_name}</h3><p className="text-sm text-slate-500 dark:text-slate-400">{draft.group_name}</p></div>
        <p className="text-xl font-black text-slate-950 dark:text-white">₹{Number(draft.amount).toFixed(2)}</p>
      </div>
      <p className="mt-2 text-[11px] text-slate-500 dark:text-slate-400">{draft.reason}</p>
      <DraftFooter state={state} error={error} expiresAt={draft.expires_at} onConfirm={onConfirm} onCancel={onCancel} confirmLabel="Confirm settlement" confirmClass="bg-emerald-600 text-white" icon={WalletCards} />
    </div>
  );
}

function Message({ item }) {
  const user = item.role === "user";
  return (
    <div className={`flex gap-3 ${user ? "justify-end" : "justify-start"}`}>
      {!user && <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-slate-950 text-white dark:bg-white dark:text-slate-950"><Bot className="h-4 w-4" /></div>}
      <div className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-6 ${user ? "rounded-br-md bg-slate-950 text-white dark:bg-white dark:text-slate-950" : "rounded-bl-md border border-slate-200 bg-white/80 text-slate-700 shadow-sm dark:border-white/10 dark:bg-white/5 dark:text-slate-200"}`}>
        <p className="whitespace-pre-wrap">{item.content}</p>
        {item.expenseDraft && <ExpenseDraftCard draft={item.expenseDraft} state={item.draftState || "pending"} error={item.draftError} onConfirm={() => item.onConfirm?.()} onCancel={() => item.onCancel?.()} />}
        {item.settlementDraft && <SettlementDraftCard draft={item.settlementDraft} state={item.draftState || "pending"} error={item.draftError} onConfirm={() => item.onConfirm?.()} onCancel={() => item.onCancel?.()} />}
        {item.clarification && (
          <div className="mt-3 space-y-2">
            {item.clarification.options.filter((o) => o.group_id).map((o) => (
              <button key={o.group_id} disabled={item.busy} onClick={() => item.onPickGroup?.(o.group_id)} className="block w-full rounded-xl border border-blue-200 bg-blue-50/70 px-3 py-2 text-left text-xs font-bold text-blue-700 hover:bg-blue-50 disabled:opacity-50 dark:border-blue-400/20 dark:bg-blue-400/10 dark:text-blue-300">{o.label}</button>
            ))}
          </div>
        )}
        {item.tools?.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5 border-t border-slate-200/70 pt-2.5 dark:border-white/10">
            {item.mode === "deterministic" && <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-1 text-[9px] font-black uppercase tracking-wider text-emerald-700"><CheckCircle2 className="h-2.5 w-2.5" />backend verified</span>}
            {item.tools.map((tool) => <span key={tool} className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-1 text-[9px] font-black uppercase tracking-wider text-slate-500 dark:bg-white/10 dark:text-slate-400"><Wrench className="h-2.5 w-2.5" />{tool.replaceAll("_", " ")}</span>)}
          </div>
        )}
      </div>
      {user && <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-blue-600 text-white"><UserRound className="h-4 w-4" /></div>}
    </div>
  );
}

export default function AI() {
  const toast = useToast();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showHistory, setShowHistory] = useState(false);
  const [history, setHistory] = useState(null);

  const conversation = useMemo(() => messages.map(({ role, content }) => ({ role, content })), [messages]);

  const patchMessage = useCallback((index, patch) => {
    setMessages((list) => list.map((m, i) => (i === index ? { ...m, ...patch } : m)));
  }, []);

  async function send(text = input, groupId = null) {
    const message = text.trim();
    if (!message || loading) return;
    setInput("");
    setError("");
    if (!groupId) setMessages((m) => [...m, { role: "user", content: message }]);
    setLoading(true);
    try {
      const { data } = await api.post("/ai/chat", { message, conversation, ...(groupId ? { group_id: groupId } : {}) });
      setMessages((m) => [...m, {
        role: "assistant", content: data.reply, tools: data.used_tools, mode: data.mode,
        expenseDraft: data.expense_draft, settlementDraft: data.settlement_draft,
        clarification: data.clarification, retryMessage: message, draftState: "pending",
      }]);
    } catch (err) {
      setError(getErrorMessage(err, "SplitPay AI couldn't connect. Make sure Ollama is running."));
    } finally {
      setLoading(false);
    }
  }

  // The ONLY write path: confirm by draft id. The server executes the payload it stored, not anything sent from here.
  async function confirmDraft(index) {
    const item = messages[index];
    const draft = item.expenseDraft || item.settlementDraft;
    if (!draft || item.draftState === "confirming" || item.draftState === "confirmed") return;
    patchMessage(index, { draftState: "confirming" });
    try {
      const { data } = await api.post(`/ai/drafts/${draft.draft_id}/confirm`);
      patchMessage(index, { draftState: "confirmed" });
      setMessages((m) => [...m, { role: "assistant", content: data.message, tools: [] }]);
      toast.success(data.already_confirmed ? "Already saved — nothing was duplicated." : data.message);
      setHistory(null);
    } catch (err) {
      const msg = getErrorMessage(err, "The draft could not be saved.");
      patchMessage(index, { draftState: "failed", draftError: msg });
      toast.error(msg);
    }
  }

  async function cancelDraft(index) {
    const item = messages[index];
    const draft = item.expenseDraft || item.settlementDraft;
    if (!draft) return;
    patchMessage(index, { draftState: "confirming" });
    try {
      await api.post(`/ai/drafts/${draft.draft_id}/cancel`);
      patchMessage(index, { draftState: "cancelled" });
      setHistory(null);
    } catch (err) {
      patchMessage(index, { draftState: "pending" });
      toast.error(getErrorMessage(err, "Could not cancel the draft."));
    }
  }

  async function toggleHistory() {
    const next = !showHistory;
    setShowHistory(next);
    if (next && history === null) {
      try {
        const { data } = await api.get("/ai/actions");
        setHistory(data);
      } catch (err) {
        setHistory([]);
        toast.error(getErrorMessage(err, "Could not load AI activity."));
      }
    }
  }

  return (
    <div className="mx-auto max-w-5xl">
      <section className="relative overflow-hidden rounded-[2rem] border border-slate-200 bg-[#fbf7ef] p-6 shadow-sm dark:border-white/10 dark:bg-[#0b1a2a] sm:p-8">
        <div className="absolute -right-16 -top-16 h-48 w-48 rounded-full bg-blue-500/10 blur-3xl" />
        <div className="relative">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-blue-200 bg-blue-50 px-3 py-1.5 text-[10px] font-black uppercase tracking-[.16em] text-blue-700 dark:border-blue-400/20 dark:bg-blue-400/10 dark:text-blue-300"><Sparkles className="h-3 w-3" /> Local AI agent</div>
              <h1 className="font-serif text-4xl font-bold tracking-[-.04em] text-slate-950 dark:text-white sm:text-5xl">Ask your money anything.</h1>
              <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-500 dark:text-slate-400">SplitPay AI can analyze your groups, expenses, balances and settlements, and prepare confirmation-gated expense or settlement actions. Your deterministic backend remains the source of truth.</p>
            </div>
            <div className="hidden h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-slate-950 text-white shadow-xl sm:flex dark:bg-white dark:text-slate-950"><Bot className="h-6 w-6" /></div>
          </div>
        </div>
      </section>

      <section className="mt-5 overflow-hidden rounded-[2rem] border border-slate-200 bg-white/70 shadow-sm backdrop-blur-xl dark:border-white/10 dark:bg-white/[0.03]">
        <div className="flex min-h-[420px] flex-col">
          <div className="flex-1 space-y-4 overflow-y-auto p-5 sm:p-7">
            {messages.length === 0 && (
              <div className="flex min-h-[300px] flex-col items-center justify-center text-center">
                <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-slate-950 text-white shadow-xl dark:bg-white dark:text-slate-950"><Bot className="h-7 w-7" /></div>
                <h2 className="mt-5 font-serif text-2xl font-bold text-slate-950 dark:text-white">Your private SplitPay assistant</h2>
                <p className="mt-2 max-w-md text-sm leading-6 text-slate-500 dark:text-slate-400">Try one of these questions. The agent will call only the tools it needs.</p>
                <div className="mt-5 flex max-w-2xl flex-wrap justify-center gap-2">
                  {suggestions.map((suggestion) => <button key={suggestion} onClick={() => send(suggestion)} className="rounded-full border border-slate-200 bg-white px-3.5 py-2 text-xs font-bold text-slate-600 transition hover:-translate-y-0.5 hover:border-slate-300 dark:border-white/10 dark:bg-white/5 dark:text-slate-300">{suggestion}</button>)}
                </div>
              </div>
            )}
            {messages.map((item, i) => <Message key={`${item.role}-${i}`} item={{ ...item, busy: loading, onConfirm: () => confirmDraft(i), onCancel: () => cancelDraft(i), onPickGroup: (gid) => send(item.retryMessage, gid) }} />)}
            {loading && <div className="flex items-center gap-3 text-sm text-slate-400"><Loader2 className="h-4 w-4 animate-spin" /> SplitPay AI is thinking…</div>}
            {error && <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-xs font-semibold text-rose-700 dark:border-rose-400/20 dark:bg-rose-400/10 dark:text-rose-300">{error}</div>}
          </div>
          <div className="border-t border-slate-200/70 p-4 dark:border-white/10 sm:p-5">
            <form onSubmit={(e) => { e.preventDefault(); send(); }} className="flex items-end gap-2 rounded-2xl border border-slate-200 bg-slate-50 p-2 shadow-inner dark:border-white/10 dark:bg-white/5">
              <textarea value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} rows={1} placeholder="Ask about your expenses, groups or balances…" className="max-h-28 min-h-11 flex-1 resize-none bg-transparent px-3 py-3 text-sm text-slate-900 outline-none placeholder:text-slate-400 dark:text-white" />
              <button disabled={!input.trim() || loading} className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-slate-950 text-white transition hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-40 dark:bg-white dark:text-slate-950" aria-label="Send message"><Send className="h-4 w-4" /></button>
            </form>
            <p className="mt-2 flex items-center justify-center gap-1 text-center text-[9px] font-bold uppercase tracking-[.13em] text-slate-400"><CheckCircle2 className="h-3 w-3 text-emerald-500" /> AI drafts · confirmation-gated writes · deterministic financial backend</p>
          </div>
        </div>
      </section>

      <section className="mt-5 rounded-[2rem] border border-slate-200 bg-white/70 p-5 shadow-sm dark:border-white/10 dark:bg-white/[0.03]">
        <button onClick={toggleHistory} className="flex w-full items-center justify-between text-left" aria-expanded={showHistory}>
          <span className="inline-flex items-center gap-2 text-sm font-black text-slate-800"><History className="h-4 w-4 text-slate-400" /> AI activity</span>
          <span className="text-xs font-bold text-slate-400">{showHistory ? "Hide" : "Show"}</span>
        </button>
        {showHistory && (history === null ? <div className="skeleton mt-4 h-16 rounded-2xl" /> : history.length === 0 ? <p className="mt-4 rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-4 text-xs text-slate-500">No AI-prepared actions yet. Ask the assistant to add an expense or settle up.</p> : (
          <ul className="mt-4 divide-y divide-slate-100">
            {history.map((h) => <li key={h.id} className="flex items-center justify-between gap-3 py-2.5 text-xs"><span className="min-w-0 truncate text-slate-600" title={h.error || h.summary}>{h.summary}</span><span className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-black uppercase tracking-wider ${h.status === "CONFIRMED" ? "border-emerald-100 bg-emerald-50 text-emerald-700" : h.status === "FAILED" ? "border-rose-100 bg-rose-50 text-rose-700" : "border-slate-200 bg-slate-50 text-slate-500"}`}>{h.status.toLowerCase()}</span></li>)}
          </ul>
        ))}
      </section>
    </div>
  );
}
