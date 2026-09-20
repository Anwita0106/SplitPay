import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fail, ok, renderAt } from "./helpers.jsx";

vi.mock("../services/api.js", () => ({ default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }));
import api from "../services/api.js";
import AI from "../pages/AI.jsx";

const expenseDraft = {
  draft_id: "11111111-1111-1111-1111-111111111111",
  expires_at: new Date(Date.now() + 600000).toISOString(),
  expense: { description: "Dinner", total_amount: "2400.00", group_id: "g1" },
  group_name: "Goa Trip", paid_by_name: "Anwi",
  participants: [{ user_id: "a", name: "Anwi", amount: "1200.00" }, { user_id: "b", name: "Anwita", amount: "1200.00" }],
  assumptions: [],
};

beforeEach(() => vi.resetAllMocks());

describe("AI page draft flow", () => {
  it("confirms a draft by id only, then locks the card", async () => {
    api.post.mockImplementation((url) => {
      if (url === "/ai/chat") return ok({ reply: "I've prepared an expense draft", used_tools: ["prepare_expense_draft"], mode: "deterministic", expense_draft: expenseDraft });
      if (url.endsWith("/confirm")) return ok({ message: "Expense saved: Dinner for ₹2400 in Goa Trip.", already_confirmed: false });
      return fail(500, {});
    });
    renderAt(<AI />);
    await userEvent.type(screen.getByPlaceholderText(/ask about/i), "I paid 2400 for dinner{enter}");
    const confirm = await screen.findByRole("button", { name: /confirm expense/i });
    await userEvent.click(confirm);
    await waitFor(() => expect(screen.getByText(/confirmed and saved/i)).toBeInTheDocument());

    const confirmCall = api.post.mock.calls.find(([u]) => u.endsWith("/confirm"));
    expect(confirmCall[0]).toBe(`/ai/drafts/${expenseDraft.draft_id}/confirm`);
    expect(confirmCall.length).toBe(1); // no body: the server uses the payload it stored
    expect(screen.queryByRole("button", { name: /confirm expense/i })).toBeNull();
  });

  it("shows the server's reason when a draft can't be confirmed", async () => {
    api.post.mockImplementation((url) => {
      if (url === "/ai/chat") return ok({ reply: "draft", used_tools: [], mode: "deterministic", expense_draft: expenseDraft });
      return fail(409, { detail: "Anwita is no longer a member of this group." });
    });
    renderAt(<AI />);
    await userEvent.type(screen.getByPlaceholderText(/ask about/i), "add expense{enter}");
    await userEvent.click(await screen.findByRole("button", { name: /confirm expense/i }));
    await waitFor(() => expect(screen.getAllByText(/no longer a member/i).length).toBeGreaterThan(0));
    expect(screen.queryByRole("button", { name: /confirm expense/i })).toBeNull();
  });

  it("cancel calls the cancel endpoint and never confirm", async () => {
    api.post.mockImplementation((url) => {
      if (url === "/ai/chat") return ok({ reply: "draft", used_tools: [], mode: "deterministic", expense_draft: expenseDraft });
      return ok({ status: "CANCELLED" });
    });
    renderAt(<AI />);
    await userEvent.type(screen.getByPlaceholderText(/ask about/i), "add expense{enter}");
    await userEvent.click(await screen.findByRole("button", { name: /cancel/i }));
    await waitFor(() => expect(screen.getByText(/nothing was changed/i)).toBeInTheDocument());
    const urls = api.post.mock.calls.map(([u]) => u);
    expect(urls).toContain(`/ai/drafts/${expenseDraft.draft_id}/cancel`);
    expect(urls.some((u) => u.endsWith("/confirm"))).toBe(false);
  });

  it("lets the user pick between identically named groups and resends with that group_id", async () => {
    const options = [{ label: "Goa Trip · members: Anwi", group_id: "g-1" }, { label: "Goa Trip · members: Anwi, Anwita", group_id: "g-2" }];
    api.post.mockImplementation((url, body) => {
      if (url === "/ai/chat" && !body.group_id) return ok({ reply: "You have 2 groups named “Goa Trip”. Which one do you mean?", used_tools: [], mode: "deterministic", clarification: { question: "Which?", options } });
      if (url === "/ai/chat") return ok({ reply: "Anwita owes you ₹1200 in Goa Trip.", used_tools: [], mode: "deterministic" });
      return fail(500, {});
    });
    renderAt(<AI />);
    await userEvent.type(screen.getByPlaceholderText(/ask about/i), "Who owes me in Goa Trip?{enter}");
    await userEvent.click(await screen.findByRole("button", { name: /Anwi, Anwita/ }));
    await waitFor(() => expect(screen.getByText(/Anwita owes you ₹1200/)).toBeInTheDocument());
    const retry = api.post.mock.calls.filter(([u]) => u === "/ai/chat")[1][1];
    expect(retry.group_id).toBe("g-2");
    expect(retry.message).toBe("Who owes me in Goa Trip?");
  });

  it("renders a friendly error when the request fails", async () => {
    api.post.mockImplementation(() => fail(503, { detail: "AI unavailable" }));
    renderAt(<AI />);
    await userEvent.type(screen.getByPlaceholderText(/ask about/i), "hello{enter}");
    expect(await screen.findByText("AI unavailable")).toBeInTheDocument();
  });
});
