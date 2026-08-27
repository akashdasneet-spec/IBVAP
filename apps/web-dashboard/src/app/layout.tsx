import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "IBVAP Tactical Command & Control (C2)",
  description: "Intelligent Border Video Analytics Platform - Sector Operations Dashboard",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="bg-tactical-dark text-slate-100 min-h-screen flex flex-col antialiased select-none">
        {children}
      </body>
    </html>
  );
}
