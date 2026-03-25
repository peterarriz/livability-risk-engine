"use client";

/**
 * frontend/src/app/login/page.tsx
 *
 * Auth is now handled by Clerk (SignInButton in the top nav).
 * This route redirects to home where the Clerk modal is available.
 */

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/");
  }, [router]);
  return null;
}
