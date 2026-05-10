# Connector: VoiceDNA / Cartesia / ElevenLabs (TTS chain)

The voice-clone narration stack is opt-in (A5 add-on per the parent strategy doc). When enabled, the connector ships a multi-backend TTS chain with VoiceDNA-encrypted creator-owned voice fingerprints, Cartesia and ElevenLabs as primary render backends, and per-render approval gates. The default is OFF; creators must explicitly enable.

## API surface

- VoiceDNA: https://www.voicedna.io/. Encrypted voice fingerprint storage with creator-owned password. Cannot be decrypted without the creator's password, including by the runtime.
- Cartesia: https://cartesia.ai/. Real-time TTS with voice cloning. API at https://docs.cartesia.ai/. API key auth.
- ElevenLabs: https://elevenlabs.io/. Voice cloning + TTS. API at https://elevenlabs.io/docs/api-reference. API key auth.
- Fish Audio S2: https://fish.audio/. Multilingual TTS, strong on Spanish + Portuguese. API key auth.
- Qwen3-TTS: open-weight, self-hostable. Used as a tertiary fallback for bilingual fidelity.

## Encryption-first architecture

The creator owns their voice. The substrate stores a `.voicedna.enc` encrypted blob whose decryption password lives only in the creator's password manager. Even the runtime cannot decrypt the file without the password being passed in at render time.

This design is deliberate: voice cloning is one of the highest-trust operations a creator can authorize. The substrate refuses to render TTS audio if any of the following are true:

- The creator has not explicitly authorized this render via per-render sign-off
- The script being rendered contains content the creator has flagged as never-render (medical claims, financial advice, brand-deal product mentions without disclosure)
- The destination platform requires disclosure of synthetic audio and the creator has not added disclosure
- The PerTh watermark verification on the previous render of the same fingerprint failed (signal of model drift or compromise)

## Resources mapped to typed-memory categories

| Asset | Substrate category | Sync direction |
|---|---|---|
| Encrypted voice fingerprint blobs (`.voicedna.enc` files) | `voice-fingerprint-audio` per the schema | local-only (never sync to cloud) |
| Per-render audit log (every render with script, fingerprint ID, target platform, approval timestamp, watermark hash) | `voice-fingerprint-audio.audit_log` (append-only) | local hash-chained ledger |
| Generated TTS audio files | `content-piece` enrichment with `production_assets: [<path>]` and `synthetic_audio: true` | manual (creator drops final renders into vault) |

## Operator workflow

1. Creator records 5-15 minutes of clean studio audio in their natural voice.
2. Audio gets fed to VoiceDNA's training pipeline; output is a `.voicedna.enc` blob.
3. Creator stores the encryption password in their password manager. Substrate confirms the password works by doing a test-render of "hello" and discarding it.
4. For each rendered narration: creator approves the script, picks the target backend (Cartesia for English, Fish Audio S2 for Spanish, etc.), submits.
5. Render produces audio + PerTh watermark. Audio file lands at `External Inputs/VoiceDNA/Renders/<YYYY-MM-DD>-<slug>.mp3` with a sidecar `.json` containing the watermark hash + audit-log entry.
6. Creator imports the audio into the destination tool (Captions, VEED, etc.) for the final video edit.

## Hard gates

The substrate refuses to skip these:

- Per-render creator approval is mandatory. The substrate will not auto-render scripts.
- PerTh watermark verification on the prior render must pass before the next render; failure surfaces a hard error and asks the creator to re-train the fingerprint.
- Audit log is append-only; no edits, no deletes. If a render needs to be invalidated, the operator marks the audit-log entry as `revoked: true` with a reason, but the entry stays.
- Fingerprint blob storage is local-only. The substrate refuses to upload `.voicedna.enc` files to any cloud storage.

## Backend routing per language

The pack init step asks the creator which languages they render in and configures the default backend per language:

- English → Cartesia (lowest latency, strong on register variation)
- Spanish → Fish Audio S2 (best Latin-American Spanish accent fidelity)
- Portuguese → Fish Audio S2
- French / German / Italian → ElevenLabs
- Other → Qwen3-TTS self-hosted fallback

The creator can override per-render.

## Privacy + retention

- Voice fingerprint blobs are creator-owned. The substrate has zero access to the underlying voice data without the password.
- Audit log retains per-render entries indefinitely. Forensic-grade integrity is the point.
- Generated TTS audio files are creator-owned. Retention follows the published-piece retention rules.

## Alternatives the pack supports interchangeably

- Resemble AI (commercial, similar to ElevenLabs)
- Coqui TTS (open-source, self-hostable)
- Murf.ai (commercial)
- Play.ht (commercial)

Same architecture: encrypted fingerprint, per-render approval, watermark verification, append-only audit log. Backend choice is interchangeable; the gating logic is the substrate's.

## Disabled by default

Per the parent strategy doc and the conservative design above, this connector ships disabled. Tier-A creators (per the influencer-pack tier system) typically enable it after the first 3 months of pack-in-use, when the trust and approval workflow is established. Tier-B and Tier-C creators usually do not enable it during the first cohort.
