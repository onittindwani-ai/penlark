"use client";
import { Button } from "@sendora/ui-kit";

/** Shown when a page throws while it draws. The retry button asks Next to draw it again. */
export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main className="vp-login" id="main" role="alert">
      <div className="vp-login__card" style={{ display: "grid", gap: 13 }}>
        <h1 className="vp-title">Something went wrong</h1>
        <p className="vp-sub">The page could not be shown. Nothing was approved, exported or sent by this error.{error.digest ? ` Reference: ${error.digest}.` : ""}</p>
        <p style={{ margin: 0 }}><Button variant="primary" onClick={() => reset()}>Try again</Button></p>
      </div>
    </main>
  );
}
