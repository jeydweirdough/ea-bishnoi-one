import { NextResponse, type NextRequest } from "next/server";
import { APPROVER_COOKIE, ROLE_COOKIE, parseRole, redirectFor } from "@/lib/access";

/**
 * Phase 1 permission gate. The role comes from the development role switcher
 * until One Admin login is integrated; the FastAPI service re-checks every
 * data request server-side.
 */
export function proxy(request: NextRequest) {
  const role = parseRole(request.cookies.get(ROLE_COOKIE)?.value);
  const approver = request.cookies.get(APPROVER_COOKIE)?.value === "1";
  const target = redirectFor(request.nextUrl.pathname, role, approver);
  if (target && target !== request.nextUrl.pathname) {
    return NextResponse.redirect(new URL(target, request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/|api/|icons/|fonts/|sw.js|manifest.webmanifest|favicon.ico|robots.txt).*)"],
};
