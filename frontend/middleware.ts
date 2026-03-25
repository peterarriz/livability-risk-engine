/**
 * frontend/middleware.ts
 * task: app-024
 *
 * Clerk auth middleware.
 * - Protects /dashboard (and all sub-paths) — redirects to Clerk hosted sign-in if unauthenticated.
 * - Leaves / and /score (and all other routes) publicly accessible.
 */

import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

const isProtectedRoute = createRouteMatcher(["/dashboard(.*)", "/account(.*)"]);


export default clerkMiddleware(async (auth, req) => {
  if (isProtectedRoute(req)) {
    await auth.protect();
  }
});

export const config = {
  matcher: [
    // Skip Next.js internals and static files
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    // Always run for API routes
    "/(api|trpc)(.*)",
  ],
};
