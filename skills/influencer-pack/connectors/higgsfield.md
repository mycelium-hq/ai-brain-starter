# Connector: Higgsfield

Higgsfield is a generative-video tool used for AI b-roll: short clip generation from text or image prompts, used as inserts in Reels, TikToks, and YouTube Shorts. The connector treats Higgsfield as a tooling integration rather than a content source. Output assets land in the creator's local working directory and get linked into `content-piece` records as production assets.

## API surface

- Higgsfield does not currently offer a public API. Output happens through the web UI at https://higgsfield.ai/.
- The connector wraps the workflow rather than the API: it stages prompt sets in `External Inputs/Higgsfield/Prompts/<YYYY-MM-DD>.md`, the creator runs them in the Higgsfield UI, and downloads land in `External Inputs/Higgsfield/Renders/<YYYY-MM-DD>/<slug>.mp4`.

## Resources mapped to typed-memory categories

| Higgsfield asset | Substrate category | Sync direction |
|---|---|---|
| Generated video clips | `content-piece` enrichment with `production_assets: [<path>]` | manual (creator drops files into the Renders folder) |
| Prompt sets that produced renders | `content-source` with `subtype: prompt-set` | manual write by the operator |

## Operator workflow

1. `/content-engine` skill drafts a prompt set for the upcoming week's content (4-7 b-roll clips needed for planned Reels).
2. Drafts land at `External Inputs/Higgsfield/Prompts/<YYYY-MM-DD>.md` with one prompt per line plus the target Reel concept.
3. Creator opens Higgsfield, runs each prompt, downloads the renders.
4. Renders land in `External Inputs/Higgsfield/Renders/<YYYY-MM-DD>/`.
5. The next `/content-engine` run sees the new renders and links them into the relevant `content-piece` draft as production assets.

## Cost handling

Higgsfield charges per render. The substrate does not handle billing; the creator sees their own credit balance in the Higgsfield UI. The pack surfaces a soft prompt during init asking the creator to set a monthly Higgsfield budget so the `/content-engine` skill can warn before drafting prompt sets that would exceed it.

## Privacy + retention

Generated clips are creator-owned. Retention defaults to indefinite. The substrate does not store the source prompts beyond the dated prompts file.

## Alternatives the pack supports interchangeably

- Runway ML
- Sora (OpenAI)
- Veo (Google)
- Luma Dream Machine

Each follows the same pattern: prompt-set staged in vault, render downloaded to vault, `content-piece` enrichment. The init step asks which tool the creator uses and configures the prompts-folder name accordingly.
