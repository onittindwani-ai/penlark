import type { Metadata } from "next";
import type { ReactNode } from "react";
import { themeInitScript } from "@sendora/ui-kit";
import "@sendora/ui-kit/styles.css";
import "./globals.css";
import { Providers } from "@/components/Providers";

export const metadata: Metadata = { title: "Penlark", description: "Write in your own voice. A live voice match meter, house rules, claims that need a source, and a person approving everything." };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" data-accent="plum" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
