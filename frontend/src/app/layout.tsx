import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
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
          <ScrollNavState />
          <Providers>
            {children}
          </Providers>
        </body>
      </html>
    </ClerkProvider>
  );
}
