const STREET_SUFFIX: Record<string, string> = {
  st: "street",
  street: "street",
  ave: "avenue",
  av: "avenue",
  avenue: "avenue",
  blvd: "boulevard",
  boulevard: "boulevard",
  dr: "drive",
  drive: "drive",
  rd: "road",
  road: "road",
};

const DIRECTION: Record<string, string> = {
  n: "north",
  s: "south",
  e: "east",
  w: "west",
  ne: "northeast",
  nw: "northwest",
  se: "southeast",
  sw: "southwest",
};

export function normalizeAddressQuery(raw: string): string {
  const base = raw
    .toLowerCase()
    .trim()
    .replace(/[.,]/g, " ")
    .replace(/[^\w\s#-]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!base) return "";
  return base
    .split(" ")
    .map((token) => STREET_SUFFIX[DIRECTION[token] ?? token] ?? (DIRECTION[token] ?? token))
    .join(" ");
}

export function normalizeAddressRecord(displayAddress: string): {
  normalizedFull: string;
  street: string;
  city: string;
  state: string;
} {
  const parts = displayAddress.split(",").map((part) => part.trim()).filter(Boolean);
  const street = parts[0] ?? displayAddress;
  const city = parts[1] ?? "";
  const state = parts[2]?.match(/\b([A-Za-z]{2})\b/)?.[1]?.toUpperCase() ?? "";
  return {
    normalizedFull: normalizeAddressQuery(displayAddress),
    street: normalizeAddressQuery(street),
    city: normalizeAddressQuery(city),
    state,
  };
}

export function formatDisplayAddress(street: string, city: string, state: string, zip?: string | null): string {
  const loc = [city, state].filter(Boolean).join(", ");
  return `${street}${loc ? `, ${loc}` : ""}${zip ? ` ${zip}` : ""}`.trim();
}

export function buildAddressSearchTokens(raw: string): string[] {
  return normalizeAddressQuery(raw).split(" ").filter((token) => token.length >= 2);
}
