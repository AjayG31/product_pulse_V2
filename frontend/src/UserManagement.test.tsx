import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

const adminUser = {
  user_id: "usr_admin_01",
  email: "admin@example.test",
  role: "ADMIN" as const,
  status: "ACTIVE" as const,
  must_change_password: false,
  created_at: "2026-11-24T10:00:00.000Z",
  updated_at: "2026-11-24T10:00:00.000Z",
};
const businessUser = { ...adminUser, user_id: "usr_business_01", email: "business@example.test", role: "BUSINESS_USER" as const };

type ManagedUser = {
  user_id: string;
  email: string;
  role: "ADMIN" | "BUSINESS_USER";
  status: "ACTIVE" | "DEACTIVATED";
  must_change_password: boolean;
  created_at: string;
  updated_at: string;
  deactivated_at?: string | null;
};

const page = (items: ManagedUser[]) => ({
  items,
  page: { page: 1, page_size: 50, total_items: items.length, total_pages: items.length ? 1 : 0 },
});

const targetUser: ManagedUser = {
  ...businessUser,
  user_id: "usr_target_01",
  email: "target@example.test",
  must_change_password: false,
};

function response(status: number, payload: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => payload } as Response;
}

function emptyJobs() {
  return response(200, { items: [], page: { page: 1, page_size: 50, total_items: 0, total_pages: 0 } });
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("Admin user management", () => {
  it("keeps management Admin-only and does not request the user API for a Business User", async () => {
    const calls: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      calls.push(url);
      if (url === "/auth/session") return response(200, { user: businessUser, csrf_token: "business-csrf" });
      throw new Error(`Unexpected request ${url}`);
    });

    render(<App />);

    expect(await screen.findByRole("heading", { name: "Product quality monitoring" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Users" })).not.toBeInTheDocument();
    expect(calls.some((url) => url.startsWith("/admin/users"))).toBe(false);
  });

  it("shows loading, empty, and safe stale-list error states", async () => {
    const user = userEvent.setup();
    let finishList: ((value: Response) => void) | undefined;
    let listRequests = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url === "/auth/session") return response(200, { user: adminUser, csrf_token: "admin-csrf" });
      if (url.startsWith("/admin/ingestion/jobs?")) return emptyJobs();
      if (url.startsWith("/admin/users?")) {
        listRequests += 1;
        if (listRequests === 1) return await new Promise<Response>((resolve) => { finishList = resolve; });
        if (listRequests === 2) return response(200, page([targetUser]));
        return response(503, { detail: "Unsafe account response body", request_id: "req-list-01" });
      }
      throw new Error(`Unexpected request ${url}`);
    });

    render(<App />);
    await user.click(await screen.findByRole("button", { name: "Users" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Loading user accounts");
    finishList?.(response(200, page([])));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("No user accounts match these filters."));
    await user.click(screen.getByRole("button", { name: "Refresh users" }));
    expect(await screen.findByText("target@example.test")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Refresh users" }));
    expect(await screen.findByText(/The user request could not be completed/)).toBeVisible();
    expect(await screen.findByText(/Showing the last successful user list/)).toBeVisible();
    expect(screen.queryByText("Unsafe account response body")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reset password for target@example.test" })).toBeDisabled();
  });

  it("filters users and provisions only an approved role with a write-only password", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("crypto", { randomUUID: () => "create-user-key" });
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    let finishCreate: ((value: Response) => void) | undefined;
    let listResult: ManagedUser[] = [adminUser, targetUser];
    const submittedPassword = "Temporary phrase for new user 2026!";
    const createdUser: ManagedUser = {
      ...targetUser,
      user_id: "usr_new_01",
      email: "new.user@example.test",
      role: "BUSINESS_USER",
      must_change_password: true,
    };
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      calls.push({ url, init });
      if (url === "/auth/session") return response(200, { user: adminUser, csrf_token: "admin-csrf" });
      if (url.startsWith("/admin/ingestion/jobs?")) return emptyJobs();
      if (url.startsWith("/admin/users?") && url.includes("role=BUSINESS_USER")) return response(200, page([targetUser]));
      if (url.startsWith("/admin/users?")) return response(200, page(listResult));
      if (url === "/admin/users" && init?.method === "POST") {
        return await new Promise<Response>((resolve) => { finishCreate = resolve; });
      }
      throw new Error(`Unexpected request ${url}`);
    });

    render(<App />);
    await user.click(await screen.findByRole("button", { name: "Users" }));
    expect(await screen.findByRole("table", { name: "User accounts" })).toBeVisible();
    expect(screen.queryByText("Viewer")).not.toBeInTheDocument();

    await user.click(screen.getByRole("combobox", { name: "Role" }));
    await user.click(screen.getByRole("option", { name: "Business User" }));
    await waitFor(() => expect(calls.some((call) => call.url.includes("role=BUSINESS_USER"))).toBe(true));
    expect(await screen.findByText("target@example.test")).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Provision user" }));
    const createDialog = screen.getByRole("dialog", { name: "Provision user" });
    await user.type(within(createDialog).getByLabelText(/Email/), "new.user@example.test");
    await user.click(within(createDialog).getByRole("combobox", { name: "Role" }));
    await user.click(screen.getByRole("option", { name: "Business User" }));
    const passwordInput = within(createDialog).getByLabelText(/Temporary password/);
    expect(passwordInput).toHaveAttribute("type", "password");
    await user.type(passwordInput, submittedPassword);
    await user.click(within(createDialog).getByRole("button", { name: "Provision user" }));

    await waitFor(() => expect(calls.some((call) => call.url === "/admin/users" && call.init?.method === "POST")).toBe(true));
    expect(passwordInput).toHaveValue("");
    const createCall = calls.find((call) => call.url === "/admin/users" && call.init?.method === "POST");
    expect(createCall?.init?.credentials).toBe("include");
    expect(new Headers(createCall?.init?.headers).get("X-CSRF-Token")).toBe("admin-csrf");
    expect(new Headers(createCall?.init?.headers).get("Idempotency-Key")).toBe("create-user-key");
    expect(JSON.parse(String(createCall?.init?.body))).toEqual({ email: "new.user@example.test", role: "BUSINESS_USER", initial_password: submittedPassword });
    expect(localStorage.length).toBe(0);

    listResult = [adminUser, targetUser, createdUser];
    finishCreate?.(response(201, createdUser));
    expect(await screen.findByText(/Provisioned new.user@example.test/)).toBeVisible();
    expect(screen.queryByText(submittedPassword)).not.toBeInTheDocument();
  });

  it("clears reset passwords after submission and dismissal, and never displays them", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("crypto", { randomUUID: () => "reset-user-key" });
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    let finishReset: ((value: Response) => void) | undefined;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      calls.push({ url, init });
      if (url === "/auth/session") return response(200, { user: adminUser, csrf_token: "admin-csrf" });
      if (url.startsWith("/admin/ingestion/jobs?")) return emptyJobs();
      if (url.startsWith("/admin/users?")) return response(200, page([targetUser]));
      if (url.endsWith("/password-reset") && init?.method === "POST") {
        return await new Promise<Response>((resolve) => { finishReset = resolve; });
      }
      throw new Error(`Unexpected request ${url}`);
    });

    render(<App />);
    await user.click(await screen.findByRole("button", { name: "Users" }));
    await user.click(await screen.findByRole("button", { name: "Reset password for target@example.test" }));
    const resetDialog = screen.getByRole("dialog", { name: "Reset temporary password" });
    const passwordInput = within(resetDialog).getByLabelText(/Temporary password/);
    const submittedPassword = "Temporary reset phrase for target 2026!";
    await user.type(passwordInput, submittedPassword);
    await user.click(within(resetDialog).getByRole("button", { name: "Set temporary password" }));

    await waitFor(() => expect(calls.some((call) => call.url.endsWith("/password-reset") && call.init?.method === "POST")).toBe(true));
    expect(passwordInput).toHaveValue("");
    const resetCall = calls.find((call) => call.url.endsWith("/password-reset"));
    expect(resetCall?.init?.method).toBe("POST");
    expect(new Headers(resetCall?.init?.headers).get("X-CSRF-Token")).toBe("admin-csrf");
    expect(new Headers(resetCall?.init?.headers).get("Idempotency-Key")).toBe("reset-user-key");
    expect(JSON.parse(String(resetCall?.init?.body))).toEqual({ temporary_password: submittedPassword });
    expect(localStorage.length).toBe(0);

    finishReset?.(response(200, { ...targetUser, must_change_password: true }));
    expect(await screen.findByText(/Temporary password reset for target@example.test/)).toBeVisible();
    expect(screen.queryByText(submittedPassword)).not.toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Reset temporary password" })).not.toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Reset password for target@example.test" }));
    const reopenedDialog = screen.getByRole("dialog", { name: "Reset temporary password" });
    const reopenedInput = within(reopenedDialog).getByLabelText(/Temporary password/);
    await user.type(reopenedInput, "Another temporary password 2026!");
    await user.click(within(reopenedDialog).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Reset temporary password" })).not.toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Reset password for target@example.test" }));
    expect(within(screen.getByRole("dialog", { name: "Reset temporary password" })).getByLabelText(/Temporary password/)).toHaveValue("");
    expect(localStorage.length).toBe(0);
  });

  it("handles failed password submission safely and deactivation with an explicit confirmation", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("crypto", { randomUUID: () => "account-action-key" });
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    let isDeactivated = false;
    const deactivatedUser = { ...targetUser, status: "DEACTIVATED" as const, deactivated_at: "2026-11-25T10:00:00.000Z" };
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      calls.push({ url, init });
      if (url === "/auth/session") return response(200, { user: adminUser, csrf_token: "admin-csrf" });
      if (url.startsWith("/admin/ingestion/jobs?")) return emptyJobs();
      if (url.startsWith("/admin/users?")) return response(200, page([isDeactivated ? deactivatedUser : targetUser]));
      if (url === "/admin/users" && init?.method === "POST") return response(422, { detail: "Unsafe echoed secret must not render", request_id: "req-safe-01" });
      if (url === `/admin/users/${targetUser.user_id}` && init?.method === "PATCH") {
        isDeactivated = true;
        return response(200, deactivatedUser);
      }
      if (url.endsWith("/password-reset") && init?.method === "POST") return response(403, { detail: "Forbidden" });
      throw new Error(`Unexpected request ${url}`);
    });

    render(<App />);
    await user.click(await screen.findByRole("button", { name: "Users" }));
    await user.click(screen.getByRole("button", { name: "Provision user" }));
    const createDialog = screen.getByRole("dialog", { name: "Provision user" });
    await user.type(within(createDialog).getByLabelText(/Email/), "new.user@example.test");
    await user.click(within(createDialog).getByRole("combobox", { name: "Role" }));
    await user.click(screen.getByRole("option", { name: "Admin" }));
    const secret = "Temporary password for failing action! 2026";
    const secretInput = within(createDialog).getByLabelText(/Temporary password/);
    await user.type(secretInput, secret);
    await user.click(within(createDialog).getByRole("button", { name: "Provision user" }));
    expect(await screen.findByText(/Check the email and temporary-password requirements/)).toBeVisible();
    expect(screen.queryByText("Unsafe echoed secret must not render")).not.toBeInTheDocument();
    expect(secretInput).toHaveValue("");
    expect(localStorage.length).toBe(0);

    await user.click(within(createDialog).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Provision user" })).not.toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Provision user" }));
    const reopenedCreateDialog = screen.getByRole("dialog", { name: "Provision user" });
    expect(within(reopenedCreateDialog).getByLabelText(/Temporary password/)).toHaveValue("");
    await user.click(within(reopenedCreateDialog).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Provision user" })).not.toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Deactivate target@example.test" }));
    const confirm = screen.getByRole("dialog", { name: "Confirm account deactivation" });
    await user.click(within(confirm).getByRole("button", { name: "Confirm deactivation" }));
    expect(await screen.findByText(/Deactivated target@example.test/)).toBeVisible();
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Confirm account deactivation" })).not.toBeInTheDocument());
    const deactivateCall = calls.find((call) => call.url === `/admin/users/${targetUser.user_id}`);
    expect(deactivateCall?.init?.method).toBe("PATCH");
    expect(new Headers(deactivateCall?.init?.headers).get("X-CSRF-Token")).toBe("admin-csrf");
    expect(new Headers(deactivateCall?.init?.headers).get("Idempotency-Key")).toBe("account-action-key");
    expect(JSON.parse(String(deactivateCall?.init?.body))).toEqual({});

    expect(await screen.findByText("Deactivated")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Reset password for target@example.test" }));
    const deniedDialog = screen.getByRole("dialog", { name: "Reset temporary password" });
    const deniedPassword = within(deniedDialog).getByLabelText(/Temporary password/);
    await user.type(deniedPassword, "Temporary password denied! 2026");
    await user.click(within(deniedDialog).getByRole("button", { name: "Set temporary password" }));
    expect(await within(deniedDialog).findByText("You do not have permission to manage users.")).toBeVisible();
    expect(deniedPassword).toHaveValue("");
  });
});
