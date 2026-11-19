# Releasing

GitHub (`origin/main`) gets **one commit per release**, named after its version (`v1.1.0`), with the
features listed in the commit body, a matching tag, and an entry in `CHANGELOG.md`. Day-to-day work
stays local.

## Day to day

- Work on the local **`dev`** branch. Every feature or fix is its own commit there.
- `dev` is never pushed.

## Making a release

```bash
git switch dev
scripts/release.sh 1.1.0        # squashes dev into one "v1.1.0" commit on main, tags it, updates CHANGELOG.md
git push origin main v1.1.0     # publish, then press Redeploy in Coolify
```

The script:

1. refuses to run with uncommitted changes, on another branch, or when the version already exists;
2. squashes every commit on `dev` since the last release into one commit on `main` called `v<version>`,
   with one line per feature commit in its body;
3. sets the version in `web/package.json`, `web/package-lock.json` and the API (`api/app/main.py`);
4. adds the release at the top of `CHANGELOG.md`;
5. tags it `v<version>`;
6. keeps the detailed commits locally on `archive/v<version>` and resets `dev` to the release.

## Which number

`major.minor.patch`, starting at **1.0.0**:

- new features → raise the middle number (1.0.0 → 1.1.0);
- only fixes → raise the last number (1.1.0 → 1.1.1);
- a change that breaks how people use it or needs data moved by hand → raise the first number.
