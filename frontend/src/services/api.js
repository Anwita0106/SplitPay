import axios from "axios";

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const api = axios.create({ baseURL: BASE_URL });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("splitpay_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      localStorage.removeItem("splitpay_token");
      if (window.location.pathname !== "/login") {
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);

// A fresh, random idempotency key per "Pay Now" click — generated client-side
// per attempt (NOT reused across retries of the SAME logical attempt in a
// naive way; React state holds it for the duration of one payment flow so a
// double-click or a network retry of that same click reuses the same key).
export function newIdempotencyKey() {
  return crypto.randomUUID();
}

export default api;
