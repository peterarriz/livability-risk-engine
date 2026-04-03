"use client";
import { useEffect, useRef, useState, useCallback } from "react";

type Props = {
  defaultValue?: string;
  placeholder?: string;
  onSelect: (address: string) => void;
  onChange?: (value: string) => void;
  name?: string;
  style?: React.CSSProperties;
  inputStyle?: React.CSSProperties;
  ariaLabel?: string;
};

export default function AddressAutocomplete({
  defaultValue = "",
  placeholder,
  onSelect,
  onChange,
  name,
  inputStyle,
  ariaLabel,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [value, setValue] = useState(defaultValue);
  const autocompleteRef = useRef<google.maps.places.Autocomplete | null>(null);

  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;

    // Google Maps may load async — poll briefly if not ready yet.
    let attempts = 0;
    const maxAttempts = 20;

    function tryInit() {
      if (autocompleteRef.current) return; // already initialized
      if (!window.google?.maps?.places) {
        attempts++;
        if (attempts < maxAttempts) setTimeout(tryInit, 250);
        return;
      }

      const ac = new window.google.maps.places.Autocomplete(el!, {
        types: ["address"],
        componentRestrictions: { country: "us" },
      });

      ac.addListener("place_changed", () => {
        const place = ac.getPlace();
        if (place.formatted_address) {
          setValue(place.formatted_address);
          onSelectRef.current(place.formatted_address);
        }
      });

      autocompleteRef.current = ac;
    }

    tryInit();

    return () => {
      if (autocompleteRef.current) {
        google.maps.event.clearInstanceListeners(autocompleteRef.current);
        autocompleteRef.current = null;
      }
    };
  }, []);

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setValue(e.target.value);
      onChange?.(e.target.value);
    },
    [onChange],
  );

  return (
    <input
      ref={inputRef}
      type="text"
      name={name}
      value={value}
      onChange={handleChange}
      placeholder={placeholder ?? "Enter any US address"}
      aria-label={ariaLabel}
      style={inputStyle}
      autoComplete="off"
    />
  );
}
