# Connector: YouTube

YouTube is the primary platform for long-form creator content (podcasts, video essays, keynotes, masterclasses) and a major surface for short-form via Shorts. This connector specs the API surface, the ingest flow that backs the creator-facing skills, and the write-back rules.

## Companion skill

The actual ingestion runs through the bundled `ingest-youtube` skill at `~/.claude/skills/ingest-youtube/`. This file specs the platform contract; the skill specs the runtime. They are sibling artifacts.

## API surface

- Base URL: `https://www.googleapis.com/youtube/v3/`
- Documentation: https://developers.google.com/youtube/v3/docs
- Auth: OAuth 2.0 for write operations (uploads, comment moderation, playlist management); API key for read-only (analytics, channel listing).
- Rate limits: 10,000 quota units per day per project on the default tier. A `videos.list` call costs 1 unit; a `search.list` call costs 100 units.

## Ingest path (used by `ingest-youtube`)

The connector deliberately does not rely on the YouTube Data API for transcript extraction. Subtitles are not exposed via the v3 API. The path is:

1. `yt-dlp --list-subs <url>` enumerates available manual and auto-generated subtitle tracks.
2. Subtitle priority: manual subs first (creator-uploaded, accurate punctuation and speaker labels), then auto-generated (machine-transcribed, lowercase, no punctuation), then Whisper local fallback (creator-controlled).
3. `yt-dlp --write-sub --sub-lang <lang> --skip-download --sub-format vtt -o <tmp> <url>` downloads the chosen subtitle as VTT.
4. The skill strips VTT timing markers, deduplicates repeated lines (auto-generated VTTs are line-doubled), and reflows into clean prose paragraphs preserving sentence boundaries.
5. Metadata via `yt-dlp --print-json --skip-download <url>`: video_id, title, channel, channel_url, upload_date, duration, language, description.
6. Output writes to `External Inputs/YouTube/<channel-slug>/<YYYY-MM-DD>-<video-slug>.md` with frontmatter contract documented in the `ingest-youtube` SKILL.md.

## Resources mapped to typed-memory categories

| YouTube resource | Substrate category | Sync direction |
|---|---|---|
| Video transcript (via `yt-dlp` per above) | `content-piece` (when the video is the creator's own); `content-source` (when the video is external research or reference) | inbound only |
| Video metadata (title, duration, view-count, like-count, comment-count) | `content-piece` (creator's own) with `platform: youtube` | inbound only |
| Channel analytics (via YouTube Analytics API, separate OAuth scope) | `audience-segment` (subscriber demographics, watch-time by topic) | inbound only |
| Comments (via Data API v3 `commentThreads.list`) | `dm-conversation` (when the creator wants comments triaged alongside DMs) or `audience-question` (when comments contain recurring topical questions) | bidirectional (write-back via `comments.insert`) |
| Playlists | `content-collection` (when the creator organizes videos into series) | bidirectional |
| Live stream chat | `dm-conversation` (with `subtype: live-chat`) | inbound only |

## Auth setup

1. Creator visits https://console.cloud.google.com/, creates a project, enables YouTube Data API v3 and YouTube Analytics API.
2. Creator generates an OAuth 2.0 client ID for a desktop application.
3. Substrate stores the client ID and client secret in the operator-scoped secret store, not in any vault file.
4. Creator authorizes once via OAuth authorization code flow; the substrate stores the refresh token under the creator's auth scope and uses it to mint short-lived access tokens for each ingest run.

For the transcript-only path, no API auth is required (`yt-dlp` works against the public-facing site). Auth is only needed for analytics, comment moderation, and write operations.

## Sync cadence

- **Transcript ingest (single video):** triggered manually by the operator with `/ingest-youtube <url>`. Idempotent; re-running on the same URL refreshes the file.
- **Channel mode (recent uploads):** `ingest-youtube` accepts `--days N` to pull all videos uploaded in the last N days. Default 14. Designed to run weekly via a launchd plist or cron.
- **Analytics rollup:** `/weekly-creator-report` skill triggers a YouTube Analytics pull every Monday morning to refresh the `audience-segment` and `content-piece` metric fields.
- **Comment triage:** `/dm-closer` polls `commentThreads.list` every 4 hours for new comments. Configurable per creator.

## Language handling

YouTube videos can have multiple manual subtitle tracks (creator-uploaded translations) plus auto-generated tracks in the source language. The connector defaults to language preference `en,es` (English first, Spanish second). The creator can override per-call with `/ingest-youtube <url> --lang <code-list>`.

When ingesting non-English content, the transcript stays in the original language. Translation happens downstream via `/repurposing-engine` if the creator wants to publish multilingual cuts. Never translate at ingest time.

## Whisper fallback

If a video has no manual or auto-generated subtitles (rare but happens for older uploads, livestream archives, and a few music-heavy channels), the operator can pass `--whisper` to fall back to local transcription. Requires `whisper-cpp` plus a downloaded ggml model. Local transcription has zero per-minute API cost but takes roughly real-time on CPU.

The fallback is opt-in, not automatic, because the runtime cost is real and the operator should be aware. See `ingest-youtube/SKILL.md` for the implementation status.

## Privacy + retention

- Public videos: transcripts and metadata are public information. No special retention rules.
- Unlisted videos: transcripts are still accessible if the creator has the URL but should be tagged `confidentiality: unlisted` in the typed-memory entry. Retention defaults to creator-owned (no purge until explicit request).
- Private videos: do not ingest. The connector refuses URLs that resolve to a private video.
- Live stream chat: contains audience messages from real users. Retention defaults to 90 days unless the creator explicitly extends. Personally identifying information in chat (handles, links to other accounts) follows the same defaults as DM ingest.

## Write-back patterns

The connector writes back to YouTube in three cases:

1. **Comment replies** drafted by `/dm-closer` and approved by the creator. The substrate enforces a sign-off step before any comment posts publicly.
2. **Playlist updates** when `/repurposing-engine` adds a new short to a series playlist.
3. **Video description updates** when the creator wants the description regenerated from the transcript (chapters, timestamps, transcript link). Triggered manually, not automated.

Uploads are explicitly out of scope for this connector. Creators upload through their existing tooling; this pack does not add a new uploader.

## Known platform constraints

- Auto-generated subtitle quality varies by source audio. A bad mic or strong accent produces a worse auto-transcript than a clean studio recording.
- The Data API quota (10,000 units/day default) is shared across all read calls. A creator with 200+ videos hitting the analytics endpoint daily will burn quota fast; consider requesting a quota increase from Google or batching analytics pulls.
- Live stream chat ingestion requires a live API connection during the broadcast. Replaying chat from a past stream is not supported by the Data API.
