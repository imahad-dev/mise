import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/** Must match AUTH_COOKIE_NAME in services/api/src/auth.py */
const AUTH_COOKIE_NAME = "mise_auth";

const PUBLIC_PATHS = ["/login", "/health", "/debug/sse"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Allow public paths
  if (PUBLIC_PATHS.some((p) => pathname.startsWith(p))) {
    return NextResponse.next();
  }

  // Allow API rewrites (handled by next.config.ts)
  if (pathname.startsWith("/api/")) {
    return NextResponse.next();
  }

  // Check for auth cookie (set by API on login as owner or staff)
  const authCookie = request.cookies.get(AUTH_COOKIE_NAME);

  if (!authCookie) {
    const loginUrl = new URL("/login", request.url);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    /*
     * Match all paths except:
     * - _next/static (static files)
     * - _next/image (image optimization)
     * - favicon.ico, sitemap.xml, robots.txt (metadata files)
     */
    "/((?!_next/static|_next/image|favicon.ico|sitemap.xml|robots.txt).*)",
  ],
};
