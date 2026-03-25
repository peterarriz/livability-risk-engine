/**
 * frontend/src/app/api/backend/[...path]/route.ts
 *
 * Vercel-side proxy for all Railway backend calls.
 *
 * The browser calls /api/backend/<path> (same Vercel origin — no CORS).
 * This handler forwards the request server-side to the Railway backend
 * ($NEXT_PUBLIC_API_URL), which also sees no CORS because it's a
 * server-to-server call.
 *
 * All methods (GET, POST, DELETE, OPTIONS, …) are forwarded with headers
 * and body preserved, including Authorization and X-API-Key.
 */

import { type NextRequest, NextResponse } from "next/server";

const BACKEND = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

async function handler(
  req: NextRequest,
  { params }: { params: { path: string[] } },
): Promise<NextResponse> {
  const path = params.path.join("/");
  const search = req.nextUrl.search; // preserves ?query=string
  const target = `${BACKEND}/${path}${search}`;

  // Forward all headers except `host` (which points to Vercel, not Railway).
  const headers = new Headers(req.headers);
  headers.delete("host");

  // Read body into memory — our payloads are small JSON blobs.
  const body =
    req.method !== "GET" && req.method !== "HEAD"
      ? await req.arrayBuffer()
      : undefined;

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: req.method,
      headers,
      body,
      cache: "no-store",
    });
  } catch (err) {
    console.error("[proxy] fetch failed:", target, err);
    return NextResponse.json(
      { detail: "Backend unreachable" },
      { status: 502 },
    );
  }

  // Stream the upstream response back to the browser as-is.
  return new NextResponse(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: upstream.headers,
  });
}

export const GET = handler;
export const POST = handler;
export const DELETE = handler;
export const OPTIONS = handler;
export const PUT = handler;
export const PATCH = handler;

// Never cache this proxy route.
export const dynamic = "force-dynamic";
