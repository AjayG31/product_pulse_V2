import { useMemo, useState, type ChangeEvent } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
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
  Typography,
} from "@mui/material";

import { useAuth } from "./auth";

type UploadKind = "REVIEWS" | "RETURNS" | "PRODUCT_REFERENCE" | "SUPPLIER_REFERENCE" | "BATCH_REFERENCE";
type PreviewRow = {
  row_number: number;
  row_status: string;
  source_type?: string;
  source_record_id?: string;
  rejection_codes: string[];
  rejection_detail?: string;
};
type Preview = {
  preview_id: string;
  upload_kind: UploadKind;
  original_filename: string;
  file_size_bytes: number;
  verified_sha256: string;
  parser_contract_version: string;
  state: string;
  counts: {
    total_rows: number;
    accepted_rows: number;
    rejected_rows: number;
    duplicate_noop_rows: number;
    conflict_rows: number;
  };
};
type ProcessingMode = "HISTORICAL_BATCH" | "INCREMENTAL_RESPONSES";
type IngestionJob = {
  job_id: string;
  status: string;
  processing_mode: ProcessingMode;
  counts: { persisted_feedback: number };
};

const TARGETS: Record<UploadKind, { required: string[]; optional: string[] }> = {
  REVIEWS: {
    required: ["review_id", "product_id", "supplier_id", "batch_id", "review_timestamp", "review_text"],
    optional: ["rating", "source"],
  },
  RETURNS: {
    required: ["return_id", "product_id", "supplier_id", "batch_id", "return_timestamp", "return_reason"],
    optional: ["return_quantity", "return_category"],
  },
  PRODUCT_REFERENCE: { required: ["product_id"], optional: ["name", "category"] },
  SUPPLIER_REFERENCE: { required: ["supplier_id"], optional: ["name"] },
  BATCH_REFERENCE: { required: ["batch_id", "product_id", "supplier_id"], optional: [] },
};

const KINDS: Array<{ value: UploadKind; label: string }> = [
  { value: "REVIEWS", label: "Reviews" },
  { value: "RETURNS", label: "Returns" },
  { value: "PRODUCT_REFERENCE", label: "Product reference" },
  { value: "SUPPLIER_REFERENCE", label: "Supplier reference" },
  { value: "BATCH_REFERENCE", label: "Batch reference" },
];

function parseFirstCsvRecord(source: string): string[] {
  const text = source.startsWith("\ufeff") ? source.slice(1) : source;
  const values: string[] = [];
  let value = "";
  let quoted = false;
  let atFieldStart = true;
  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (quoted) {
      if (character === '"') {
        if (text[index + 1] === '"') {
          value += '"';
          index += 1;
        } else {
          quoted = false;
        }
      } else {
        value += character;
      }
      continue;
    }
    if (character === '"' && atFieldStart) {
      quoted = true;
      atFieldStart = false;
    } else if (character === ",") {
      values.push(value);
      value = "";
      atFieldStart = true;
    } else if (character === "\r" || character === "\n") {
      values.push(value);
      if (character === "\r" && text[index + 1] === "\n") index += 1;
      return values;
    } else {
      value += character;
      atFieldStart = false;
    }
  }
  if (quoted) throw new Error("The CSV header contains an unclosed quoted value.");
  values.push(value);
  return values;
}

async function safeProblem(response: Response): Promise<string> {
  try {
    const problem = (await response.json()) as { detail?: string };
    if (problem.detail) return problem.detail;
  } catch {
    // Use the generic message below for non-JSON responses.
  }
  return "The upload could not be completed. Check the file and try again.";
}

export function AdminIngestion() {
  const { csrfToken } = useAuth();
  const [kind, setKind] = useState<UploadKind>("REVIEWS");
  const [file, setFile] = useState<File | null>(null);
  const [headers, setHeaders] = useState<string[]>([]);
  const [mappings, setMappings] = useState<string[]>([]);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [rows, setRows] = useState<PreviewRow[]>([]);
  const [processingMode, setProcessingMode] = useState<ProcessingMode | "">("");
  const [confirmationKey, setConfirmationKey] = useState("");
  const [confirmedJob, setConfirmedJob] = useState<IngestionJob | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [page, setPage] = useState(1);

  const required = TARGETS[kind].required;
  const choices = [...required, ...TARGETS[kind].optional, "IGNORE"];
  const mappingValid = useMemo(() => {
    const assigned = mappings.filter((target) => target && target !== "IGNORE");
    return mappings.length === headers.length && required.every((target) => assigned.filter((value) => value === target).length === 1)
      && new Set(assigned).size === assigned.length && mappings.every(Boolean);
  }, [headers.length, mappings, required]);

  async function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files?.[0] ?? null;
    setFile(selected);
    setPreview(null);
    setRows([]);
    setProcessingMode("");
    setConfirmationKey("");
    setConfirmedJob(null);
    setMappings([]);
    setHeaders([]);
    setError("");
    if (!selected) return;
    try {
      const bytes = await selected.arrayBuffer();
      const decoded = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
      const parsed = parseFirstCsvRecord(decoded);
      if (!parsed.length || parsed.some((header) => !header)) throw new Error("The CSV header must name every source column.");
      setHeaders(parsed);
      setMappings(parsed.map(() => ""));
    } catch (cause) {
      setFile(null);
      setError(cause instanceof Error ? cause.message : "The CSV header could not be read.");
    }
  }

  async function createPreview() {
    if (!file || !csrfToken || !mappingValid) return;
    setLoading(true);
    setError("");
    setPreview(null);
    setProcessingMode("");
    setConfirmationKey("");
    setConfirmedJob(null);
    try {
      const form = new FormData();
      form.append("upload_kind", kind);
      form.append("column_mappings", JSON.stringify(headers.map((source_header, source_column_index) => ({
        source_column_index,
        source_header,
        target_field: mappings[source_column_index],
      }))));
      form.append("file", file, file.name);
      const response = await fetch("/admin/ingestion/previews", {
        method: "POST",
        credentials: "include",
        headers: { "X-CSRF-Token": csrfToken, "Idempotency-Key": crypto.randomUUID() },
        body: form,
      });
      if (!response.ok) throw new Error(await safeProblem(response));
      const result = (await response.json()) as Preview;
      setPreview(result);
      setProcessingMode("");
      setConfirmationKey(crypto.randomUUID());
      setConfirmedJob(null);
      setPage(1);
      await loadRows(result.preview_id, 1);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The upload could not be completed. Try again.");
    } finally {
      setLoading(false);
    }
  }

  async function loadRows(previewId: string, requestedPage: number) {
    const response = await fetch(`/admin/ingestion/previews/${encodeURIComponent(previewId)}/rows?page=${requestedPage}&page_size=50`, {
      credentials: "include",
    });
    if (!response.ok) throw new Error(await safeProblem(response));
    const result = (await response.json()) as { items: PreviewRow[] };
    setRows(result.items);
  }

  async function changePage(nextPage: number) {
    if (!preview) return;
    setError("");
    setLoading(true);
    try {
      await loadRows(preview.preview_id, nextPage);
      setPage(nextPage);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The preview rows could not be loaded.");
    } finally {
      setLoading(false);
    }
  }

  async function confirmImport() {
    if (!preview || !csrfToken || !processingMode || !confirmationKey || preview.state !== "READY" || preview.counts.accepted_rows < 1) return;
    setConfirming(true);
    setError("");
    try {
      const response = await fetch(`/admin/ingestion/previews/${encodeURIComponent(preview.preview_id)}/confirm`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrfToken,
          "Idempotency-Key": confirmationKey,
        },
        body: JSON.stringify({ verified_sha256: preview.verified_sha256, processing_mode: processingMode }),
      });
      if (!response.ok) throw new Error(await safeProblem(response));
      const job = (await response.json()) as IngestionJob;
      setConfirmedJob(job);
      setPreview({ ...preview, state: "CONFIRMED" });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The import could not be confirmed. Try again.");
    } finally {
      setConfirming(false);
    }
  }

  return (
    <Card variant="outlined" sx={{ mt: 3 }}>
      <CardContent>
        <Stack spacing={2}>
          <Typography component="h2" variant="h5">Admin CSV upload and preview</Typography>
          <Typography color="text.secondary">Upload a CSV, map each source column, and review the immutable server preview.</Typography>
          <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap" }}>
            {KINDS.map((item) => (
              <Button key={item.value} component="a" href={`/admin/ingestion/templates/${item.value}`} variant="text" disabled={confirming}>
                Download {item.label} template
              </Button>
            ))}
          </Stack>
          <FormControl fullWidth>
            <InputLabel id="upload-kind-label">CSV type</InputLabel>
            <Select
              labelId="upload-kind-label"
              label="CSV type"
              value={kind}
              disabled={confirming}
              onChange={(event) => {
                setKind(event.target.value as UploadKind);
                setMappings(headers.map(() => ""));
                setPreview(null);
                setProcessingMode("");
                setConfirmationKey("");
                setConfirmedJob(null);
              }}
            >
              {KINDS.map((item) => <MenuItem key={item.value} value={item.value}>{item.label}</MenuItem>)}
            </Select>
          </FormControl>
          <Button component="label" variant="outlined" sx={{ alignSelf: "flex-start" }} disabled={confirming}>
            Choose CSV file
            <input hidden type="file" accept=".csv,text/csv" aria-label="CSV file" disabled={confirming} onChange={chooseFile} />
          </Button>
          {file && <Typography color="text.secondary">Selected file: {file.name}</Typography>}
          {headers.length > 0 && (
            <Box>
              <Typography component="h3" variant="h6" sx={{ mb: 1 }}>Map source columns</Typography>
              <Stack spacing={1.5}>
                {headers.map((header, index) => {
                  const label = `Source column ${index + 1}: ${header}`;
                  const usedByOther = new Set(mappings.filter((_value, mappingIndex) => mappingIndex !== index && _value && _value !== "IGNORE"));
                  return (
                    <Stack key={`${index}-${header}`} direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ alignItems: { sm: "center" } }}>
                      <Typography sx={{ minWidth: 220, overflowWrap: "anywhere" }}>{label}</Typography>
                      <FormControl fullWidth size="small">
                        <InputLabel id={`mapping-label-${index}`}>Canonical field for source column {index + 1}</InputLabel>
                        <Select
                          labelId={`mapping-label-${index}`}
                          label={`Canonical field for source column ${index + 1}`}
                          value={mappings[index] ?? ""}
                          disabled={confirming}
                          onChange={(event) => {
                            const next = [...mappings];
                            next[index] = event.target.value;
                            setMappings(next);
                            setPreview(null);
                            setProcessingMode("");
                            setConfirmationKey("");
                            setConfirmedJob(null);
                          }}
                        >
                          <MenuItem value=""><em>Choose a field</em></MenuItem>
                          {choices.map((target) => (
                            <MenuItem key={target} value={target} disabled={target !== "IGNORE" && usedByOther.has(target)}>
                              {target === "IGNORE" ? "IGNORE" : `${target}${required.includes(target) ? " (required)" : " (optional)"}`}
                            </MenuItem>
                          ))}
                        </Select>
                      </FormControl>
                    </Stack>
                  );
                })}
              </Stack>
            </Box>
          )}
          {error && <Alert role="alert" severity="error">{error}</Alert>}
          <Button variant="contained" onClick={createPreview} disabled={!file || !mappingValid || loading || confirming}>
            {loading ? "Creating preview…" : "Create preview"}
          </Button>
          {preview && (
            <Box>
              <Typography component="h3" variant="h6">Preview {preview.preview_id}</Typography>
              <Typography>State: {preview.state}</Typography>
              <Typography>File: {preview.original_filename} ({preview.file_size_bytes} bytes)</Typography>
              <Typography>SHA-256: {preview.verified_sha256}</Typography>
              <Typography>Parser: {preview.parser_contract_version}</Typography>
              <Typography>
                Rows: {preview.counts.total_rows}; accepted {preview.counts.accepted_rows}; rejected {preview.counts.rejected_rows};
                duplicate no-op {preview.counts.duplicate_noop_rows}; conflicts {preview.counts.conflict_rows}
              </Typography>
              <Table size="small" aria-label="Preview row outcomes">
                <TableHead><TableRow><TableCell>Row</TableCell><TableCell>Status</TableCell><TableCell>Source identity</TableCell><TableCell>Reason</TableCell></TableRow></TableHead>
                <TableBody>
                  {rows.map((row) => (
                    <TableRow key={row.row_number}>
                      <TableCell>{row.row_number}</TableCell>
                      <TableCell>{row.row_status}</TableCell>
                      <TableCell>{row.source_record_id ?? "—"}</TableCell>
                      <TableCell>{(row.rejection_detail ?? row.rejection_codes.join(", ")) || "—"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
                <Button onClick={() => void changePage(page - 1)} disabled={page <= 1 || loading || confirming}>Previous</Button>
                <Typography sx={{ alignSelf: "center" }}>Page {page}</Typography>
                <Button onClick={() => void changePage(page + 1)} disabled={rows.length < 50 || loading || confirming}>Next</Button>
              </Stack>
              {preview.upload_kind !== "PRODUCT_REFERENCE" && preview.upload_kind !== "SUPPLIER_REFERENCE" && preview.upload_kind !== "BATCH_REFERENCE" && preview.state === "READY" && preview.counts.accepted_rows > 0 && (
                <Stack spacing={1.5} sx={{ mt: 2, maxWidth: 460 }}>
                  <FormControl fullWidth>
                    <InputLabel id="processing-mode-label">Processing mode</InputLabel>
                    <Select
                      labelId="processing-mode-label"
                      label="Processing mode"
                      value={processingMode}
                      onChange={(event) => setProcessingMode(event.target.value as ProcessingMode | "")}
                      disabled={Boolean(confirmedJob) || confirming}
                    >
                      <MenuItem value=""><em>Choose a processing mode</em></MenuItem>
                      <MenuItem value="HISTORICAL_BATCH">Historical batch</MenuItem>
                      <MenuItem value="INCREMENTAL_RESPONSES">Incremental responses</MenuItem>
                    </Select>
                  </FormControl>
                  <Button variant="contained" onClick={() => void confirmImport()} disabled={!processingMode || Boolean(confirmedJob) || confirming}>
                    {confirming ? "Confirming import…" : "Confirm import"}
                  </Button>
                </Stack>
              )}
              {confirmedJob && (
                <Alert severity="success" sx={{ mt: 2 }}>
                  Import confirmed. Job {confirmedJob.job_id} is {confirmedJob.status.toLowerCase()} with {confirmedJob.counts.persisted_feedback} feedback records persisted.
                </Alert>
              )}
            </Box>
          )}
        </Stack>
      </CardContent>
    </Card>
  );
}
