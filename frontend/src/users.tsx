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

import { useAuth, type PublicUser } from "./auth";

type UserRole = PublicUser["role"];
type UserStatus = PublicUser["status"];
type ManagedUser = PublicUser & { deactivated_at?: string | null };
type UserPage = {
  items: ManagedUser[];
  page: { page: number; page_size: number; total_items: number; total_pages: number };
};
type Problem = { request_id?: string };

const PAGE_SIZE = 50;

async function safeError(response: Response): Promise<string> {
  let requestId = "";
  try {
    const problem = (await response.json()) as Problem;
    requestId = problem.request_id ? ` (Request ID: ${problem.request_id})` : "";
  } catch {
    // Never render a server response body on credential workflows.
  }
  if (response.status === 401) return "Your session has expired. Sign in again.";
  if (response.status === 403) return "You do not have permission to manage users.";
  if (response.status === 404) return "The account could not be found. Refresh the list and try again.";
  if (response.status === 409) return `The account or request conflicts with the current state.${requestId}`;
  if (response.status === 422) return `Check the email and temporary-password requirements.${requestId}`;
  return `The user request could not be completed.${requestId}`;
}

function roleLabel(role: UserRole): string {
  return role === "ADMIN" ? "Admin" : "Business User";
}

function statusLabel(status: UserStatus): string {
  return status === "ACTIVE" ? "Active" : "Deactivated";
}

export function AdminUserManagement() {
  const { user, csrfToken } = useAuth();
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [pageInfo, setPageInfo] = useState<UserPage["page"]>({
    page: 1,
    page_size: PAGE_SIZE,
    total_items: 0,
    total_pages: 0,
  });
  const [statusFilter, setStatusFilter] = useState<"" | UserStatus>("");
  const [roleFilter, setRoleFilter] = useState<"" | UserRole>("");
  const [pageNumber, setPageNumber] = useState(1);
  const [reloadKey, setReloadKey] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [notice, setNotice] = useState("");
  const hasLoaded = useRef(false);

  const [createOpen, setCreateOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"" | UserRole>("");
  const [initialPassword, setInitialPassword] = useState("");
  const [createError, setCreateError] = useState("");
  const [savingCreate, setSavingCreate] = useState(false);

  const [deactivateTarget, setDeactivateTarget] = useState<ManagedUser | null>(null);
  const [deactivateError, setDeactivateError] = useState("");
  const [savingDeactivate, setSavingDeactivate] = useState(false);

  const [resetTarget, setResetTarget] = useState<ManagedUser | null>(null);
  const [temporaryPassword, setTemporaryPassword] = useState("");
  const [resetError, setResetError] = useState("");
  const [savingReset, setSavingReset] = useState(false);

  useEffect(() => {
    if (user?.role !== "ADMIN") return;
    let active = true;
    const query = new URLSearchParams({ page: String(pageNumber), page_size: String(PAGE_SIZE) });
    if (statusFilter) query.set("status", statusFilter);
    if (roleFilter) query.set("role", roleFilter);
    setLoading(true);
    setLoadError("");
    fetch(`/admin/users?${query.toString()}`, { credentials: "include" })
      .then(async (response) => {
        if (!response.ok) throw new Error(await safeError(response));
        return (await response.json()) as UserPage;
      })
      .then((result) => {
        if (!active) return;
        setUsers(result.items);
        setPageInfo(result.page);
        hasLoaded.current = true;
      })
      .catch((error: unknown) => {
        if (active) setLoadError(error instanceof Error ? error.message : "User accounts could not be loaded.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [user?.role, statusFilter, roleFilter, pageNumber, reloadKey]);

  function openCreate() {
    setEmail("");
    setRole("");
    setInitialPassword("");
    setCreateError("");
    setCreateOpen(true);
  }

  function dismissCreate() {
    if (savingCreate) return;
    setCreateOpen(false);
    setInitialPassword("");
    setEmail("");
    setRole("");
    setCreateError("");
  }

  async function submitCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (user?.role !== "ADMIN" || !csrfToken || !role || !email.trim() || initialPassword.length < 15 || initialPassword.length > 128) return;
    const submittedPassword = initialPassword;
    setInitialPassword("");
    setCreateError("");
    setNotice("");
    setSavingCreate(true);
    try {
      const response = await fetch("/admin/users", {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrfToken,
          "Idempotency-Key": crypto.randomUUID(),
        },
        body: JSON.stringify({ email: email.trim(), role, initial_password: submittedPassword }),
      });
      if (!response.ok) throw new Error(await safeError(response));
      const created = (await response.json()) as ManagedUser;
      setCreateOpen(false);
      setEmail("");
      setRole("");
      setNotice(`Provisioned ${created.email}. Hand the temporary password directly to the verified user in person; they must change it before normal use.`);
      setPageNumber(1);
      setReloadKey((value) => value + 1);
    } catch (error) {
      setCreateError(error instanceof Error ? error.message : "The account could not be provisioned.");
    } finally {
      setSavingCreate(false);
    }
  }

  async function submitDeactivation() {
    if (user?.role !== "ADMIN" || !csrfToken || !deactivateTarget) return;
    setDeactivateError("");
    setNotice("");
    setSavingDeactivate(true);
    try {
      const response = await fetch(`/admin/users/${encodeURIComponent(deactivateTarget.user_id)}`, {
        method: "PATCH",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrfToken,
          "Idempotency-Key": crypto.randomUUID(),
        },
        body: JSON.stringify({}),
      });
      if (!response.ok) throw new Error(await safeError(response));
      const deactivated = (await response.json()) as ManagedUser;
      setNotice(`Deactivated ${deactivated.email}; the API revoked its active sessions.`);
      setDeactivateTarget(null);
      setReloadKey((value) => value + 1);
    } catch (error) {
      setDeactivateError(error instanceof Error ? error.message : "The account could not be deactivated.");
    } finally {
      setSavingDeactivate(false);
    }
  }

  function openReset(target: ManagedUser) {
    setResetTarget(target);
    setTemporaryPassword("");
    setResetError("");
  }

  function dismissReset() {
    if (savingReset) return;
    setTemporaryPassword("");
    setResetTarget(null);
    setResetError("");
  }

  async function submitReset(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (user?.role !== "ADMIN" || !csrfToken || !resetTarget || temporaryPassword.length < 15 || temporaryPassword.length > 128) return;
    const submittedPassword = temporaryPassword;
    setTemporaryPassword("");
    setResetError("");
    setNotice("");
    setSavingReset(true);
    try {
      const response = await fetch(`/admin/users/${encodeURIComponent(resetTarget.user_id)}/password-reset`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrfToken,
          "Idempotency-Key": crypto.randomUUID(),
        },
        body: JSON.stringify({ temporary_password: submittedPassword }),
      });
      if (!response.ok) throw new Error(await safeError(response));
      const reset = (await response.json()) as ManagedUser;
      setResetTarget(null);
      setNotice(`Temporary password reset for ${reset.email}. Hand it directly to the verified user in person; it must be changed before normal use.`);
      setReloadKey((value) => value + 1);
    } catch (error) {
      setResetError(error instanceof Error ? error.message : "The password could not be reset.");
    } finally {
      setSavingReset(false);
    }
  }

  if (user?.role !== "ADMIN") {
    return <Alert severity="error">You do not have permission to manage users.</Alert>;
  }

  const actionsDisabled = loading || Boolean(loadError) || !csrfToken;

  return (
    <Stack spacing={2}>
      <Card variant="outlined">
        <CardContent>
          <Stack spacing={2}>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}>
              <div>
                <Typography component="h2" variant="h5">User management</Typography>
                <Typography color="text.secondary">Provision and manage Admin and Business User accounts.</Typography>
              </div>
              <Stack direction="row" spacing={1}>
                <Button onClick={() => setReloadKey((value) => value + 1)} disabled={loading}>Refresh users</Button>
                <Button variant="contained" onClick={openCreate} disabled={!csrfToken}>Provision user</Button>
              </Stack>
            </Stack>

            {notice && <Alert severity="success">{notice}</Alert>}
            {loadError && <Alert severity="error">{loadError}</Alert>}
            {loadError && hasLoaded.current && <Alert severity="warning">Showing the last successful user list. Management actions are disabled until it refreshes.</Alert>}

            <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
              <FormControl size="small" sx={{ minWidth: 190 }}>
                <InputLabel id="user-status-filter-label">Status</InputLabel>
                <Select
                  labelId="user-status-filter-label"
                  label="Status"
                  value={statusFilter}
                  onChange={(event) => { setStatusFilter(event.target.value as "" | UserStatus); setPageNumber(1); }}
                >
                  <MenuItem value="">All statuses</MenuItem>
                  <MenuItem value="ACTIVE">Active</MenuItem>
                  <MenuItem value="DEACTIVATED">Deactivated</MenuItem>
                </Select>
              </FormControl>
              <FormControl size="small" sx={{ minWidth: 190 }}>
                <InputLabel id="user-role-filter-label">Role</InputLabel>
                <Select
                  labelId="user-role-filter-label"
                  label="Role"
                  value={roleFilter}
                  onChange={(event) => { setRoleFilter(event.target.value as "" | UserRole); setPageNumber(1); }}
                >
                  <MenuItem value="">All roles</MenuItem>
                  <MenuItem value="ADMIN">Admin</MenuItem>
                  <MenuItem value="BUSINESS_USER">Business User</MenuItem>
                </Select>
              </FormControl>
            </Stack>

            {loading && <Typography role="status">Loading user accounts…</Typography>}
            {!loading && !loadError && users.length === 0 && <Typography role="status">No user accounts match these filters.</Typography>}
            {users.length > 0 && (
              <>
                <Table size="small" aria-label="User accounts">
                  <TableHead>
                    <TableRow>
                      <TableCell>Email</TableCell>
                      <TableCell>Role</TableCell>
                      <TableCell>Status</TableCell>
                      <TableCell>Must change password</TableCell>
                      <TableCell>Created (UTC)</TableCell>
                      <TableCell>Actions</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {users.map((managedUser) => (
                      <TableRow key={managedUser.user_id}>
                        <TableCell>{managedUser.email}</TableCell>
                        <TableCell>{roleLabel(managedUser.role)}</TableCell>
                        <TableCell>{statusLabel(managedUser.status)}</TableCell>
                        <TableCell>{managedUser.must_change_password ? "Yes" : "No"}</TableCell>
                        <TableCell>{managedUser.created_at} (UTC)</TableCell>
                        <TableCell>
                          <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                            <Button onClick={() => openReset(managedUser)} disabled={actionsDisabled} aria-label={`Reset password for ${managedUser.email}`}>
                              Reset password
                            </Button>
                            {managedUser.status === "ACTIVE" && (
                              <Button color="error" onClick={() => { setDeactivateTarget(managedUser); setDeactivateError(""); }} disabled={actionsDisabled} aria-label={`Deactivate ${managedUser.email}`}>
                                Deactivate
                              </Button>
                            )}
                          </Stack>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                  <Button onClick={() => setPageNumber((value) => Math.max(1, value - 1))} disabled={loading || pageInfo.page <= 1}>Previous page</Button>
                  <Typography aria-live="polite">Page {pageInfo.page} of {Math.max(1, pageInfo.total_pages)} ({pageInfo.total_items} users)</Typography>
                  <Button onClick={() => setPageNumber((value) => value + 1)} disabled={loading || pageInfo.page >= pageInfo.total_pages}>Next page</Button>
                </Stack>
              </>
            )}
          </Stack>
        </CardContent>
      </Card>

      <Dialog open={createOpen} onClose={dismissCreate}>
        <form onSubmit={submitCreate}>
          <DialogTitle>Provision user</DialogTitle>
          <DialogContent>
            <Stack spacing={2} sx={{ pt: 1, minWidth: { sm: 420 } }}>
              <Typography color="text.secondary">The user must change this temporary password before normal use. Hand it directly to the verified user in person; ProductPulse does not email credentials.</Typography>
              {createError && <Alert severity="error">{createError}</Alert>}
              <TextField label="Email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} required disabled={savingCreate} slotProps={{ htmlInput: { maxLength: 320 } }} />
              <FormControl required disabled={savingCreate}>
                <InputLabel id="new-user-role-label">Role</InputLabel>
                <Select labelId="new-user-role-label" label="Role" value={role} onChange={(event) => setRole(event.target.value as "" | UserRole)}>
                  <MenuItem value="">Select role</MenuItem>
                  <MenuItem value="ADMIN">Admin</MenuItem>
                  <MenuItem value="BUSINESS_USER">Business User</MenuItem>
                </Select>
              </FormControl>
              <TextField
                label="Temporary password"
                type="password"
                value={initialPassword}
                onChange={(event) => setInitialPassword(event.target.value)}
                required
                disabled={savingCreate}
                autoComplete="off"
                helperText="Use 15–128 characters. The server checks the full password policy."
                slotProps={{ htmlInput: { minLength: 15, maxLength: 128 } }}
              />
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={dismissCreate} disabled={savingCreate}>Cancel</Button>
            <Button type="submit" variant="contained" disabled={savingCreate || !csrfToken || !role || initialPassword.length < 15 || initialPassword.length > 128}>
              {savingCreate ? "Provisioning…" : "Provision user"}
            </Button>
          </DialogActions>
        </form>
      </Dialog>

      <Dialog open={deactivateTarget !== null} onClose={() => { if (!savingDeactivate) setDeactivateTarget(null); }}>
        <DialogTitle>Confirm account deactivation</DialogTitle>
        <DialogContent>
          <Stack spacing={2}>
            <Typography>Deactivate {deactivateTarget?.email}? The API will revoke that account’s active sessions. Deactivated accounts cannot be reactivated under the current contract.</Typography>
            {deactivateError && <Alert severity="error">{deactivateError}</Alert>}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeactivateTarget(null)} disabled={savingDeactivate}>Cancel</Button>
          <Button color="error" variant="contained" onClick={submitDeactivation} disabled={savingDeactivate || !csrfToken}>
            {savingDeactivate ? "Deactivating…" : "Confirm deactivation"}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={resetTarget !== null} onClose={dismissReset}>
        <form onSubmit={submitReset}>
          <DialogTitle>Reset temporary password</DialogTitle>
          <DialogContent>
            <Stack spacing={2} sx={{ pt: 1, minWidth: { sm: 420 } }}>
              <Typography color="text.secondary">For {resetTarget?.email}. All active sessions will be revoked, and the user must change the temporary password before normal use. Hand it directly to the verified user in person.</Typography>
              {resetError && <Alert severity="error">{resetError}</Alert>}
              <TextField
                label="Temporary password"
                type="password"
                value={temporaryPassword}
                onChange={(event) => setTemporaryPassword(event.target.value)}
                required
                disabled={savingReset}
                autoComplete="off"
                helperText="Use 15–128 characters. The server checks the full password policy."
                slotProps={{ htmlInput: { minLength: 15, maxLength: 128 } }}
              />
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={dismissReset} disabled={savingReset}>Cancel</Button>
            <Button type="submit" variant="contained" disabled={savingReset || !csrfToken || temporaryPassword.length < 15 || temporaryPassword.length > 128}>
              {savingReset ? "Resetting…" : "Set temporary password"}
            </Button>
          </DialogActions>
        </form>
      </Dialog>
    </Stack>
  );
}
