"use client";

import { useState } from "react";
import { Eye, EyeOff, KeyRound, LockKeyhole } from "lucide-react";
import { api, useApi, type ApiError } from "@/lib/api";
import type { Role } from "@/lib/nav";
import { Button, Field, Input } from "@/components/ui/controls";
import { useShell } from "./shell-context";

/** "dev" shows the development directory; "password" the email + password sign-in. */
export function useAuthMode(): "dev" | "password" | undefined {
  return useApi<{ mode: "dev" | "password" }>("/api/v1/auth/mode").data?.mode;
}

/**
 * Production, before the app is usable: signed out, or still on a temporary password.
 * The shell then hides navigation, search and notifications, leaving only the sign-in screen.
 */
export function useBareShell(): boolean {
  const { session, me, meError } = useShell();
  const mode = useAuthMode();
  if (mode !== "password" || session === null) return false;
  return !session.user || meError?.status === 401 || Boolean(me?.must_change_password);
}

type SignedIn = { employee_no: string; name: string; role: Role; approver: boolean; must_change_password: boolean };

function Frame({ icon: Icon, title, lead, children }: { icon: typeof KeyRound; title: string; lead: string; children: React.ReactNode }) {
  return (
    <div className="mx-auto w-full max-w-[420px] px-4 pb-12 pt-10 sm:px-6 lg:pt-20">
      <span className="flex size-12 items-center justify-center rounded-[12px] border border-line bg-sheet">
        <Icon className="size-6" strokeWidth={1.6} aria-hidden="true" />
      </span>
      <h1 className="mt-5 text-[28px] font-bold leading-tight tracking-[-0.02em]">{title}</h1>
      <p className="mt-1.5 text-[15px] leading-relaxed text-ink-2">{lead}</p>
      <div className="mt-7">{children}</div>
    </div>
  );
}

function PasswordInput({ id, value, onChange, autoComplete, invalid }: { id: string; value: string; onChange: (v: string) => void; autoComplete: string; invalid?: boolean }) {
  const [shown, setShown] = useState(false);
  return (
    <div className="relative">
      <Input id={id} type={shown ? "text" : "password"} value={value} onChange={(e) => onChange(e.target.value)} autoComplete={autoComplete} invalid={invalid} className="pr-12" />
      <button
        type="button"
        onClick={() => setShown((s) => !s)}
        aria-label={shown ? "Hide password" : "Show password"}
        aria-pressed={shown}
        className="absolute right-1 top-1/2 flex size-10 -translate-y-1/2 items-center justify-center rounded-[var(--radius-ctl)] text-ink-3 hover:text-ink"
      >
        {shown ? <EyeOff className="size-[18px]" strokeWidth={1.75} /> : <Eye className="size-[18px]" strokeWidth={1.75} />}
      </button>
    </div>
  );
}

/** Production sign-in: work email and password. */
export function PasswordSignIn() {
  const { signInAs } = useShell();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      const u = await api<SignedIn>("/api/v1/auth/login", { method: "POST", json: { email: email.trim(), password } });
      signInAs(u.employee_no, u.role, u.approver);
    } catch (err) {
      setError((err as ApiError).message);
      setPassword("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Frame icon={KeyRound} title="Sign in" lead="Executive Admin · Bishnoi One. Use your work email and password.">
      <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
        <Field label="Work email" htmlFor="si-email">
          <Input id="si-email" type="email" inputMode="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} invalid={Boolean(error)} />
        </Field>
        <Field label="Password" htmlFor="si-password">
          <PasswordInput id="si-password" value={password} onChange={setPassword} autoComplete="current-password" invalid={Boolean(error)} />
        </Field>
        {error && (
          <p role="alert" className="text-[13.5px] text-danger">
            {error}
          </p>
        )}
        <Button type="submit" variant="primary" busy={busy} disabled={!email.trim() || !password} className="mt-1 w-full">
          Sign in
        </Button>
        <p className="text-[13px] leading-relaxed text-ink-3">Forgot your password or locked out? Ask Executive Admin for a temporary password.</p>
      </form>
    </Frame>
  );
}

/** Change password. `forced`: first sign-in with a temporary password, before anything else is shown. */
export function ChangePasswordForm({ forced, onDone }: { forced?: boolean; onDone: () => void }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<string>();
  const [busy, setBusy] = useState(false);
  const mismatch = again.length > 0 && again !== next;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (mismatch) return;
    setBusy(true);
    setErrors({});
    setMessage(undefined);
    try {
      await api("/api/v1/auth/password", { method: "POST", json: { current_password: current, new_password: next } });
      onDone();
    } catch (err) {
      const x = err as ApiError;
      setErrors(x.fields ?? {});
      setMessage(x.fields ? undefined : x.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
      <Field label={forced ? "Temporary password" : "Current password"} htmlFor="cp-current" error={errors.current_password}>
        <PasswordInput id="cp-current" value={current} onChange={setCurrent} autoComplete="current-password" invalid={Boolean(errors.current_password)} />
      </Field>
      <Field label="New password" htmlFor="cp-new" hint="At least 10 characters. A short phrase is easy to remember." error={errors.new_password}>
        <PasswordInput id="cp-new" value={next} onChange={setNext} autoComplete="new-password" invalid={Boolean(errors.new_password)} />
      </Field>
      <Field label="New password again" htmlFor="cp-again" error={mismatch ? "The two new passwords don't match" : undefined}>
        <PasswordInput id="cp-again" value={again} onChange={setAgain} autoComplete="new-password" invalid={mismatch} />
      </Field>
      {message && (
        <p role="alert" className="text-[13.5px] text-danger">
          {message}
        </p>
      )}
      <Button type="submit" variant="primary" busy={busy} disabled={!current || next.length < 10 || again !== next} className="w-full">
        Save new password
      </Button>
    </form>
  );
}

export function ForcedPasswordChange() {
  const { refreshMe, signOut } = useShell();
  return (
    <Frame icon={LockKeyhole} title="Choose a new password" lead="You signed in with a temporary password. Choose your own before continuing. Other devices are signed out.">
      <ChangePasswordForm forced onDone={refreshMe} />
      <button type="button" onClick={signOut} className="mt-5 text-[13.5px] font-medium text-ink-2 underline-offset-2 hover:underline">
        Sign out
      </button>
    </Frame>
  );
}
