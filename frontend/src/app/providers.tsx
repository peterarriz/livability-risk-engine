"use client";

/**
 * frontend/src/app/providers.tsx
 * task: data-045
 *
 * Client-side provider wrapper. Placed here so layout.tsx (a Server Component)
 * can import it without becoming a client component itself.
 *
 * Wraps children with NextAuth's SessionProvider so that useSession() and
 * signIn() work throughout the app.
 */

import { SessionProvider } from "next-auth/react";
import type { ReactNode } from "react";

export default function Providers({ children }: { children: ReactNode }) {
  return <SessionProvider>{children}</SessionProvider>;
}
