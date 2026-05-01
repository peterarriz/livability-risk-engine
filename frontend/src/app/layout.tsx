import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import Providers from "./providers";
import { ScrollNavState } from "@/components/scroll-nav-state";
import "./globals.css";

export const metadata: Metadata = {
  title: "Livability Risk Engine",
  description: "Coverage-aware construction disruption scoring from public permit and planned closure records.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const document = (
    <html lang="en">
      <body>
        <ScrollNavState />
        <Providers>
          {children}
        </Providers>
      </body>
    </html>
  );

  if (process.env.NEXT_PUBLIC_CLERK_CONFIGURED !== "true") {
    return document;
  }

  return <ClerkProvider>{document}</ClerkProvider>;
}
