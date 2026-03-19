import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Livability Risk Engine",
  description: "Chicago disruption intelligence for evaluating near-term construction risk by address.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
