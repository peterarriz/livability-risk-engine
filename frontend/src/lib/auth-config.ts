/**
 * frontend/src/lib/auth-config.ts
 * task: data-045
 *
 * NextAuth v4 configuration shared between the App Router API handler and
 * any server components that call getServerSession(authOptions).
 *
 * Providers:
 *   1. Google OAuth  — handles the OAuth 2.0 dance; syncs to our backend
 *                      via POST /auth/google after each sign-in.
 *   2. Credentials   — email + password; calls POST /auth/login or
 *                      POST /auth/register on our FastAPI backend.
 *
 * Session strategy: JWT (stored in an httpOnly cookie, no DB sessions table).
 * The NextAuth JWT stores our backend_token so API calls can use it directly.
 *
 * Environment variables required:
 *   NEXTAUTH_SECRET          — random string, >32 chars (sign/encrypt session cookie)
 *   NEXTAUTH_URL             — canonical URL of the Next.js app (e.g. https://…vercel.app)
 *   GOOGLE_CLIENT_ID         — from Google Cloud Console OAuth 2.0 credentials
 *   GOOGLE_CLIENT_SECRET     — from Google Cloud Console OAuth 2.0 credentials
 *   NEXT_PUBLIC_API_URL      — FastAPI base URL (e.g. https://…railway.app)
 *   NEXTAUTH_BACKEND_SECRET  — (optional) shared secret for /auth/google server-to-server call
 */

import type { NextAuthOptions } from "next-auth";
import CredentialsProvider from "next-auth/providers/credentials";
import GoogleProvider from "next-auth/providers/google";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const BACKEND_SECRET = process.env.NEXTAUTH_BACKEND_SECRET ?? "";

// ---------------------------------------------------------------------------
// Type augmentation: add backend_token + id to the session user shape
// ---------------------------------------------------------------------------
// (Full declaration lives in src/types/next-auth.d.ts)

export const authOptions: NextAuthOptions = {
  providers: [
    // ------------------------------------------------------------------
    // Google OAuth provider
    // ------------------------------------------------------------------
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID ?? "",
      clientSecret: process.env.GOOGLE_CLIENT_SECRET ?? "",
    }),

    // ------------------------------------------------------------------
    // Email + password credentials provider
    // ------------------------------------------------------------------
    CredentialsProvider({
      id: "credentials",
      name: "Email",
      credentials: {
        email: { label: "Email", type: "email", placeholder: "you@example.com" },
        password: { label: "Password", type: "password" },
        // Pass "register" to create a new account; omit or pass "login" to sign in.
        mode: { label: "Mode", type: "text" },
      },
      async authorize(credentials) {
        if (!credentials?.email || !credentials?.password) return null;

        const isRegister = credentials.mode === "register";
        const endpoint = isRegister ? "/auth/register" : "/auth/login";

        let res: Response;
        try {
          res = await fetch(`${API_BASE}${endpoint}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              email: credentials.email,
              password: credentials.password,
            }),
          });
        } catch {
          throw new Error("Could not reach the backend — please try again");
        }

        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail ?? "Authentication failed");
        }

        const data = await res.json();
        return {
          id: String(data.account_id),
          email: data.email,
          name: data.display_name ?? data.email.split("@")[0],
          // @ts-expect-error — extended field declared in next-auth.d.ts
          backend_token: data.token,
        };
      },
    }),
  ],

  callbacks: {
    // ------------------------------------------------------------------
    // signIn: called after each successful provider auth.
    // For Google, we sync the user to our backend and attach backend_token.
    // ------------------------------------------------------------------
    async signIn({ user, account }) {
      if (account?.provider === "google") {
        try {
          const res = await fetch(`${API_BASE}/auth/google`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              google_id: account.providerAccountId,
              email: user.email,
              display_name: user.name,
              internal_secret: BACKEND_SECRET || undefined,
            }),
          });
          if (!res.ok) return false;
          const data = await res.json();
          // Attach backend_token to user so the jwt callback can pick it up
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          (user as any).backend_token = data.token;
          user.id = String(data.account_id);
        } catch {
          return false;
        }
      }
      return true;
    },

    // ------------------------------------------------------------------
    // jwt: persist backend_token into the NextAuth JWT cookie.
    // ------------------------------------------------------------------
    async jwt({ token, user }) {
      if (user) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        token.backend_token = (user as any).backend_token as string | undefined;
        token.sub = user.id;
      }
      return token;
    },

    // ------------------------------------------------------------------
    // session: expose backend_token and id on the client-accessible session.
    // ------------------------------------------------------------------
    async session({ session, token }) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (session.user as any).backend_token = token.backend_token;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (session.user as any).id = token.sub;
      return session;
    },
  },

  pages: {
    signIn: "/login",
  },

  session: {
    strategy: "jwt",
    maxAge: 30 * 24 * 60 * 60, // 30 days, matches backend JWT expiry
  },

  secret: process.env.NEXTAUTH_SECRET,
};
