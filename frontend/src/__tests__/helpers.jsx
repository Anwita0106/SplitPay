import { render } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";
import { ToastProvider } from "../context/ToastContext.jsx";

// Pages read the signed-in user from AuthContext; provide a stub through vi.mock in each test file.
export function renderAt(ui, { path = "/", route = "/" } = {}) {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <ToastProvider>
        <Routes>
          <Route path={path} element={ui} />
          <Route path="*" element={<div data-testid="elsewhere" />} />
        </Routes>
      </ToastProvider>
    </MemoryRouter>
  );
}
export const ok = (data) => Promise.resolve({ data });
export const fail = (status, data) => Promise.reject({ response: { status, data } });
export { vi };
