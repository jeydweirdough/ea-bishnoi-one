import { redirect } from "next/navigation";

/** proxy.ts sends "/" to the right home for the current role; this is only a fallback. */
export default function Root() {
  redirect("/me");
}
