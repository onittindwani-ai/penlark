import Link from "next/link";

export default function NotFound() {
  return (
    <main className="vp-login" id="main">
      <div className="vp-login__card" style={{ display: "grid", gap: 13 }}>
        <h1 className="vp-title">That page does not exist</h1>
        <p className="vp-sub">The address may have a typo, or the page was moved. Go back to the Studio and use the menu.</p>
        <p style={{ margin: 0 }}><Link href="/" className="vp-approval-link">Go to the Studio</Link></p>
      </div>
    </main>
  );
}
