# Team Workflows

What a team vault runs that a personal vault cannot. Four workflows that usually repay the install by themselves.

## 1. Meeting-to-decision pipeline

Meetings end. Transcripts land in the vault via Granola, Gemini, Otter, or whichever transcription tool your team already uses. The system picks it up and:

1. Tags the meeting by project and participants.
2. Extracts action items and routes each one to the right owner based on role, not by hand.
3. Extracts decisions and files them in a decision log with who decided, what was decided, what tradeoffs were named, and a blank outcome field to track later.
4. Drafts follow-up messages for the owner to review and send.

What breaks in a personal vault: action items route to "you." On a team they need to route to Maria, Diego, or Ana based on who they actually belong to, and each owner needs to see their items without having to read every meeting note.

## 2. Weekly team ritual

Every Monday, a single command runs the team's weekly review:

1. Pulls all meetings, decisions, and action items from the past week.
2. Surfaces what moved, what stalled, and what got dropped.
3. Lists open loops older than 14 days: things someone promised to do and did not.
4. Produces a one-page summary the team reads before the weekly meeting.

The weekly meeting becomes 30 minutes of decisions instead of 60 minutes of status updates.

## 3. Onboarding with institutional memory

A new hire joins on day 1. Instead of asking every senior person "what did we decide about X" for six weeks, they ask the vault:

- Why did we move off the old CRM?
- What is our policy on discounting enterprise deals?
- Who owns the relationship with that vendor?
- What did the founders decide about Q3 priorities?

Every answer comes back with the decision log entry, the meeting where it was discussed, and the people who were in the room. The new hire is operating at week-6 knowledge on day 1.

What breaks in a personal vault: there is no institutional memory. Everything lives in the founder's head. Onboarding takes weeks because knowledge transfer is synchronous and interrupt-driven.

## 4. Contractor delegation with context

Every contractor task in the team vault carries four fields:

- **What** the task is.
- **Where** the work lives (which docs, which folder, which past examples).
- **Shape** the output should take (format, length, voice, a working sample).
- **Channel** to deliver through (email draft, Slack message, upload to a folder).

Tasks that do not include all four fields are blocked at write time by a hook. The contractor reads the task once and ships. No clarifying questions, no off-shape output, no wasted hours.

What breaks without this: contractors get one-liners ("write the outreach email"), spend two hours guessing what was wanted, and deliver something the founder rewrites from scratch. The discipline around the four fields is small. Maintaining it without tooling is where most teams fail.

## 5. Canonical Facts registry

Every high-stakes doc the team publishes (pitch deck, sales one-pager, investor memo, marketing site) contains numeric claims: market size, growth rates, customer counts, revenue figures, attribution quotes. A single misquoted number across two files is the fastest way to lose an investor or a deal.

The team vault keeps a `Canonical Facts.md` file as the single source of truth for every number, source, and attribution that appears anywhere in external-facing material. Each entry carries:

- The claim ("market size is $X billion")
- The tier-1 source (primary report, not a secondary citation or content-mill summary)
- The year of the data
- The URL and access date

Any file under the raise, sales, or brand folders that cites a number must trace back to Canonical Facts. When a number in Canonical Facts is updated, a grep check flags every downstream file that still carries the stale version. Drift between Canonical Facts and any external asset is a stop-ship defect before anything ships.

What breaks without this: four different market-size numbers end up in five different investor assets, an LP Googles one of them, finds a contradiction, and walks. You had one job: don't contradict yourself on a spec sheet.

## 6. Playbook-to-task wiring (orphan prevention)

When you write a step-by-step playbook for a contractor or team member (an "Instructions for [Name]" doc), the playbook is useless unless it is linked from a live task in the to-do system. A playbook alone is invisible work: the contractor never sees it, the team lead forgets it exists, the work never ships.

Every playbook file must be paired with a task in the team to-do file that:

- Links to the playbook with a wikilink
- Carries an owner, area, priority, and due date
- Is mirrored into the owner's personal view

Session close runs an orphan-playbook scan: any "Instructions for [Name]" file modified this session is grepped against the team to-do file. If no matching task exists, the session cannot close until a task is added or the playbook is marked `status: reference-only` in its frontmatter.

What breaks without this: you spend 45 minutes writing a careful playbook, forget to wire it to a task, and the contractor never sees it. The work that needed to ship before Friday doesn't ship because no one knew it was on the table.

---

If these workflows match what your team is already trying to do and failing at, [working-with-me.md](working-with-me.md) has the packages to install them.
