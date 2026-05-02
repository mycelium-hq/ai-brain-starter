# PR #142: Daily backup runbook

## Procedure

1. Snapshot the working tree with `git stash --include-untracked`.
2. Tar the vault root excluding `.git/`.
3. Encrypt the tar with age and the operator public key.
4. Push the encrypted file to the off-site bucket.
5. Verify the upload by re-listing and matching sha256.

PR URL: https://example.com/repos/ops/runbooks/pull/142
