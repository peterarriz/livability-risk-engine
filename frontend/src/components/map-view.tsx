"use client";

import { useEffect, useRef } from "react";

type MapViewProps = {
  latitude: number;
  longitude: number;
  address: string;
};

export function MapView({ latitude, longitude, address }: MapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  // Keep a reference to the map instance so we can clean it up and reinitialise
  // when the coordinates change without creating duplicate maps.
  const mapRef = useRef<unknown>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    // Destroy the previous map instance if coordinates changed.
    if (mapRef.current) {
      (mapRef.current as { remove(): void }).remove();
      mapRef.current = null;
    }

    // Leaflet requires window access — import dynamically to stay SSR-safe.
    import("leaflet").then((L) => {
      if (!containerRef.current) return;

      // Fix default icon URLs broken by webpack asset hashing.
      const iconBase = "https://unpkg.com/leaflet@1.9.4/dist/images/";
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      delete (L.Icon.Default.prototype as any)._getIconUrl;
      L.Icon.Default.mergeOptions({
        iconUrl: `${iconBase}marker-icon.png`,
        iconRetinaUrl: `${iconBase}marker-icon-2x.png`,
        shadowUrl: `${iconBase}marker-shadow.png`,
      });

      const map = L.map(containerRef.current).setView([latitude, longitude], 15);

      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        maxZoom: 19,
      }).addTo(map);

      L.marker([latitude, longitude]).addTo(map).bindPopup(address).openPopup();

      mapRef.current = map;
    });

    return () => {
      if (mapRef.current) {
        (mapRef.current as { remove(): void }).remove();
        mapRef.current = null;
      }
    };
  }, [latitude, longitude, address]);

  return (
    <>
      {/* Leaflet CSS loaded inline to avoid adding a global import */}
      <link
        rel="stylesheet"
        href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
        crossOrigin=""
      />
      <div
        ref={containerRef}
        style={{ height: "280px", width: "100%", borderRadius: "var(--radius, 6px)" }}
        aria-label={`Map showing location of ${address}`}
      />
    </>
  );
}
