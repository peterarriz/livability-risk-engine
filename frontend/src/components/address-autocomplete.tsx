"use client";
import { useEffect, useRef, useState, useCallback } from "react";

type Prediction = { description: string; place_id: string };

type Props = {
  defaultValue?: string;
  placeholder?: string;
  onSelect: (address: string) => void;
  onChange?: (value: string) => void;
  name?: string;
  inputStyle?: React.CSSProperties;
  dropdownStyle?: React.CSSProperties;
  ariaLabel?: string;
};

export default function AddressAutocomplete({
  defaultValue = "",
  placeholder,
  onSelect,
  onChange,
  name,
  inputStyle,
  dropdownStyle,
  ariaLabel,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const serviceRef = useRef<google.maps.places.AutocompleteService | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [value, setValue] = useState(defaultValue);
  const [suggestions, setSuggestions] = useState<Prediction[]>([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const [activeIdx, setActiveIdx] = useState(-1);
  const [ready, setReady] = useState(false);

  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  // Poll for Google Maps API readiness.
  useEffect(() => {
    let attempts = 0;
    function check() {
      if (window.google?.maps?.places?.AutocompleteService) {
        serviceRef.current = new window.google.maps.places.AutocompleteService();
        setReady(true);
      } else if (++attempts < 40) {
        setTimeout(check, 250);
      }
    }
    check();
  }, []);

  const fetchPredictions = useCallback((input: string) => {
    if (!serviceRef.current || input.trim().length < 3) {
      setSuggestions([]);
      return;
    }
    serviceRef.current.getPlacePredictions(
      { input, componentRestrictions: { country: "us" }, types: ["address"] },
      (predictions, status) => {
        if (status === google.maps.places.PlacesServiceStatus.OK && predictions) {
          setSuggestions(
            predictions.slice(0, 5).map((p) => ({
              description: p.description,
              place_id: p.place_id,
            })),
          );
          setShowDropdown(true);
          setActiveIdx(-1);
        } else {
          setSuggestions([]);
        }
      },
    );
  }, []);

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const v = e.target.value;
      setValue(v);
      onChange?.(v);
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => fetchPredictions(v), 200);
    },
    [onChange, fetchPredictions],
  );

  const handleSelect = useCallback((description: string) => {
    setValue(description);
    setSuggestions([]);
    setShowDropdown(false);
    onSelectRef.current(description);
  }, []);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!showDropdown || suggestions.length === 0) return;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIdx((prev) => (prev < suggestions.length - 1 ? prev + 1 : 0));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIdx((prev) => (prev > 0 ? prev - 1 : suggestions.length - 1));
      } else if (e.key === "Enter" && activeIdx >= 0) {
        e.preventDefault();
        handleSelect(suggestions[activeIdx].description);
      } else if (e.key === "Escape") {
        setShowDropdown(false);
      }
    },
    [showDropdown, suggestions, activeIdx, handleSelect],
  );

  // Close dropdown on outside click.
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (inputRef.current && !inputRef.current.parentElement?.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  return (
    <div style={{ position: "relative", flex: 1 }}>
      <input
        ref={inputRef}
        type="text"
        name={name}
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        onFocus={() => { if (suggestions.length > 0) setShowDropdown(true); }}
        placeholder={placeholder ?? "Enter any US address"}
        aria-label={ariaLabel}
        style={inputStyle}
        autoComplete="off"
        role="combobox"
        aria-expanded={showDropdown && suggestions.length > 0}
        aria-autocomplete="list"
      />
      {showDropdown && suggestions.length > 0 && (
        <ul
          role="listbox"
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            right: 0,
            margin: "4px 0 0",
            padding: 0,
            listStyle: "none",
            background: "#FFFFFF",
            border: "1px solid #E5E7EB",
            borderRadius: "8px",
            boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
            zIndex: 10000,
            maxHeight: "240px",
            overflow: "auto",
            ...dropdownStyle,
          }}
        >
          {suggestions.map((s, i) => (
            <li
              key={s.place_id}
              role="option"
              aria-selected={i === activeIdx}
              onMouseDown={() => handleSelect(s.description)}
              onMouseEnter={() => setActiveIdx(i)}
              style={{
                padding: "8px 12px",
                fontSize: "0.875rem",
                color: "#374151",
                cursor: "pointer",
                background: i === activeIdx ? "#F3F4F6" : "transparent",
                borderTop: i > 0 ? "1px solid #F3F4F6" : undefined,
              }}
            >
              {s.description}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
