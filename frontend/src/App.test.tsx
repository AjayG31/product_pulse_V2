import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

const regularUser = {
  user_id: "usr_business_01",
  email: "business@example.test",
  role: "BUSINESS_USER" as const,
  status: "ACTIVE" as const,
  must_change_password: false,
  created_at: "2026-11-22T10:00:00.000Z",
  updated_at: "2026-11-22T10:00:00.000Z",
};

const temporaryUser = { ...regularUser, must_change_password: true };
const adminUser = { ...regularUser, user_id: "usr_admin_01", email: "admin@example.test", role: "ADMIN" as const };

function response(status: number, payload: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  } as Response;
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("authentication flows", () => {
  it("bootstraps CSRF, signs in, and keeps tokens out of browser storage", async () => {
    const user = userEvent.setup();
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      calls.push({ url, init });
      if (url === "/auth/session") return response(401, {});
      if (url === "/auth/csrf") return response(200, { csrf_token: "prelogin-csrf" });
      if (url === "/auth/login") return response(200, { user: regularUser, csrf_token: "session-csrf" });
      throw new Error(`Unexpected request ${url}`);
    });
    const storageWrite = vi.spyOn(Storage.prototype, "setItem");

    render(<App />);
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeVisible();
    await user.type(screen.getByRole("textbox", { name: "Email" }), "business@example.test");
    await user.type(screen.getByLabelText(/^Password/), "Temporary phrase 2026!");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("heading", { name: "Product quality monitoring" })).toBeVisible();
    expect(screen.getByText(/Signed in as business@example.test/)).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Admin CSV upload and preview" })).not.toBeInTheDocument();
    expect(calls.map((call) => call.url)).toEqual(["/auth/session", "/auth/csrf", "/auth/login"]);
    expect(calls[2].init?.credentials).toBe("include");
    expect(JSON.parse(String(calls[2].init?.body))).toEqual({ email: "business@example.test", password: "Temporary phrase 2026!" });
    expect(new Headers(calls[2].init?.headers).get("X-CSRF-Token")).toBe("prelogin-csrf");
    expect(storageWrite).not.toHaveBeenCalled();
  });

  it("shows Admin templates and maps columns before creating a safe preview", async () => {
    const user = userEvent.setup();
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      calls.push({ url, init });
      if (url === "/auth/session") return response(200, { user: adminUser, csrf_token: "admin-session-csrf" });
      if (url === "/admin/ingestion/previews") {
        return response(201, {
          preview_id: "prv_01",
          upload_kind: "REVIEWS",
          original_filename: "reviews.csv",
          file_size_bytes: 123,
          verified_sha256: "a".repeat(64),
          parser_contract_version: "reviews-v1",
          state: "READY",
          counts: { total_rows: 1, accepted_rows: 1, rejected_rows: 0, duplicate_noop_rows: 0, conflict_rows: 0 },
        });
      }
      if (url === "/admin/ingestion/previews/prv_01/rows?page=1&page_size=50") {
        return response(200, { items: [{ row_number: 1, row_status: "ACCEPTED", source_record_id: "r1", rejection_codes: [] }] });
      }
      if (url === "/admin/ingestion/previews/prv_01/confirm") {
        return response(202, {
          job_id: "ing_01",
          status: "QUEUED",
          processing_mode: "HISTORICAL_BATCH",
          counts: { persisted_feedback: 1 },
        });
      }
      throw new Error(`Unexpected request ${url}`);
    });

    render(<App />);
    expect(await screen.findByRole("heading", { name: "Admin CSV upload and preview" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Download Reviews template" })).toHaveAttribute("href", "/admin/ingestion/templates/REVIEWS");
    const csv = new File([
      "review_id,product_id,supplier_id,batch_id,review_timestamp,review_text\r\nr1,p1,,,2026-11-20T09:10:11Z,good product\r\n",
    ], "reviews.csv", { type: "text/csv" });
    await user.upload(screen.getByLabelText("CSV file"), csv);

    const targets = ["review_id", "product_id", "supplier_id", "batch_id", "review_timestamp", "review_text"];
    for (const [index, target] of targets.entries()) {
      const selector = screen.getByRole("combobox", { name: `Canonical field for source column ${index + 1}` });
      await user.click(selector);
      await user.click(screen.getByRole("option", { name: `${target} (required)` }));
    }
    await user.click(screen.getByRole("button", { name: "Create preview" }));

    expect(await screen.findByRole("heading", { name: "Preview prv_01" })).toBeVisible();
    expect(screen.getByText(/State: READY/)).toBeVisible();
    expect(screen.getByText("r1")).toBeVisible();
    const uploadCall = calls.find((call) => call.url === "/admin/ingestion/previews");
    expect(uploadCall?.init?.credentials).toBe("include");
    expect(new Headers(uploadCall?.init?.headers).get("X-CSRF-Token")).toBe("admin-session-csrf");
    expect(new Headers(uploadCall?.init?.headers).get("Idempotency-Key")).toBeTruthy();
    const body = uploadCall?.init?.body as FormData;
    expect(body.get("upload_kind")).toBe("REVIEWS");
    expect(JSON.parse(String(body.get("column_mappings")))).toEqual(targets.map((target_field, source_column_index) => ({
      source_column_index,
      source_header: target_field,
      target_field,
    })));
    expect(body.get("file")).toBeInstanceOf(File);
    expect(screen.getByRole("combobox", { name: "Processing mode" })).toBeVisible();
    const confirmButton = screen.getByRole("button", { name: "Confirm import" });
    expect(confirmButton).toBeDisabled();
    await user.click(screen.getByRole("combobox", { name: "Processing mode" }));
    await user.click(screen.getByRole("option", { name: "Historical batch" }));
    expect(confirmButton).toBeEnabled();
    await user.click(confirmButton);
    expect(await screen.findByRole("alert")).toHaveTextContent("Import confirmed. Job ing_01 is queued with 1 feedback records persisted.");

    const confirmCall = calls.find((call) => call.url === "/admin/ingestion/previews/prv_01/confirm");
    expect(confirmCall?.init?.method).toBe("POST");
    expect(confirmCall?.init?.credentials).toBe("include");
    expect(new Headers(confirmCall?.init?.headers).get("X-CSRF-Token")).toBe("admin-session-csrf");
    expect(new Headers(confirmCall?.init?.headers).get("Idempotency-Key")).toBeTruthy();
    expect(JSON.parse(String(confirmCall?.init?.body))).toEqual({
      verified_sha256: "a".repeat(64),
      processing_mode: "HISTORICAL_BATCH",
    });
  });

  it("forces a temporary-password change, clears submitted values, and rotates session state", async () => {
    const user = userEvent.setup();
    const changes: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === "/auth/session") return response(200, { user: temporaryUser, csrf_token: "temporary-session-csrf" });
      if (url === "/auth/password-change") {
        changes.push(String(init?.body));
        if (changes.length === 1) {
          return response(422, { detail: "Choose a compliant password." });
        }
        return response(200, { user: regularUser, csrf_token: "rotated-session-csrf" });
      }
      throw new Error(`Unexpected request ${url}`);
    });

    render(<App />);
    expect(await screen.findByRole("heading", { name: "Change your temporary password" })).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Product quality monitoring" })).not.toBeInTheDocument();
    const temporaryInput = screen.getByLabelText(/^Temporary password/) as HTMLInputElement;
    const newPasswordInput = screen.getByLabelText(/^New password/) as HTMLInputElement;
    await user.type(temporaryInput, "Temporary phrase 2026!");
    await user.type(newPasswordInput, "A new permanent phrase 2026!");
    await user.click(screen.getByRole("button", { name: "Change password" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Choose a compliant password.");
    expect(temporaryInput.value).toBe("");
    expect(newPasswordInput.value).toBe("");

    await user.type(temporaryInput, "Temporary phrase 2026!");
    await user.type(newPasswordInput, "A new permanent phrase 2026!");
    await user.click(screen.getByRole("button", { name: "Change password" }));
    expect(await screen.findByRole("heading", { name: "Product quality monitoring" })).toBeVisible();
    expect(JSON.parse(changes[1])).toEqual({
      current_password: "Temporary phrase 2026!",
      new_password: "A new permanent phrase 2026!",
    });
    await waitFor(() => expect(screen.queryByLabelText(/^Temporary password/)).not.toBeInTheDocument());
  });
});
