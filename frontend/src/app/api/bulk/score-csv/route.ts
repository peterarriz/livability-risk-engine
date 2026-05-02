import { auth, currentUser } from "@clerk/nextjs/server";
import { type NextRequest, NextResponse } from "next/server";
import { getBulkAccessTier } from "@/lib/bulk-access";

const BACKEND = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

const OUTPUT_FILENAME = "livability_scores.csv";

function jsonError(detail: string, status: number): NextResponse {
  return NextResponse.json(
    { detail },
    {
      status,
      headers: {
        "Cache-Control": "no-store",
      },
    },
  );
}

function getInternalApiKey(): string | null {
  const internalKey = process.env.LRE_INTERNAL_API_KEY?.trim();
  if (internalKey) return internalKey;

  const bulkKey = process.env.LRE_BULK_API_KEY?.trim();
  return bulkKey || null;
}

function isUploadedFile(value: FormDataEntryValue | null): value is File {
  return (
    typeof value === "object" &&
    value !== null &&
    "arrayBuffer" in value &&
    "size" in value &&
    Number(value.size) > 0
  );
}

function formatBackendDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => formatBackendDetail(item)).filter(Boolean).join("; ");
  }
  if (detail && typeof detail === "object") {
    return JSON.stringify(detail);
  }
  return "";
}

async function readBackendError(response: Response): Promise<string> {
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    const data = await response.json().catch(() => null) as { detail?: unknown; message?: unknown } | null;
    return formatBackendDetail(data?.detail ?? data?.message);
  }

  return response.text().catch(() => "");
}

export async function POST(req: NextRequest): Promise<NextResponse> {
  let authState: Awaited<ReturnType<typeof auth>>;
  try {
    authState = await auth();
  } catch {
    return jsonError("Sign in to upload CSV.", 401);
  }

  if (!authState.userId) {
    return jsonError("Sign in to upload CSV.", 401);
  }

  let tier = getBulkAccessTier(authState.sessionClaims);
  if (!tier) {
    const user = await currentUser().catch(() => null);
    tier = getBulkAccessTier(user?.publicMetadata);
  }

  if (!tier) {
    return jsonError(
      "Bulk CSV scoring is available for pilot users. Request pilot access to upload CSV files.",
      403,
    );
  }

  let formData: FormData;
  try {
    formData = await req.formData();
  } catch {
    return jsonError("Upload a valid CSV file using multipart form data.", 400);
  }

  const file = formData.get("file");
  if (!isUploadedFile(file)) {
    return jsonError("Choose a CSV file before starting bulk scoring.", 400);
  }

  const internalApiKey = getInternalApiKey();
  if (!internalApiKey) {
    return jsonError(
      "Bulk CSV scoring is not configured. Set LRE_INTERNAL_API_KEY or LRE_BULK_API_KEY server-side only.",
      500,
    );
  }

  const upstreamFormData = new FormData();
  upstreamFormData.append("file", file, file.name || "addresses.csv");

  let upstream: Response;
  try {
    upstream = await fetch(`${BACKEND}/score/batch/csv`, {
      method: "POST",
      headers: {
        "X-API-Key": internalApiKey,
      },
      body: upstreamFormData,
      cache: "no-store",
    });
  } catch {
    return jsonError("Bulk scoring backend is unreachable. Please try again.", 502);
  }

  if (!upstream.ok) {
    const detail = await readBackendError(upstream);

    if (upstream.status === 401 || upstream.status === 403) {
      return jsonError(
        "Bulk scoring is temporarily unavailable because server access was rejected.",
        502,
      );
    }

    if (upstream.status === 400 || upstream.status === 422) {
      return jsonError(
        detail || "The CSV could not be processed. Make sure it has an address column and no more than 200 rows.",
        upstream.status,
      );
    }

    return jsonError(
      detail ? `Bulk scoring backend error: ${detail}` : "Bulk scoring backend returned an error. Please try again.",
      502,
    );
  }

  const headers = new Headers();
  headers.set("Content-Type", upstream.headers.get("content-type") ?? "text/csv; charset=utf-8");
  headers.set("Content-Disposition", `attachment; filename="${OUTPUT_FILENAME}"`);
  headers.set("Cache-Control", "no-store");

  return new NextResponse(upstream.body, {
    status: 200,
    headers,
  });
}

export const dynamic = "force-dynamic";
