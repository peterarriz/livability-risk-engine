"use client";

/**
 * frontend/src/app/login/page.tsx
 *
 * Legacy login route.
 * Redirects back to home so deployed users do not land on a dead-end page.
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
