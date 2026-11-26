import { useEffect, useRef, useState } from "react";
import {
  Alert,
  Button,
  Card,
  CardContent,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";

import { useAuth } from "./auth";

type ConflictKind = "SOURCE_PAYLOAD" | "REFERENCE_MAPPING";
type ConflictState = "PENDING" | "RESOLVED" | "DISMISSED";
type ConflictDecision = "KEEP_EXISTING" | "APPLY_INCOMING_REFERENCE" | "DISMISS";
type Conflict = {
  conflict_id: string;
  preview_id: string;
  row_number: number;
  conflict_kind: ConflictKind;
  existing_feedback_id: string | null;
  source_type: string | null;
  source_record_id: string | null;
  existing_value_hash: string | null;
  incoming_value_hash: string | null;
  mapping_key: string | null;
  state: ConflictState;
  resolution_note: string | null;
  created_at: string;
  resolved_by: string | null;
  resolved_at: string | null;
};
type ConflictPage = {
  items: Conflict[];
  page: { page: number; page_size: number; total_items: number; total_pages: number };
};
type Problem = { detail?: string; request_id?: string };

const CONFLICTS_URL = "/admin/reconciliation/conflicts";
const PAGE_SIZE = 50;

function safeLabel(value: string | null | undefined): string {
  return value ?? "—";
}

function decisionLabel(decision: ConflictDecision): string {
  switch (decision) {
    case "KEEP_EXISTING":
      return "Keep existing";
    case "APPLY_INCOMING_REFERENCE":
      return "Apply incoming reference";
    case "DISMISS":
      return "Dismiss conflict";
  }
}

async function apiError(response: Response): Promise<string> {
  let problem: Problem = {};
  try {
    problem = (await response.json()) as Problem;
  } catch {
    // Keep a stable message when the response is not a problem document.
  }
  if (response.status === 401) return "Your session has expired. Sign in again.";
  if (response.status === 403) return "You do not have permission to review conflicts.";
  const detail = problem.detail ?? "The conflict request could not be completed.";
  return problem.request_id ? `${detail} (Request ID: ${problem.request_id})` : detail;
}

export function AdminConflictReview() {
  const { csrfToken } = useAuth();
  const [kindFilter, setKindFilter] = useState<"" | ConflictKind>("");
  const [stateFilter, setStateFilter] = useState<ConflictState>("PENDING");
  const [pageNumber, setPageNumber] = useState(1);
  const [reloadKey, setReloadKey] = useState(0);
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const [pageInfo, setPageInfo] = useState<ConflictPage["page"]>({
    page: 1,
    page_size: PAGE_SIZE,
    total_items: 0,
    total_pages: 0,
  });
  const [queueLoading, setQueueLoading] = useState(true);
  const [queueError, setQueueError] = useState("");
  const [queueStale, setQueueStale] = useState(false);
  const queueHasLoaded = useRef(false);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<Conflict | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [detailStale, setDetailStale] = useState(false);
  const [selectedDecision, setSelectedDecision] = useState<ConflictDecision | null>(null);
  const [resolutionNote, setResolutionNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [actionError, setActionError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  useEffect(() => {
    let active = true;
    const query = new URLSearchParams({ state: stateFilter, page: String(pageNumber), page_size: String(PAGE_SIZE) });
    if (kindFilter) query.set("conflict_kind", kindFilter);
    setQueueLoading(true);
    setQueueError("");
    fetch(`${CONFLICTS_URL}?${query.toString()}`, { credentials: "include" })
      .then(async (response) => {
        if (!response.ok) throw new Error(await apiError(response));
        return (await response.json()) as ConflictPage;
      })
      .then((result) => {
        if (!active) return;
        setConflicts(result.items);
        setPageInfo(result.page);
        setQueueStale(false);
        queueHasLoaded.current = true;
      })
      .catch((error: unknown) => {
        if (!active) return;
        setQueueError(error instanceof Error ? error.message : "The conflict queue could not be loaded.");
        setQueueStale(queueHasLoaded.current);
      })
      .finally(() => {
        if (active) setQueueLoading(false);
      });
    return () => {
      active = false;
    };
  }, [kindFilter, stateFilter, pageNumber, reloadKey]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      setDetailLoading(false);
      setDetailError("");
      setDetailStale(false);
      return;
    }
    let active = true;
    setDetailLoading(true);
    setDetailError("");
    fetch(`${CONFLICTS_URL}/${encodeURIComponent(selectedId)}`, { credentials: "include" })
      .then(async (response) => {
        if (!response.ok) throw new Error(await apiError(response));
        return (await response.json()) as Conflict;
      })
      .then((result) => {
        if (!active) return;
        setDetail(result);
        setDetailStale(false);
      })
      .catch((error: unknown) => {
        if (!active) return;
        setDetailError(error instanceof Error ? error.message : "Conflict details could not be loaded.");
        setDetailStale(detail !== null);
      })
      .finally(() => {
        if (active) setDetailLoading(false);
      });
    return () => {
      active = false;
    };
  }, [selectedId, reloadKey]);

  function openDecision(decision: ConflictDecision) {
    setSelectedDecision(decision);
    setResolutionNote("");
    setActionError("");
    setSuccessMessage("");
  }

  async function submitDecision() {
    if (!detail || !selectedDecision || !csrfToken || !resolutionNote.trim()) return;
    if (selectedDecision === "APPLY_INCOMING_REFERENCE" && !detail.existing_value_hash) return;
    setSaving(true);
    setActionError("");
    setSuccessMessage("");
    const body: {
      decision: ConflictDecision;
      resolution_note: string;
      expected_existing_value_hash?: string;
    } = { decision: selectedDecision, resolution_note: resolutionNote.trim() };
    if (selectedDecision === "APPLY_INCOMING_REFERENCE" && detail.existing_value_hash) {
      body.expected_existing_value_hash = detail.existing_value_hash;
    }
    try {
      const response = await fetch(`${CONFLICTS_URL}/${encodeURIComponent(detail.conflict_id)}/resolve`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrfToken,
          "Idempotency-Key": crypto.randomUUID(),
        },
        body: JSON.stringify(body),
      });
      if (response.status === 409) {
        setActionError("This conflict changed after it was opened. The latest state was reloaded; review it and choose again.");
        setSelectedDecision(null);
        setResolutionNote("");
        setReloadKey((value) => value + 1);
        return;
      }
      if (!response.ok) throw new Error(await apiError(response));
      const updated = (await response.json()) as Conflict;
      setDetail(updated);
      setSelectedDecision(null);
      setResolutionNote("");
      setSuccessMessage("Conflict decision recorded.");
      setReloadKey((value) => value + 1);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "The conflict decision could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Stack spacing={2}>
      <Card variant="outlined">
        <CardContent>
          <Stack spacing={2}>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}>
              <div>
                <Typography component="h2" variant="h5">Conflict review</Typography>
                <Typography color="text.secondary">
                  Review source and reference conflicts explicitly. This workflow does not change feedback linkage.
                </Typography>
              </div>
              <Button onClick={() => setReloadKey((value) => value + 1)} disabled={queueLoading}>
                Refresh queue
              </Button>
            </Stack>

            <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
              <FormControl size="small" sx={{ minWidth: 220 }}>
                <InputLabel id="conflict-kind-label">Conflict kind</InputLabel>
                <Select
                  labelId="conflict-kind-label"
                  label="Conflict kind"
                  value={kindFilter}
                  onChange={(event) => { setKindFilter(event.target.value as "" | ConflictKind); setPageNumber(1); }}
                >
                  <MenuItem value="">All kinds</MenuItem>
                  <MenuItem value="SOURCE_PAYLOAD">Source payload</MenuItem>
                  <MenuItem value="REFERENCE_MAPPING">Reference mapping</MenuItem>
                </Select>
              </FormControl>
              <FormControl size="small" sx={{ minWidth: 220 }}>
                <InputLabel id="conflict-state-label">State</InputLabel>
                <Select
                  labelId="conflict-state-label"
                  label="State"
                  value={stateFilter}
                  onChange={(event) => { setStateFilter(event.target.value as ConflictState); setPageNumber(1); }}
                >
                  <MenuItem value="PENDING">Pending</MenuItem>
                  <MenuItem value="RESOLVED">Resolved</MenuItem>
                  <MenuItem value="DISMISSED">Dismissed</MenuItem>
                </Select>
              </FormControl>
            </Stack>

            {queueLoading && <Typography role="status">Loading conflict queue…</Typography>}
            {queueError && <Alert severity="error">{queueError}</Alert>}
            {queueStale && <Alert severity="warning">Showing the last successful queue result; it may be stale.</Alert>}
            {!queueLoading && !queueError && conflicts.length === 0 && (
              <Typography role="status">No conflicts match these filters.</Typography>
            )}
            {!queueLoading && conflicts.length > 0 && (
              <>
                <Table size="small" aria-label="Conflict queue">
                  <TableHead>
                    <TableRow>
                      <TableCell>Conflict ID</TableCell>
                      <TableCell>Kind</TableCell>
                      <TableCell>Source or mapping key</TableCell>
                      <TableCell>State</TableCell>
                      <TableCell>Created (UTC)</TableCell>
                      <TableCell>Review</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {conflicts.map((conflict) => (
                      <TableRow key={conflict.conflict_id}>
                        <TableCell>{conflict.conflict_id}</TableCell>
                        <TableCell>{conflict.conflict_kind}</TableCell>
                        <TableCell>{safeLabel(conflict.source_record_id ?? conflict.mapping_key)}</TableCell>
                        <TableCell>{conflict.state}</TableCell>
                        <TableCell>{conflict.created_at} (UTC)</TableCell>
                        <TableCell>
                          <Button onClick={() => {
                            setSelectedId(conflict.conflict_id);
                            setDetail(null);
                            setDetailStale(false);
                            setSelectedDecision(null);
                            setResolutionNote("");
                            setSuccessMessage("");
                            setActionError("");
                          }} aria-label={`Review conflict ${conflict.conflict_id}`}>
                            Review
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                  <Button onClick={() => setPageNumber((value) => Math.max(1, value - 1))} disabled={queueLoading || pageInfo.page <= 1}>
                    Previous page
                  </Button>
                  <Typography aria-live="polite">
                    Page {pageInfo.page} of {Math.max(1, pageInfo.total_pages)} ({pageInfo.total_items} conflicts)
                  </Typography>
                  <Button onClick={() => setPageNumber((value) => value + 1)} disabled={queueLoading || pageInfo.page >= pageInfo.total_pages}>
                    Next page
                  </Button>
                </Stack>
              </>
            )}
          </Stack>
        </CardContent>
      </Card>

      {selectedId && (
        <Card variant="outlined">
          <CardContent>
            <Stack spacing={2}>
              <Typography component="h3" variant="h6">Conflict details</Typography>
              {detailLoading && <Typography role="status">Loading conflict details…</Typography>}
              {detailError && <Alert severity="error">{detailError}</Alert>}
              {detailStale && <Alert severity="warning">Showing previously loaded details; refresh before deciding.</Alert>}
              {detail && !detailLoading && (
                <>
                  <Stack spacing={0.5}>
                    <Typography>Conflict: {detail.conflict_id}</Typography>
                    <Typography>Kind: {detail.conflict_kind}</Typography>
                    <Typography>State: {detail.state}</Typography>
                    <Typography>Preview: {detail.preview_id}</Typography>
                    <Typography>Row: {detail.row_number}</Typography>
                    <Typography>Source type: {safeLabel(detail.source_type)}</Typography>
                    <Typography>Source record ID: {safeLabel(detail.source_record_id)}</Typography>
                    <Typography>Existing feedback ID: {safeLabel(detail.existing_feedback_id)}</Typography>
                    <Typography>Mapping key: {safeLabel(detail.mapping_key)}</Typography>
                    <Typography>Existing value SHA-256: {safeLabel(detail.existing_value_hash)}</Typography>
                    <Typography>Incoming value SHA-256: {safeLabel(detail.incoming_value_hash)}</Typography>
                    <Typography>Created: {detail.created_at} (UTC)</Typography>
                    {detail.resolution_note && <Typography>Resolution note: {detail.resolution_note}</Typography>}
                    {detail.resolved_by && <Typography>Reviewed by: {detail.resolved_by}</Typography>}
                    {detail.resolved_at && <Typography>Reviewed at: {detail.resolved_at} (UTC)</Typography>}
                  </Stack>
                  <Alert severity="info">
                    Conflict resolution records a decision about this import row. It does not link feedback to a product, supplier, or batch.
                    Use the separate linkage reconciliation workflow for linkage changes.
                  </Alert>
                  {detail.state === "PENDING" && !detailLoading && !detailError && !detailStale && (
                    <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                      <Button variant="outlined" onClick={() => openDecision("KEEP_EXISTING")}>Keep existing</Button>
                      {detail.conflict_kind === "REFERENCE_MAPPING" && detail.existing_value_hash && (
                        <Button variant="contained" onClick={() => openDecision("APPLY_INCOMING_REFERENCE")}>
                          Apply incoming reference
                        </Button>
                      )}
                      <Button color="inherit" onClick={() => openDecision("DISMISS")}>Dismiss conflict</Button>
                    </Stack>
                  )}
                  {detail.state !== "PENDING" && <Typography>This conflict has already been reviewed; no further decision is available.</Typography>}
                  {actionError && <Alert severity="error">{actionError}</Alert>}
                  {successMessage && <Alert severity="success">{successMessage}</Alert>}
                </>
              )}
            </Stack>
          </CardContent>
        </Card>
      )}

      <Dialog open={selectedDecision !== null} onClose={() => { if (!saving) setSelectedDecision(null); }}>
        <DialogTitle>Confirm {selectedDecision ? decisionLabel(selectedDecision) : "conflict decision"}</DialogTitle>
        <DialogContent>
          <Stack spacing={1} sx={{ pt: 1 }}>
            <Typography>
              {detail?.conflict_kind === "SOURCE_PAYLOAD"
                ? "The original source feedback will remain unchanged."
                : "This records only the selected reference mapping decision."}
            </Typography>
            <TextField
              autoFocus
              required
              multiline
              minRows={3}
              label="Resolution note"
              value={resolutionNote}
              slotProps={{ htmlInput: { maxLength: 2000 } }}
              onChange={(event) => setResolutionNote(event.target.value)}
              helperText={`${resolutionNote.length}/2000 characters`}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSelectedDecision(null)} disabled={saving}>Cancel</Button>
          <Button onClick={submitDecision} disabled={saving || !resolutionNote.trim() || !csrfToken} variant="contained">
            {saving ? "Saving…" : "Confirm decision"}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
