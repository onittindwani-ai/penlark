import { fileURLToPath } from "node:url";
import type { NextConfig } from "next";

const dev = process.env.NODE_ENV !== "production";

/** What the browser may load. Nothing from another site: every script, style, image, font and request comes from this app. `unsafe-inline` for scripts is needed because the framework
 *  writes its start up data into the page as inline scripts and the page sets the colour theme before it paints; a per request nonce would remove it, at the price of drawing every page
 *  on the server for every visit. `unsafe-eval` and the websocket are for the development server only. */
const csp = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${dev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  `connect-src 'self'${dev ? " ws: wss:" : ""}`,
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

const config: NextConfig = {
  transpilePackages: ["@sendora/ui-kit"],
  reactStrictMode: true,
  poweredByHeader: false,
  // Only Docker builds ask for the standalone folder (NEXT_STANDALONE=1); a normal build works with `next start`.
  output: process.env.NEXT_STANDALONE === "1" ? "standalone" : undefined,
  async headers() {
    // Defence in depth for the browser. The session cookie is already httpOnly and sameSite=lax.
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Content-Security-Policy", value: csp },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  },
  outputFileTracingRoot: fileURLToPath(new URL("../../", import.meta.url)),
};

export default config;
