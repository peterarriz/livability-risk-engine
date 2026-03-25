"use client";

/**
 * frontend/src/app/providers.tsx
 *
 * Client-side provider wrapper. Auth is handled by ClerkProvider in layout.tsx.
 * This component is kept as a passthrough so layout.tsx does not need changes.
 */

import type { ReactNode } from "react";

export default function Providers({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
