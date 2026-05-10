# Connector: Calendly / Cal.com

Calendly and Cal.com are booking tools for brand-deal calls, podcast recordings, paid 1-on-1 coaching, and audience meetups. The connector covers both (similar APIs) plus Acuity, SavvyCal, and other booking platforms.

## API surface

- Calendly: https://calendly.com/. API at https://developer.calendly.com/. OAuth 2.0.
- Cal.com: https://cal.com/. Open-source, self-host or cloud. API at https://cal.com/docs/api-reference. API key auth.
- Auth: tool-specific. OAuth or per-account API key.

## Resources mapped to typed-memory categories

| Asset | Substrate category | Sync direction |
|---|---|---|
| Booked meetings (brand-deal calls, podcast recordings, coaching sessions) | `dm-conversation` with `subtype: scheduled-call` linked to the relevant `collab-deal` or `creator-revenue` | bidirectional |
| Pre-meeting questionnaire responses | `dm-conversation` enrichment with `pre_meeting_notes` | inbound only |
| Recording links (when integrated with Riverside, Zoom, etc.) | `content-source` with `subtype: meeting-recording` | inbound only (when recording is enabled) |
| Booking page metrics (conversion, time-to-book, drop-off) | `audience-segment` aggregate | inbound only |

## Operator workflow

1. Creator publishes booking page link (https://cal.com/<creator>/podcast-pitch or equivalent).
2. Audience members or brand contacts book via the public link, fill the questionnaire.
3. Connector polls the booking API every 5 minutes for new bookings.
4. New booking creates a `dm-conversation` record linked to the relevant `collab-deal` if the booker matches an existing brand thread, OR creates a fresh `collab-deal` record at `stage: discovery-call`.
5. Pre-meeting questionnaire responses get attached to the conversation so the creator walks into the call already briefed.
6. Post-meeting: if recording was enabled, the recording URL gets ingested as a `content-source`. If meeting was a podcast guest spot, `/repurposing-engine` queues the recording for clip-extraction once the host publishes it.

## Multi-meeting-type handling

Most creators run several booking-page variants: brand-deal call (15-min discovery), podcast pitch (30-min), paid coaching (60-min), audience meet-and-greet (15-min cohort). The connector treats each meeting type as a distinct entry-point with its own routing logic.

The pack init step asks the creator to enumerate meeting types and configure default routing per type:

- Brand-deal call → routes to `collab-deal.stage = discovery-call`, blocks calendar
- Podcast pitch → routes to `collab-deal.stage = podcast-inbound`, requires manual qualification before blocking calendar
- Paid coaching → routes to `creator-revenue` pre-charge, blocks calendar
- Cohort meet-and-greet → routes to `audience-segment` aggregate, blocks calendar

## Privacy + retention

- Pre-meeting questionnaire responses can contain personal context (the booker shares their company size, intent, etc.). Retention defaults to 2 years to support follow-up cycles.
- Meeting recordings (when enabled) are subject to the recording platform's terms (Riverside, Zoom, etc.). The substrate stores only the recording URL and metadata, not the audio/video.
- Booker email addresses are PII. Retention default is 7 years matching tax recordkeeping.

## Alternatives the pack supports interchangeably

- Acuity Scheduling
- SavvyCal
- TidyCal
- Motion (with built-in scheduling)
- Reclaim

Same workflow: bookings poll, ingest as `dm-conversation`, routing by meeting type, post-meeting cross-reference into `collab-deal` or `creator-revenue`.
