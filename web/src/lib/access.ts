import { findGroup, homeFor, type Role } from "./nav";

export const ROLE_COOKIE = "ea_role";
export const APPROVER_COOKIE = "ea_approver";
/** Development sign-in: employee number. The API derives role and grants from it. */
export const USER_COOKIE = "ea_user";

export const ROLES: { value: Role; label: string; hint: string }[] = [
  { value: "admin", label: "Admin", hint: "All nine groups, authorized companies" },
  { value: "assistant", label: "Assistant", hint: "Assigned and delegated scope" },
  { value: "employee", label: "Employee", hint: "Self-service requests only" },
];

/** Least privilege: anything unrecognised is an Employee. */
export function parseRole(value: string | undefined | null): Role {
  return value === "admin" || value === "assistant" ? value : "employee";
}

/**
 * Route-level permission check. Returns null when allowed, or the path to
 * send the user to instead. Shared by proxy.ts (request time) and pages.
 */
export function redirectFor(pathname: string, role: Role, approver: boolean): string | null {
  const parts = pathname.split("/").filter(Boolean);
  if (parts.length === 0) return homeFor(role);
  const [first, second] = parts;
  if (first === "me" || first === "offline" || first === "r") return null;
  if (first === "inbox") return approver ? null : homeFor(role);
  const group = findGroup(first);
  if (!group) return null; // let not-found handle it
  if (role === "employee") return "/me";
  if (second) {
    const item = group.items.find((i) => i.slug === second);
    if (item?.adminOnly && role !== "admin") return `/${group.slug}`;
  }
  return null;
}
