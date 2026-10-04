---
title: "Security runbook"
nav_order: 14
summary: "What the maintainer does on a vulnerability report, a compromised or broken release, and a leaked collector key or database credential, and the repository settings each step relies on."
status: stable
---

# Security runbook

Three situations. Each step names the command where one
exists. The repository settings these steps rely on are listed at the end, with a script that
reads them. Reading a setting is not a drill: a runbook counts as exercised only once a drill
of it is recorded in [drills](drills.md).

`X.Y.Z` is the affected release, `X.Y.W` the last good one before it, and `X.Y.V` the fix.
The five distributions ship in lockstep (`guardana-core`, `guardana-rules`, `guardana-cli`,
`guardana-report`, `guardana-server`), so a step that names "the five" applies to all of them.

## A vulnerability report

A report arrives as a private advisory ([`SECURITY.md`](../../SECURITY.md)) or by email. An
emailed report goes into a draft advisory first, so the whole case lives in one private place.

1. **Answer the reporter within 14 days**, the promise `SECURITY.md` makes, in the advisory's
   comments.
2. **Assess it.** Reproduce it with a minimal fixture built in code, name the affected
   distributions and versions, and decide on a severity. If it is not a vulnerability, say why
   in the advisory and close it.
3. **Fix it on the advisory's temporary private fork** (the advisory page, "Start a temporary
   private fork"). Write the test first, as for any change, and run the gate locally:
   `scripts/ci_local.sh --quiet`. Nothing about the fix goes to a public branch, issue or
   pull request yet.
4. **Release the fix.** Merge the private fork's pull request from the advisory page, then cut
   the patch straight away:

   ```bash
   uv run python scripts/release.py patch --dry-run
   uv run python scripts/release.py patch
   ```

   The publish pauses on the `pypi` environment for its approval, as every release does.
5. **Publish the advisory** once the five are on PyPI: ecosystem `pip`, each affected
   distribution, affected versions `<= X.Y.Z`, patched version `X.Y.V`. Request a CVE from the
   advisory page when the severity warrants it. Credit the reporter if they want credit.
6. **Record it** in `CHANGELOG.md` under the fixed version, in a `### Security` section that
   links the advisory.

```bash
gh api repos/guardana/guardana/security-advisories --jq '.[] | {ghsa_id, state, summary}'
```

## A compromised or broken release

A release that must not be installed: a broken build, a vulnerability shipped in it, or an
artifact nobody here built.

1. **Stop a release still in flight.** While the `publish` job waits for its approval, a cancel
   uploads nothing:

   ```bash
   gh run list --workflow release.yml --limit 3
   gh run view <run-id> --json jobs --jq '.jobs[] | {name, status}'
   gh run cancel <run-id>
   ```

2. **Yank the five on PyPI** (the owner, signed in to PyPI: each project → Manage → Releases →
   `X.Y.Z` → Options → Yank, with the reason). Yank rather than delete: an exact pin still
   resolves, a range no longer picks the release, and PyPI never accepts the same file name
   twice, so a deleted file cannot be replaced anyway.
3. **Delete the image versions on ghcr.** Do it for `guardana` and for `guardana-collector`.
   Deleting a version removes the tags it carried, so note them first and point each moving tag
   (`X.Y`, and any other tag the listing shows besides `X.Y.Z`) back at `X.Y.W`:

   ```bash
   gh auth refresh -s read:packages,delete:packages
   gh api orgs/guardana/packages/container/guardana/versions \
     --jq '.[] | {id, tags: .metadata.container.tags}'
   gh api -X DELETE orgs/guardana/packages/container/guardana/versions/<version-id>
   docker buildx imagetools create --tag ghcr.io/guardana/guardana:X.Y ghcr.io/guardana/guardana:X.Y.W
   ```

4. **Move the `vX.Y` git tag back.** It is the pointer the Marketplace Action pins follow.
   Leave `vX.Y.Z` where it is: once a release is published its tag names the bytes people
   installed.

   ```bash
   git fetch --tags origin
   git tag -f vX.Y "vX.Y.W^{commit}" && git push -f origin vX.Y
   ```

5. **Say so on the GitHub Release** and make the last good one the latest:

   ```bash
   gh release edit vX.Y.Z --prerelease --notes-file yanked.md   # why it was yanked, then the old notes
   gh release edit vX.Y.W --latest
   ```

6. **Publish an advisory** when the release was a security problem (shipped a vulnerability, or
   carries an artifact nobody here built), following steps 5 and 6 of the section above.
7. **Ship the fix** as `X.Y.V` with `scripts/release.py`, and record the yank in
   `CHANGELOG.md` under that version.

When the cause is an artifact nobody here built, also check what let it through before the next
release: the trusted publisher on each PyPI project (repository `guardana/guardana`, workflow
`release.yml`, environment `pypi`), the environment's reviewers, the tag ruleset, recent runs of
the release workflow (`gh run list --workflow release.yml`), and the output of the settings
check below.

## A leaked collector key or database credential

**An API key.** Issue the replacement first, so the pipeline that used the key keeps reporting,
then revoke the leaked one and confirm it is refused. The full rotation is in
[deployment](../deployment.md).

```bash
guardana-collector key list --project acme/web          # find the prefix; shows when it was last used
guardana-collector key create --project acme/web --name ci-rotated
# store the new key as GUARDANA_COLLECTOR_TOKEN where the old one was, then:
guardana-collector key revoke <prefix>
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $OLD_KEY" \
  https://collector.example.com/findings                 # must print 401
guardana-collector run list --project acme/web          # runs nobody here submitted?
guardana-collector audit list --project acme/web
```

**The database credential.** Whoever holds it bypasses the API's tenancy: they can read every
project and write rows, keys included.

1. Change the role's password in PostgreSQL (`ALTER ROLE <role> WITH PASSWORD '<new>';`, as an
   administrative role), and restrict which hosts may connect as it.
2. Update `GUARDANA_DATABASE_URL` wherever the collector reads it and restart every replica;
   `guardana-collector status` confirms the new URL connects.
3. Treat the stored findings as disclosed, and tell the projects' owners.
4. Run `guardana-collector key list` and revoke every key nobody here issued. Keys are stored
   hashed, so the leak did not expose the existing ones, but a write could have added one.

## The settings this relies on

| setting | relied on by |
|---|---|
| private vulnerability reporting | a vulnerability report |
| a tag ruleset restricting who creates, moves or deletes `v*` tags, bypassable by maintainers only ([setup](github-setup.md#3a-protect-release-tags--settings--rules--rulesets)) | both releases above: only a maintainer can publish |
| a required reviewer on the `pypi` environment | every publish pauses for one approval |
| the release workflow's `publish` job needs `ci-passed` | a tag publishes only a commit CI passed |
| the two ghcr packages are public | the documented `docker run`, and the image steps above |

```bash
uv run python scripts/check_repo_settings.py
```

Each setting prints `PRESENT`, `ABSENT` or `NOT CHECKED` (no `gh`, `gh` not logged in, or a `403`
or `404`). It exits `0` when all are present, `1` when any is absent, and `2` when any could not
be read. The ghcr packages need a token with `read:packages`, and the tag ruleset's bypass list
an admin's token. How to put each setting in place:
[GitHub repository setup](github-setup.md); the tag ruleset is
[section 3a](github-setup.md#3a-protect-release-tags--settings--rules--rulesets).
