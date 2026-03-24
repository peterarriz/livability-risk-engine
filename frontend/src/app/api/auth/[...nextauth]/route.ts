/**
 * frontend/src/app/api/auth/[...nextauth]/route.ts
 * task: data-045
 *
 * Next.js App Router handler for NextAuth v4.
 * Delegates all auth logic to authOptions in src/lib/auth-config.ts.
 */

import NextAuth from "next-auth";
import { authOptions } from "@/lib/auth-config";

const handler = NextAuth(authOptions);

export { handler as GET, handler as POST };
