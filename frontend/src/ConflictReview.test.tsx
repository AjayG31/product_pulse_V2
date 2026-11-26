import { cleanup, render, screen, waitFor } from "@testing-library/react";
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

type Conflict = {
  conflict_id: string;
  preview_id: string;
  row_number: number;
  conflict_kind: "SOURCE_PAYLOAD" | "REFERENCE_MAPPING";
  existing_feedback_id: string | null;
  source_type: string | null;
  source_record_id: string | null;
  existing_value_hash: string | null;
  incoming_value_hash: string | null;
  mapping_key: string | null;
  state: "PENDING" | "RESOLVED" | "DISMISSED";
  resolution_note: string | null;
  created_at: string;
  resolved_by: string | null;
  resolved_at: string | null;
};

const sourceConflict: Conflict = {
  conflict_id: "cnf_source_01",
  preview_id: "prv_01",
  row_number: 7,
  conflict_kind: "SOURCE_PAYLOAD",
  existing_feedback_id: "fbk_01",
  source_type: "REVIEW",
  source_record_id: "review-007",
  existing_value_hash: "a".repeat(64),
  incoming_value_hash: "b".repeat(64),
  mapping_key: null,
  state: "PENDING",
  resolution_note: null,
  created_at: "2026-11-24T09:30:00.000Z",
  resolved_by: null,
  resolved_at: null,
};
const referenceConflict: Conflict = {
  ...sourceConflict,
  conflict_id: "cnf_reference_01",
  conflict_kind: "REFERENCE_MAPPING",
  source_type: null,
  source_record_id: null,
  existing_feedback_id: null,
  mapping_key: "product_id:p-01",
};

function response(status: number, payload: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => payload } as Response;
}

function emptyJobs() {
  return response(200, { items: [], page: { page: 1, page_size: 50, total_items: 0, total_pages: 0 } });
}

function conflictPage(items: Conflict[]) {
  return response(200, { items, page: { page: 1, page_size: 50, total_items: items.length, total_pages: items.length ? 1 : 0 } });
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("Admin conflict review", () => {
  it("keeps the queue Admin-only and does not call the conflict API for a Business User", async () => {
    const calls: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      calls.push(url);
      if (url === "/auth/session") return response(200, { user: businessUser, csrf_token: "business-csrf" });
      throw new Error(`Unexpected request ${url}`);
    });

    render(<App />);

    expect(await screen.findByRole("heading", { name: "Product quality monitoring" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Conflict review" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Conflict review" })).not.toBeInTheDocument();
    expect(calls.some((url) => url.startsWith("/admin/reconciliation/conflicts"))).toBe(false);
  });

  it("filters and opens safe source-conflict details without showing raw feedback or offering an invalid action", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("crypto", { randomUUID: () => "source-decision-key" });
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    let current = sourceConflict;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      calls.push({ url, init });
      if (url === "/auth/session") return response(200, { user: adminUser, csrf_token: "admin-csrf" });
      if (url.startsWith("/admin/ingestion/jobs?")) return emptyJobs();
      if (url.startsWith("/admin/reconciliation/conflicts?")) {
        if (url.includes("conflict_kind=REFERENCE_MAPPING")) return conflictPage([]);
        return conflictPage(current.state === "PENDING" ? [current] : []);
      }
      if (url === `/admin/reconciliation/conflicts/${current.conflict_id}`) {
        return response(200, { ...current, raw_feedback: "UNSAFE_RAW_FEEDBACK_SENTINEL" });
      }
      if (url.endsWith("/resolve")) {
        current = { ...current, state: "RESOLVED", resolution_note: "Kept source record" };
        return response(200, current);
      }
      throw new Error(`Unexpected request ${url}`);
    });

    render(<App />);
    await user.click(await screen.findByRole("button", { name: "Conflict review" }));
    expect(await screen.findByRole("table", { name: "Conflict queue" })).toBeVisible();
    expect(await screen.findByText("cnf_source_01")).toBeVisible();
    const firstFilterCall = calls.find((call) => call.url.startsWith("/admin/reconciliation/conflicts?"));
    expect(firstFilterCall?.url).toContain("state=PENDING");

    await user.click(screen.getByRole("combobox", { name: "Conflict kind" }));
    await user.click(screen.getByRole("option", { name: "Reference mapping" }));
    await waitFor(() => expect(calls.some((call) => call.url.includes("conflict_kind=REFERENCE_MAPPING"))).toBe(true));
    expect(await screen.findByRole("status")).toHaveTextContent("No conflicts match these filters.");

    await user.click(screen.getByRole("combobox", { name: "Conflict kind" }));
    await user.click(screen.getByRole("option", { name: "All kinds" }));
    await user.click(await screen.findByRole("button", { name: "Review conflict cnf_source_01" }));
    expect(await screen.findByText(/Existing value SHA-256:/)).toBeVisible();
    expect(screen.getByText(/does not link feedback to a product, supplier, or batch/i)).toBeVisible();
    expect(screen.queryByText("UNSAFE_RAW_FEEDBACK_SENTINEL")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Apply incoming reference" })).not.toBeInTheDocument();
    expect(calls.filter((call) => call.url.endsWith("/resolve"))).toHaveLength(0);

    await user.click(screen.getByRole("button", { name: "Keep existing" }));
    expect(await screen.findByRole("dialog", { name: "Confirm Keep existing" })).toBeVisible();
    await user.type(screen.getByRole("textbox", { name: "Resolution note" }), "Keep the original feedback");
    await user.click(screen.getByRole("button", { name: "Confirm decision" }));

    expect(await screen.findByText("Conflict decision recorded.")).toBeVisible();
    const resolveCall = calls.find((call) => call.url.endsWith("/resolve"));
    expect(resolveCall?.init?.method).toBe("POST");
    expect(resolveCall?.init?.credentials).toBe("include");
    expect(new Headers(resolveCall?.init?.headers).get("X-CSRF-Token")).toBe("admin-csrf");
    expect(new Headers(resolveCall?.init?.headers).get("Idempotency-Key")).toBeTruthy();
    expect(JSON.parse(String(resolveCall?.init?.body))).toEqual({
      decision: "KEEP_EXISTING",
      resolution_note: "Keep the original feedback",
    });
  });

  it("offers Apply only after an explicit reference decision and reloads on a stale 409 without retrying", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("crypto", { randomUUID: () => "reference-decision-key" });
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    let detail = referenceConflict;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      calls.push({ url, init });
      if (url === "/auth/session") return response(200, { user: adminUser, csrf_token: "admin-csrf" });
      if (url.startsWith("/admin/ingestion/jobs?")) return emptyJobs();
      if (url.startsWith("/admin/reconciliation/conflicts?")) return conflictPage([detail]);
      if (url === `/admin/reconciliation/conflicts/${detail.conflict_id}`) return response(200, detail);
      if (url.endsWith("/resolve")) {
        detail = { ...detail, existing_value_hash: "c".repeat(64) };
        return response(409, { code: "STALE_REFERENCE_MAPPING", detail: "The reference mapping changed. Reload the conflict before applying it." });
      }
      throw new Error(`Unexpected request ${url}`);
    });

    render(<App />);
    await user.click(await screen.findByRole("button", { name: "Conflict review" }));
    await user.click(await screen.findByRole("button", { name: "Review conflict cnf_reference_01" }));
    expect(await screen.findByText("Mapping key: product_id:p-01")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Apply incoming reference" }));
    await user.type(screen.getByRole("textbox", { name: "Resolution note" }), "Apply the reviewed reference row");
    await user.click(screen.getByRole("button", { name: "Confirm decision" }));

    expect(await screen.findByText(/This conflict changed after it was opened/)).toBeVisible();
    const resolveCalls = calls.filter((call) => call.url.endsWith("/resolve"));
    expect(resolveCalls).toHaveLength(1);
    expect(JSON.parse(String(resolveCalls[0].init?.body))).toEqual({
      decision: "APPLY_INCOMING_REFERENCE",
      resolution_note: "Apply the reviewed reference row",
      expected_existing_value_hash: "a".repeat(64),
    });
    await waitFor(() => expect(calls.filter((call) => call.url === "/admin/reconciliation/conflicts/cnf_reference_01").length).toBeGreaterThanOrEqual(2));
    expect(screen.getByText(`Existing value SHA-256: ${"c".repeat(64)}`)).toBeVisible();
  });

  it("disables decisions when refreshed details fail and only stale details remain", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("crypto", { randomUUID: () => "stale-decision-key" });
    let detailRequests = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url === "/auth/session") return response(200, { user: adminUser, csrf_token: "admin-csrf" });
      if (url.startsWith("/admin/ingestion/jobs?")) return emptyJobs();
      if (url.startsWith("/admin/reconciliation/conflicts?")) return conflictPage([referenceConflict]);
      if (url === `/admin/reconciliation/conflicts/${referenceConflict.conflict_id}`) {
        detailRequests += 1;
        return detailRequests === 1 ? response(200, referenceConflict) : response(503, { detail: "Unavailable" });
      }
      if (url.endsWith("/resolve")) return response(409, { code: "STALE_REFERENCE_MAPPING", detail: "Reload required." });
      throw new Error(`Unexpected request ${url}`);
    });

    render(<App />);
    await user.click(await screen.findByRole("button", { name: "Conflict review" }));
    await user.click(await screen.findByRole("button", { name: "Review conflict cnf_reference_01" }));
    expect(await screen.findByRole("button", { name: "Apply incoming reference" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Apply incoming reference" }));
    await user.type(screen.getByRole("textbox", { name: "Resolution note" }), "Reviewed before stale refresh");
    await user.click(screen.getByRole("button", { name: "Confirm decision" }));

    expect(await screen.findByText(/This conflict changed after it was opened/)).toBeVisible();
    expect(await screen.findByText("Showing previously loaded details; refresh before deciding.")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Keep existing" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Apply incoming reference" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Dismiss conflict" })).not.toBeInTheDocument();
  });

  it("shows API loading, empty, and safe permission-error states", async () => {
    const user = userEvent.setup();
    let finishList: ((value: Response) => void) | undefined;
    let denied = false;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url === "/auth/session") return response(200, { user: adminUser, csrf_token: "admin-csrf" });
      if (url.startsWith("/admin/ingestion/jobs?")) return emptyJobs();
      if (url.startsWith("/admin/reconciliation/conflicts?")) {
        if (denied) return response(403, { detail: "Forbidden" });
        return await new Promise<Response>((resolve) => { finishList = resolve; });
      }
      throw new Error(`Unexpected request ${url}`);
    });

    render(<App />);
    await user.click(await screen.findByRole("button", { name: "Conflict review" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Loading conflict queue");
    finishList?.(conflictPage([]));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("No conflicts match these filters."));

    denied = true;
    await user.click(screen.getByRole("button", { name: "Refresh queue" }));
    expect(await screen.findByText("You do not have permission to review conflicts.")).toBeVisible();
    expect(screen.queryByRole("button", { name: /Review conflict/ })).not.toBeInTheDocument();
  });
});
