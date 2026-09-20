import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fail, ok, renderAt } from "./helpers.jsx";

vi.mock("../services/api", () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  newIdempotencyKey: () => "key-123",
}));
let currentUser = { id: "u1", name: "Anwi" };
vi.mock("../context/AuthContext.jsx", () => ({ useAuth: () => ({ user: currentUser }) }));

import api from "../services/api";
import AddExpense from "../pages/AddExpense.jsx";
import GroupDetails from "../pages/GroupDetails.jsx";
import Groups from "../pages/Groups.jsx";
import Settlements from "../pages/Settlements.jsx";

const u = (id, name) => ({ id, name, email: `${name}@x.com` });
const group = (creator = "u1") => ({
  id: "g1", name: "Goa Trip", created_by: creator, created_at: "2026-01-01T00:00:00Z",
  members: [{ user: u("u1", "Anwi"), joined_at: "" }, { user: u("u2", "Anwita"), joined_at: "" }],
  balances: [{ user: u("u1", "Anwi"), net_balance: "1200.00" }, { user: u("u2", "Anwita"), net_balance: "-1200.00" }],
  debts: [{ from_user: u("u2", "Anwita"), to_user: u("u1", "Anwi"), amount: "1200.00" }],
});
const expense = { id: "e1", group_id: "g1", description: "Dinner", total_amount: "2400.00", split_type: "EQUAL", paid_by: "u1", paid_by_name: "Anwi", created_at: "2026-01-02T00:00:00Z",
  splits: [{ user_id: "u1", amount: "1200.00" }, { user_id: "u2", amount: "1200.00" }] };

function mockGroupApi(g = group()) {
  api.get.mockImplementation((url) => {
    if (url === "/groups/g1") return ok(g);
    if (url === "/groups/g1/expenses") return ok([expense]);
    return fail(404, {});
  });
}
const details = () => renderAt(<GroupDetails />, { path: "/groups/:groupId", route: "/groups/g1" });

beforeEach(() => { vi.resetAllMocks(); currentUser = { id: "u1", name: "Anwi" }; });

describe("GroupDetails", () => {
  it("shows who pays whom and never a raw negative number", async () => {
    mockGroupApi();
    details();
    expect(await screen.findByText(/Simplest way to settle up/)).toBeInTheDocument();
    expect(screen.getByText(/Anwita pays you/)).toBeInTheDocument();
    expect(screen.queryByText(/-₹|-1,200/)).toBeNull();
  });

  it("delete group needs confirmation; cancelling deletes nothing", async () => {
    mockGroupApi();
    details();
    await userEvent.click(await screen.findByRole("button", { name: /delete group/i }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/permanently deletes the group, its 1 expense/i)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: /cancel/i }));
    expect(api.delete).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("confirming delete calls DELETE /groups/:id and leaves the page", async () => {
    mockGroupApi();
    api.delete.mockImplementation(() => ok({ id: "g1", deleted: {} }));
    details();
    await userEvent.click(await screen.findByRole("button", { name: /delete group/i }));
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: /^delete group$/i }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith("/groups/g1"));
    expect(await screen.findByTestId("elsewhere")).toBeInTheDocument();
  });

  it("a blocked delete shows the server's reason and stays on the page", async () => {
    mockGroupApi();
    api.delete.mockImplementation(() => fail(409, { detail: "A payment is in progress in this group." }));
    details();
    await userEvent.click(await screen.findByRole("button", { name: /delete group/i }));
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: /^delete group$/i }));
    expect(await screen.findByText(/payment is in progress/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Goa Trip" })).toBeInTheDocument();
  });

  it("non-creators see Leave group, not Delete group or rename", async () => {
    currentUser = { id: "u2", name: "Anwita" };
    mockGroupApi(group("u1"));
    details();
    expect(await screen.findByRole("button", { name: /leave group/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /delete group/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /rename group/i })).toBeNull();
  });

  it("deleting an expense asks first and then reloads balances", async () => {
    mockGroupApi();
    api.delete.mockImplementation(() => ok({}));
    details();
    await userEvent.click(await screen.findByRole("button", { name: /delete dinner/i }));
    expect(api.delete).not.toHaveBeenCalled();
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: /delete expense/i }));
    await waitFor(() => expect(api.delete).toHaveBeenCalledWith("/expenses/e1"));
  });

  it("rename saves via PATCH", async () => {
    mockGroupApi();
    api.patch.mockImplementation(() => ok({}));
    details();
    await userEvent.click(await screen.findByRole("button", { name: /rename group/i }));
    const input = screen.getByDisplayValue("Goa Trip");
    await userEvent.clear(input);
    await userEvent.type(input, "Goa 2026{enter}");
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith("/groups/g1", { name: "Goa 2026" }));
  });

  it("load failure shows an error panel with retry", async () => {
    api.get.mockImplementation(() => fail(404, { detail: "nope" }));
    details();
    expect(await screen.findByText(/doesn't exist or you're no longer a member/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
  });
});

describe("AddExpense edit mode", () => {
  it("prefills from the saved expense and saves with PUT (no group_id)", async () => {
    api.get.mockImplementation((url) => (url === "/groups/g1" ? ok(group()) : url === "/expenses/e1" ? ok(expense) : fail(404, {})));
    api.put.mockImplementation(() => ok({}));
    renderAt(<AddExpense />, { path: "/groups/:groupId/expenses/:expenseId/edit", route: "/groups/g1/expenses/e1/edit" });
    expect(await screen.findByDisplayValue("Dinner")).toBeInTheDocument();
    expect(screen.getByDisplayValue("2400.00")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /save changes/i }));
    await waitFor(() => expect(api.put).toHaveBeenCalled());
    const [url, body] = api.put.mock.calls[0];
    expect(url).toBe("/expenses/e1");
    expect(body.group_id).toBeUndefined();
    expect(body.participant_ids).toEqual(["u1", "u2"]);
    expect(api.post).not.toHaveBeenCalled();
  });

  it("surfaces validation errors as readable text, not [object Object]", async () => {
    api.get.mockImplementation((url) => (url === "/groups/g1" ? ok(group()) : fail(404, {})));
    api.post.mockImplementation(() => fail(422, { detail: [{ loc: ["body", "total_amount"], msg: "Value error, Amount can have at most 2 decimal places." }] }));
    renderAt(<AddExpense />, { path: "/groups/:groupId/add-expense", route: "/groups/g1/add-expense" });
    await userEvent.type(await screen.findByPlaceholderText("Hotel"), "Snacks");
    await userEvent.type(screen.getByRole("spinbutton"), "10");
    await userEvent.click(screen.getByRole("button", { name: /add expense/i }));
    expect(await screen.findByText(/total_amount: Amount can have at most 2 decimal places/)).toBeInTheDocument();
  });
});

describe("Groups duplicate names", () => {
  it("offers Open existing / Create anyway instead of silently creating a duplicate", async () => {
    api.get.mockImplementation(() => ok([]));
    api.post.mockImplementationOnce(() => fail(409, { detail: "dup", code: "DUPLICATE_GROUP_NAME", extra: { existing: [{ id: "g9", name: "Goa Trip", member_count: 3 }] } }))
            .mockImplementationOnce(() => ok({ id: "g10", name: "Goa Trip" }));
    renderAt(<Groups />, { path: "/", route: "/" });
    await userEvent.click(await screen.findByRole("button", { name: /new group/i }));
    await userEvent.type(screen.getByPlaceholderText("Goa Trip"), "Goa Trip");
    await userEvent.click(screen.getByRole("button", { name: /create group/i }));
    expect(await screen.findByText(/already have a group called/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open “Goa Trip” · 3 members/i })).toHaveAttribute("href", "/groups/g9");
    await userEvent.click(screen.getByRole("button", { name: /create anyway/i }));
    await waitFor(() => expect(api.post.mock.calls[1][1].allow_duplicate).toBe(true));
    expect(api.post.mock.calls[0][1].allow_duplicate).toBe(false);
  });
});

describe("Settlements manual record", () => {
  const pending = { id: "s1", group_id: "g1", from_user: "u2", to_user: "u1", from_name: "Anwita", to_name: "Anwi", amount: "1200.00", status: "PENDING", method: "UPI", created_at: "2026-01-03T00:00:00Z" };

  it("creditor can mark as paid after confirming; sends the idempotency key", async () => {
    api.get.mockImplementation(() => ok([pending]));
    api.post.mockImplementation(() => ok({ id: "s2", status: "COMPLETED" }));
    renderAt(<Settlements />, { path: "/groups/:groupId/settlements", route: "/groups/g1/settlements" });
    expect(await screen.findByText(/Anwita owes you/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /mark as paid/i }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/Anwita paid you ₹1,200.00 outside SplitPay/)).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
    await userEvent.click(within(dialog).getByRole("button", { name: /yes, mark as paid/i }));
    await waitFor(() => expect(api.post).toHaveBeenCalled());
    const [url, body, cfg] = api.post.mock.calls[0];
    expect(url).toBe("/groups/g1/settlements/record");
    expect(body).toEqual({ from_user: "u2", to_user: "u1", amount: "1200.00" });
    expect(cfg.headers["Idempotency-Key"]).toBe("key-123");
  });

  it("debtor with a payment in flight can continue it after a reload", async () => {
    currentUser = { id: "u2", name: "Anwita" };
    const processing = { ...pending, status: "PROCESSING" };
    api.get.mockImplementation((url) => (url === "/payments" ? ok([{ id: "p1", settlement_id: "s1", status: "PENDING", gateway_order_id: "order_1" }]) : ok([processing])));
    renderAt(<Settlements />, { path: "/groups/:groupId/settlements", route: "/groups/g1/settlements" });
    await userEvent.click(await screen.findByRole("button", { name: /continue payment/i }));
    expect(await screen.findByText(/UPI payment in progress/)).toBeInTheDocument();
    expect(screen.getByText("order_1")).toBeInTheDocument();
  });
});
