// Which build is live. Open tabs and the installed app compare it with their own and reload after a deploy.
export function GET() {
  return Response.json({ build: process.env.NEXT_PUBLIC_BUILD_ID ?? "dev" }, { headers: { "Cache-Control": "no-store" } });
}
