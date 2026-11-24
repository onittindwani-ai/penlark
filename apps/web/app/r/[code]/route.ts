import { NextResponse } from "next/server";

const API = process.env.API_BASE_URL ?? "http://127.0.0.1:8000";

/** The public tracked link. It asks the API where the code points (the API checks its allow list), and never takes a destination from the request. */
export async function GET(request: Request, ctx: { params: Promise<{ code: string }> }) {
  const { code } = await ctx.params;
  if (!/^[a-z0-9]{3,20}$/.test(code)) return new NextResponse("This link does not exist.", { status: 404 });
  let r: Response;
  try {
    r = await fetch(`${API}/api/public/r/${code}`, { redirect: "manual", cache: "no-store", headers: { "x-forwarded-for": request.headers.get("x-forwarded-for") ?? "", "user-agent": request.headers.get("user-agent") ?? "" } });
  } catch {
    return new NextResponse("The link service is not reachable. Try again in a moment.", { status: 502 });
  }
  const to = r.headers.get("location");
  if (r.status === 302 && to) return NextResponse.redirect(to, { status: 302, headers: { "Cache-Control": "no-store", "Referrer-Policy": "no-referrer" } });
  return new NextResponse(r.status === 410 ? "This link no longer points at an allowed address." : "This link does not exist.", { status: r.status === 410 ? 410 : 404 });
}
export const dynamic = "force-dynamic";
