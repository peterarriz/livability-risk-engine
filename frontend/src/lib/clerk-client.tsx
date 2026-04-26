"use client";

import type { ComponentProps, ReactNode } from "react";
import {
  SignedIn as ClerkSignedIn,
  SignedOut as ClerkSignedOut,
  SignInButton as ClerkSignInButton,
  UserButton as ClerkUserButton,
  useAuth as useClerkAuth,
  useUser as useClerkUser,
} from "@clerk/nextjs";

const clerkConfigured = process.env.NEXT_PUBLIC_CLERK_CONFIGURED === "true";

export function useUser() {
  if (!clerkConfigured) {
    return {
      isLoaded: true,
      isSignedIn: false,
      user: null,
    };
  }

  return useClerkUser();
}

export function useAuth() {
  if (!clerkConfigured) {
    return {
      isLoaded: true,
      isSignedIn: false,
      userId: null,
      sessionId: null,
      actor: null,
      orgId: null,
      orgRole: null,
      orgSlug: null,
      has: () => false,
      signOut: async () => undefined,
      getToken: async () => null,
    };
  }

  return useClerkAuth();
}

export function SignedIn({ children }: { children: ReactNode }) {
  if (!clerkConfigured) return null;
  return <ClerkSignedIn>{children}</ClerkSignedIn>;
}

export function SignedOut({ children }: { children: ReactNode }) {
  if (!clerkConfigured) return <>{children}</>;
  return <ClerkSignedOut>{children}</ClerkSignedOut>;
}

export function SignInButton(props: ComponentProps<typeof ClerkSignInButton>) {
  if (!clerkConfigured) return <>{props.children}</>;
  return <ClerkSignInButton {...props} />;
}

export function UserButton(props: ComponentProps<typeof ClerkUserButton>) {
  if (!clerkConfigured) return null;
  return <ClerkUserButton {...props} />;
}
