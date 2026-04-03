import type { Metadata } from "next";
import Script from "next/script";
import { ClerkProvider } from "@clerk/nextjs";
import { Analytics } from "@vercel/analytics/react";
import { SpeedInsights } from "@vercel/speed-insights/next";
import Providers from "./providers";
import { ScrollNavState } from "@/components/scroll-nav-state";
import "./globals.css";

export const metadata: Metadata = {
  title: "Livability Intelligence",
  description: "Address intelligence for real estate and operations teams — construction, crime, schools, and neighborhood context.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <ClerkProvider>
      <html lang="en">
        <body>
          {process.env.NEXT_PUBLIC_GOOGLE_PLACES_API_KEY && (
            <Script
              src={`https://maps.googleapis.com/maps/api/js?key=${process.env.NEXT_PUBLIC_GOOGLE_PLACES_API_KEY}&libraries=places`}
              strategy="beforeInteractive"
            />
          )}
          <ScrollNavState />
          <Providers>
            {children}
          </Providers>
          <Analytics />
          <SpeedInsights />
        </body>
      </html>
    </ClerkProvider>
  );
}
