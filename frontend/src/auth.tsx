import { createContext, useContext, useEffect, useMemo, useState } from "react";

export type PublicUser = {
  user_id: string;
  email: string;
  role: "ADMIN" | "BUSINESS_USER";
  status: "ACTIVE" | "DEACTIVATED";
  must_change_password: boolean;
  created_at: string;
  updated_at: string;
};

type SessionResponse = { user: PublicUser; csrf_token: string };
type AuthValue = {
  user: PublicUser | null;
  csrfToken: string | null;
  loading: boolean;
  signIn: (email: string, password: string, csrf: string) => Promise<void>;
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthValue | null>(null);

async function readProblem(response: Response): Promise<string> {
  try {
    const problem = (await response.json()) as { detail?: string; status?: number };
    if (response.status === 401) return "Email or password is incorrect.";
    if (response.status === 429) return "Sign-in is temporarily unavailable. Try again later.";
    if (response.status === 422) return problem.detail ?? "Check the entered values and try again.";
  } catch {
    // Keep a generic message when the response is not a valid problem document.
  }
  return "The request could not be completed. Try again.";
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<PublicUser | null>(null);
  const [csrfToken, setCsrfToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let current = true;
    fetch("/auth/session", { credentials: "include" })
      .then(async (response) => {
        if (!response.ok) return null;
        return (await response.json()) as SessionResponse;
      })
      .then((session) => {
        if (current && session) {
          setUser(session.user);
          setCsrfToken(session.csrf_token);
        }
      })
      .catch(() => undefined)
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
    };
  }, []);

  const value = useMemo<AuthValue>(
    () => ({
      user,
      csrfToken,
      loading,
      async signIn(email, password, csrf) {
        const response = await fetch("/auth/login", {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
          body: JSON.stringify({ email, password }),
        });
        if (!response.ok) throw new Error(await readProblem(response));
        const session = (await response.json()) as SessionResponse;
        setUser(session.user);
        setCsrfToken(session.csrf_token);
      },
      async changePassword(currentPassword, newPassword) {
        if (!csrfToken) throw new Error("Your session could not be verified. Sign in again.");
        const response = await fetch("/auth/password-change", {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
          body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
        });
        if (!response.ok) throw new Error(await readProblem(response));
        const session = (await response.json()) as SessionResponse;
        setUser(session.user);
        setCsrfToken(session.csrf_token);
      },
      async signOut() {
        if (!csrfToken) {
          setUser(null);
          return;
        }
        const response = await fetch("/auth/logout", {
          method: "POST",
          credentials: "include",
          headers: { "X-CSRF-Token": csrfToken },
        });
        if (response.ok || response.status === 401) {
          setUser(null);
          setCsrfToken(null);
          return;
        }
        throw new Error("Sign out could not be completed. Try again.");
      },
    }),
    [user, csrfToken, loading],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
