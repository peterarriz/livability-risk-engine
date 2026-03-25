export type AddressSuggestion = {
  canonical_id: string;
  display_address: string;
  city?: string | null;
  state?: string | null;
  zip?: string | null;
  lat?: number | null;
  lon?: number | null;
};

export type SelectedAddress = {
  id: string;
  label: string;
  lat: number | null;
  lon: number | null;
  city: string;
  state: string;
  zip?: string;
};

export type ScoreRequestInput = {
  address: string;
  canonicalId?: string | null;
  lat?: number | null;
  lon?: number | null;
};
