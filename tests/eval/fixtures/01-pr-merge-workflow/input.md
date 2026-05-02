# PR #88: Add idempotent vault writer

## Summary

We need an idempotent writer because re-running ingestion silently created duplicate files.

## Steps

1. Compute sha8 from the source ID before writing.
2. Use sha8 as the file name.
3. Skip the write when the existing file's `hand_edited:true` is set.
4. Otherwise overwrite in place and update `last_verified`.
5. Append a provenance entry every time the writer runs.

## Acceptance

- Re-running on the same source produces the same filename.
- Hand-edited files are not overwritten unless `--force` is set.

PR URL: https://example.com/repos/x/y/pull/88
