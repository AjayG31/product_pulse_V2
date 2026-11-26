import { useEffect, useState, type FormEvent } from "react";
import {
  Alert,
  AppBar,
  Box,
  Button,
  Card,
  CardContent,
  Container,
  CssBaseline,
  Stack,
  TextField,
  ThemeProvider,
  Toolbar,
  Typography,
  createTheme,
} from "@mui/material";
import { BrowserRouter } from "react-router";

import { AuthProvider, useAuth } from "./auth";
import { AdminConflictReview } from "./conflicts";
import { AdminIngestion } from "./ingestion";
import { AdminUserManagement } from "./users";

const theme = createTheme({
  palette: {
    primary: { main: "#17324d" },
    background: { default: "#f4f7fa" },
  },
});

function PageFrame({ children }: { children: React.ReactNode }) {
  return (
    <>
      <AppBar position="static">
        <Toolbar>
          <Typography component="span" variant="h6">
            ProductPulse
          </Typography>
        </Toolbar>
      </AppBar>
      {children}
    </>
  );
}

function LoginPage() {
  const { signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [csrfToken, setCsrfToken] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let current = true;
    fetch("/auth/csrf", { credentials: "include" })
      .then(async (response) => {
        if (!response.ok) throw new Error("bootstrap failed");
        return (await response.json()) as { csrf_token: string };
      })
      .then((result) => {
        if (current) setCsrfToken(result.csrf_token);
      })
      .catch(() => {
        if (current) setError("Sign-in is temporarily unavailable. Try again later.");
      });
    return () => {
      current = false;
    };
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      if (!csrfToken) throw new Error("Sign-in is temporarily unavailable. Try again later.");
      await signIn(email, password, csrfToken);
      setPassword("");
      setCsrfToken(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Sign-in failed. Try again.");
      setPassword("");
    } finally {
      setLoading(false);
    }
  }

  return (
    <PageFrame>
      <Container maxWidth="sm" sx={{ py: 6 }}>
        <Card variant="outlined">
          <CardContent>
            <Typography component="h1" variant="h4" gutterBottom>
              Sign in
            </Typography>
            <Typography color="text.secondary" sx={{ mb: 3 }}>
              Use your ProductPulse account to continue.
            </Typography>
            <Box component="form" onSubmit={submit} noValidate>
              <Stack spacing={2}>
                <TextField
                  autoComplete="username"
                  label="Email"
                  name="email"
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  required
                  fullWidth
                />
                <TextField
                  autoComplete="current-password"
                  label="Password"
                  name="password"
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                  fullWidth
                />
                {error && <Alert role="alert" severity="error">{error}</Alert>}
                <Button type="submit" variant="contained" disabled={loading || !csrfToken}>
                  {loading ? "Signing in…" : "Sign in"}
                </Button>
              </Stack>
            </Box>
          </CardContent>
        </Card>
      </Container>
    </PageFrame>
  );
}

function ForcedPasswordChangePage() {
  const { changePassword } = useAuth();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      await changePassword(currentPassword, newPassword);
      setCurrentPassword("");
      setNewPassword("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Password change failed. Try again.");
      setCurrentPassword("");
      setNewPassword("");
    } finally {
      setLoading(false);
    }
  }

  return (
    <PageFrame>
      <Container maxWidth="sm" sx={{ py: 6 }}>
        <Card variant="outlined">
          <CardContent>
            <Typography component="h1" variant="h4" gutterBottom>
              Change your temporary password
            </Typography>
            <Typography color="text.secondary" sx={{ mb: 3 }}>
              Set a new password before opening the application.
            </Typography>
            <Box component="form" onSubmit={submit} noValidate>
              <Stack spacing={2}>
                <TextField
                  autoComplete="current-password"
                  label="Temporary password"
                  name="current_password"
                  type="password"
                  value={currentPassword}
                  onChange={(event) => setCurrentPassword(event.target.value)}
                  required
                  fullWidth
                />
                <TextField
                  autoComplete="new-password"
                  label="New password"
                  name="new_password"
                  type="password"
                  value={newPassword}
                  onChange={(event) => setNewPassword(event.target.value)}
                  slotProps={{ htmlInput: { minLength: 15, maxLength: 128 } }}
                  helperText="Use 15 to 128 characters. Spaces and Unicode are allowed."
                  required
                  fullWidth
                />
                {error && <Alert role="alert" severity="error">{error}</Alert>}
                <Button type="submit" variant="contained" disabled={loading || !currentPassword || !newPassword}>
                  {loading ? "Updating password…" : "Change password"}
                </Button>
              </Stack>
            </Box>
          </CardContent>
        </Card>
      </Container>
    </PageFrame>
  );
}

function FoundationPage() {
  const { user, signOut } = useAuth();
  const [error, setError] = useState("");
  const [adminPanel, setAdminPanel] = useState<"ingestion" | "conflicts" | "users">("ingestion");

  async function logout() {
    try {
      setError("");
      await signOut();
    } catch {
      setError("Sign out could not be completed. Try again.");
    }
  }

  return (
    <PageFrame>
      <Container maxWidth="md" sx={{ py: 5 }}>
        <Stack direction="row" sx={{ mb: 3, justifyContent: "space-between", alignItems: "center" }}>
          <Typography component="h1" variant="h4">
            Product quality monitoring
          </Typography>
          <Button onClick={logout} variant="outlined">Sign out</Button>
        </Stack>
        {error && <Alert role="alert" severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        <Card variant="outlined">
          <CardContent>
            <Typography variant="h6">Application foundation</Typography>
            <Typography color="text.secondary">
              Signed in as {user?.email}. Product workflows will appear here as their approved milestones are implemented.
            </Typography>
          </CardContent>
        </Card>
        {user?.role === "ADMIN" && (
          <Stack spacing={2}>
            <Stack direction="row" spacing={1}>
              <Button
                variant={adminPanel === "ingestion" ? "contained" : "outlined"}
                aria-pressed={adminPanel === "ingestion"}
                onClick={() => setAdminPanel("ingestion")}
              >
                Ingestion
              </Button>
              <Button
                variant={adminPanel === "conflicts" ? "contained" : "outlined"}
                aria-pressed={adminPanel === "conflicts"}
                onClick={() => setAdminPanel("conflicts")}
              >
                Conflict review
              </Button>
              <Button
                variant={adminPanel === "users" ? "contained" : "outlined"}
                aria-pressed={adminPanel === "users"}
                onClick={() => setAdminPanel("users")}
              >
                Users
              </Button>
            </Stack>
            {adminPanel === "ingestion" ? <AdminIngestion /> : adminPanel === "conflicts" ? <AdminConflictReview /> : <AdminUserManagement />}
          </Stack>
        )}
      </Container>
    </PageFrame>
  );
}

function AuthenticatedContent() {
  const { user, loading } = useAuth();
  if (loading) {
    return <PageFrame><Container maxWidth="md" sx={{ py: 5 }}><Typography role="status">Checking your session…</Typography></Container></PageFrame>;
  }
  if (!user) return <LoginPage />;
  if (user.must_change_password) return <ForcedPasswordChangePage />;
  return <FoundationPage />;
}

export function App() {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <BrowserRouter>
        <AuthProvider>
          <AuthenticatedContent />
        </AuthProvider>
      </BrowserRouter>
    </ThemeProvider>
  );
}
