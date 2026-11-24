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
    let recovered = false;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      calls.push({ url, init });
      if (url === "/auth/session") return response(200, { user: adminUser, csrf_token: "admin-session-csrf" });
      if (url === "/admin/ingestion/jobs?page=1&page_size=50") {
        return response(200, {
          items: [{
            job_id: "ing_retry",
            preview_id: "prv_retry",
            status: recovered ? "QUEUED" : "FAILED",
            processing_mode: "INCREMENTAL_RESPONSES",
            created_at: "2026-11-24T10:00:00.000Z",
            counts: { total_rows: 1, accepted_rows: 1, rejected_rows: 0, persisted_feedback: 1 },
            retry_eligibility: recovered
              ? { eligible: false, reason_code: "WORK_IN_PROGRESS" }
              : { eligible: true, reason_code: "ELIGIBLE" },
            last_error_code: recovered ? null : "INGESTION_REPLAY_SAFE",
            rejection_report: { available: true, href: "/admin/ingestion/previews/prv_retry/rejection-report" },
          }],
          page: { page: 1, page_size: 50, total_items: 1, total_pages: 1 },
        });
      }
      if (url === "/admin/ingestion/jobs/ing_retry/retry") {
        recovered = true;
        return response(202, { run: { background_job_id: "bgj_recovery_01" } });
      }
      if (url === "/admin/ingestion/previews/prv_retry") {
        return response(200, { upload_kind: "REVIEWS" });
      }
      if (url === "/admin/ingestion/previews") {
        return response(201, {
          preview_id: "prv_01",
          upload_kind: "REVIEWS",
          original_filename: "reviews.csv",
          file_size_bytes: 123,
          verified_sha256: "a".repeat(64),
          parser_contract_version: "reviews-v1",
          state: "READY",
          counts: { total_rows: 2, accepted_rows: 1, rejected_rows: 1, duplicate_noop_rows: 0, conflict_rows: 0 },
          rejection_report: {
            available: true,
            href: "/admin/ingestion/previews/prv_01/rejection-report",
            content_type: "text/csv",
          },
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
    expect(await screen.findByRole("heading", { name: "Ingestion job status" })).toBeVisible();
    expect(screen.getByText("INGESTION_REPLAY_SAFE")).toBeVisible();
    expect(screen.getByText("REVIEWS")).toBeVisible();
    expect(screen.getByRole("link", { name: "Report" })).toHaveAttribute(
      "href",
      "/admin/ingestion/previews/prv_retry/rejection-report",
    );
    expect(screen.getByRole("button", { name: "Retry" })).toBeVisible();
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
    expect(screen.getByRole("link", { name: "Download rejection report" })).toHaveAttribute(
      "href",
      "/admin/ingestion/previews/prv_01/rejection-report",
    );
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

    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Recovery queued as run bgj_recovery_01.");
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
    const retryCall = calls.find((call) => call.url === "/admin/ingestion/jobs/ing_retry/retry");
    expect(retryCall?.init?.method).toBe("POST");
    expect(new Headers(retryCall?.init?.headers).get("X-CSRF-Token")).toBe("admin-session-csrf");
    expect(new Headers(retryCall?.init?.headers).get("Idempotency-Key")).toBeTruthy();
  });

  it("refreshes retry eligibility and shows the server reason after a conflict", async () => {
    const user = userEvent.setup();
    let listCalls = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      if (url === "/auth/session") return response(200, { user: adminUser, csrf_token: "admin-session-csrf" });
      if (url === "/admin/ingestion/jobs?page=1&page_size=50") {
        listCalls += 1;
        return response(200, {
          items: [{
            job_id: "ing_race",
            preview_id: "prv_race",
            status: listCalls === 1 ? "FAILED" : "QUEUED",
            processing_mode: "HISTORICAL_BATCH",
            created_at: "2026-11-24T10:00:00.000Z",
            counts: { total_rows: 2, accepted_rows: 2, rejected_rows: 0, persisted_feedback: 2 },
            retry_eligibility: listCalls === 1
              ? { eligible: true, reason_code: "ELIGIBLE" }
              : { eligible: false, reason_code: "WORK_IN_PROGRESS" },
            last_error_code: listCalls === 1 ? "INGESTION_REPLAY_SAFE" : null,
          }],
          page: { page: 1, page_size: 50, total_items: 1, total_pages: 1 },
        });
      }
      if (url === "/admin/ingestion/previews/prv_race") return response(200, { upload_kind: "RETURNS" });
      if (url === "/admin/ingestion/jobs/ing_race/retry") {
        return response(409, {
          code: "retry_not_eligible",
          detail: "This ingestion work is not eligible for recovery.",
          retry_eligibility: { eligible: false, reason_code: "WORK_IN_PROGRESS" },
        });
      }
      throw new Error(`Unexpected request ${url}`);
    });

    render(<App />);
    expect(await screen.findByRole("button", { name: "Retry" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Current eligibility: WORK_IN_PROGRESS.");
    expect(await screen.findByText("WORK_IN_PROGRESS")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
    expect(listCalls).toBe(2);
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
