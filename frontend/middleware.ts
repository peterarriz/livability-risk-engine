import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
import { NextResponse, type NextRequest } from "next/server";

const isProtectedRoute = createRouteMatcher([
  "/account(.*)",
]);

const isOutOfScopeLaunchRoute = createRouteMatcher([
  "/account(.*)",
  "/bulk(.*)",
  "/compare(.*)",
  "/dashboard(.*)",
  "/login(.*)",
  "/neighborhood(.*)",
  "/pilot-evidence(.*)",
  "/portfolio(.*)",
  "/pricing(.*)",
  "/score(.*)",
  "/sign-in(.*)",
  "/widget(.*)",
]);

function hasConfiguredClerkSecret(value: string | undefined) {
  return typeof value === "string" && /^sk_(test|live)_/.test(value);
}

function launchScopeRedirect(req: NextRequest) {
  if (!isOutOfScopeLaunchRoute(req)) {
    return null;
  }

  const url = req.nextUrl.clone();
  url.pathname = "/app";
  url.search = "";
  return NextResponse.redirect(url);
}

function missingClerkMiddleware(req: NextRequest) {
  const redirect = launchScopeRedirect(req);
  if (redirect) return redirect;

  if (!isProtectedRoute(req)) {
    return NextResponse.next();
  }

  return new NextResponse("Authentication is not configured for this environment.", {
    status: 503,
    headers: {
      "Cache-Control": "no-store",
      "Content-Type": "text/plain; charset=utf-8",
    },
  });
}

export default hasConfiguredClerkSecret(process.env.CLERK_SECRET_KEY)
  ? clerkMiddleware(async (auth, req) => {
      const redirect = launchScopeRedirect(req);
      if (redirect) return redirect;

      if (isProtectedRoute(req)) {
        await auth.protect();
      }
    })
  : missingClerkMiddleware;

export const config = {
  matcher: [
    // Skip Next.js internals and static files.
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    // Always run for API routes.
    "/(api|trpc)(.*)",
  ],
};
