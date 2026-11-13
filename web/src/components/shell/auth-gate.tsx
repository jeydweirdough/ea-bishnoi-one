"use client";

import { KeyRound, ServerCrash } from "lucide-react";
import { useApi } from "@/lib/api";
import type { Role } from "@/lib/nav";
import { EmptyState } from "@/components/ui/feedback";
import { useShell } from "./shell-context";
import { ForcedPasswordChange, PasswordSignIn, useAuthMode } from "./sign-in";

type DevUser = { employee_no: string; name: string; designation: string | null; role: Role; approver: boolean; company: string };

const GROUP_LABEL: Record<Role, string> = { admin: "Admin", assistant: "Assistant", employee: "Employees & approvers" };

/** Renders the page once someone is signed in; otherwise the development sign-in list. */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const { session, me, meError } = useShell();
  const mode = useAuthMode();
  const needsSignIn = session !== null && (!session.user || meError?.status === 401);
  const users = useApi<DevUser[]>(needsSignIn && mode === "dev" ? "/api/v1/dev/users" : null);

  if (session === null) return null;
  if (needsSignIn && mode === "password") return <PasswordSignIn />;
  if (needsSignIn && mode === undefined) return null;
  if (me?.must_change_password) return <ForcedPasswordChange />;
  if (!needsSignIn) {
    if (meError && meError.status === 0) return <EmptyState icon={ServerCrash} title="You're offline" body={meError.message} />;
    if (meError && !me) return <EmptyState icon={ServerCrash} title="Executive Admin is not reachable" body={mode === "password" ? "The service is restarting or unavailable. Try again in a minute." : "Start the Executive Admin API (port 8000) and reload."} />;
    return <>{children}</>;
  }
  return <SignIn users={users.data} loading={users.loading} failed={Boolean(users.error)} />;
}

function SignIn({ users, loading, failed }: { users?: DevUser[]; loading: boolean; failed: boolean }) {
  const { signInAs } = useShell();
  const groups = (["admin", "assistant", "employee"] as Role[]).map((r) => ({ role: r, people: (users ?? []).filter((u) => u.role === r) }));
  return (
    <div className="mx-auto w-full max-w-[640px] px-4 pb-10 pt-8 sm:px-6 lg:pt-14">
      <div className="flex items-start gap-4">
        <span className="flex size-12 shrink-0 items-center justify-center rounded-[12px] border border-line bg-sheet">
          <KeyRound className="size-6" strokeWidth={1.6} aria-hidden="true" />
        </span>
        <div>
          <h1 className="text-[26px] font-bold leading-tight tracking-[-0.02em]">Sign in</h1>
          <p className="mt-1.5 text-[15px] leading-relaxed text-ink-2">
            Pick a person from the development directory. Role, approval duties and company access come from the server.
            In production this is replaced by One Admin sign-in.
          </p>
        </div>
      </div>
      {failed && (
        <p role="alert" className="mt-6 rounded-[var(--radius-ctl)] border border-danger/30 bg-danger-soft px-4 py-3 text-[14px] text-danger">
          The API is not reachable. Start it with <code className="font-mono text-[13px]">uvicorn app.main:app --port 8000</code> and reload.
        </p>
      )}
      {loading && !users && <p className="mt-8 text-[14px] text-ink-3">Loading people…</p>}
      <div className="mt-8 flex flex-col gap-6">
        {groups.map(
          (g) =>
            g.people.length > 0 && (
              <section key={g.role}>
                <h2 className="mb-2 text-[12.5px] font-medium tracking-wide text-ink-3 uppercase">{GROUP_LABEL[g.role]}</h2>
                <ul className="divide-y divide-line overflow-hidden rounded-[var(--radius-panel)] border border-line bg-sheet">
                  {g.people.map((u) => (
                    <li key={u.employee_no}>
                      <button
                        type="button"
                        onClick={() => signInAs(u.employee_no, u.role, u.approver)}
                        className="flex min-h-14 w-full items-center gap-3 px-4 py-2.5 text-left transition-colors duration-150 hover:bg-canvas"
                      >
                        <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-ink text-[12px] font-bold text-white">
                          {u.name.split(/\s+/).map((p) => p[0]).slice(0, 2).join("").toUpperCase()}
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[14.5px] font-medium">{u.name}</span>
                          <span className="block truncate text-[12.5px] text-ink-3">
                            {u.designation} · {u.company}
                            {u.approver ? " · Approver" : ""}
                          </span>
                        </span>
                        <span className="tabular hidden text-[12px] text-mute sm:block">{u.employee_no}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </section>
            ),
        )}
      </div>
    </div>
  );
}
