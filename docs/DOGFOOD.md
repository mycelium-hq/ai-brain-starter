# Dogfood

The AI Brain Starter is built to run a real operating company, not to demo on a stage. The proof is that the maintainers run their own company on it, end to end. This document explains the dogfood pattern so anyone installing the system can apply it to their own vertical.

## Why dogfood matters

Most company-brain products optimize for the meeting transcript: a model that listens to a call, summarizes it, drops it in a folder. The transcript is the lowest-fidelity signal a company produces. It is also the easiest to capture, which is why every tool in the category looks the same.

Operating companies do not run on transcripts. They run on decisions that get made under pressure, exceptions taken when the standard runbook does not fit, and playbook gaps that only surface after the event is over. None of that lives cleanly in a transcript. It lives in the operator's head, the close-out notes, the vendor escalation thread, and the founder's voice memo on the drive home.

If the company brain does not capture those signals at the moment they are produced, they evaporate. Two weeks later the same exception happens again, the same vendor escalates again, the same playbook gap bites the next contractor. The company never compounds.

Dogfood means the system writes back to itself after every operational unit, not just after every meeting. Every cycle the company runs through, the system extracts what changed and stores it as typed memory the next cycle can read.

## The vertical pattern

Pick the operational unit that is the heartbeat of the company. For an event-production business that unit is the event. For a sales team it is the deal cycle. For a clinic it is the surgical case or patient encounter. For a school it is the semester. For an agency it is the client engagement. For a software team it is the sprint or the on-call shift.

After the unit closes, the operator on the ground runs a writeback skill. The skill scans the unit's folder, extracts three categories of capture, and writes typed memory files into the vault. The categories are deliberately small because what compounds is consistency, not volume.

## Three categories, one example each

**Decisions.** During the cycle a choice was made under pressure. The operator picked one path over another and the reason for the pick is interesting context that future cycles need.

> Example: during the cycle the team approved a vendor swap because the original vendor was unavailable on short notice. The decision file captures the swap, the rationale, the alternatives that were considered, and a blank outcome field. A scheduled scan surfaces the file 30 days later asking whether the swap held up. The founder fills in the outcome, and the next cycle inherits the verdict.

**Exceptions.** The standard runbook says X. The operator did not-X. Sometimes the deviation is the right call, sometimes it is a sign the runbook is wrong, and either answer is useful only if the deviation gets logged the moment it happens.

> Example: a client requested a custom layout that violates the standard runbook. The exception file logs the deviation, who approved it, the rationale, and a frequency counter that increments each time the same exception is observed across cycles. After three observations the system flags it. The exception is no longer an exception, it is a request the standard runbook should accommodate.

**Playbook deltas.** The post-cycle review surfaces a gap. The contractor instructions did not mention the case that came up. The runbook assumed a vendor type that does not exist anymore. The training video was filmed before the new tool shipped. None of this gets fixed unless the gap is captured the moment it is noticed.

> Example: the operator notices that the contractor instructions for a recurring task do not cover the variant the cycle just produced. The playbook-delta file proposes the edit, links to the existing playbook file, and waits as `status: proposed` for human approval. Nothing edits the live playbook automatically. The operator reviews the proposal, marks it `approved` or `rejected`, and edits the live playbook by hand. The system holds the proposal in memory either way.

## The compounding loop

Each cycle adds typed memory. After a month the vault has dozens of decision files with outcome fields, exception files with frequency counters, and playbook delta files in various review states. The vault begins to know the company's exception patterns better than any single human. The frequency counter on a recurring exception fires before the human notices the pattern. The outcome field on a 60-day-old decision surfaces as a scheduled review item before the founder remembers the decision was made.

The cycle that ran the first month is the same cycle that runs the twelfth month. What changed is the substrate. The model is not asked to remember anything between sessions. It reads the typed memory from the vault, which is deterministic. Every cycle hardens the company's knowledge in a place every future cycle can read.

## Honest scope

The dogfood pattern is the vertical thesis of this system. Generic horizontal company-brain products see the meeting transcript layer because that layer is uniform across companies. They do not see operational reality because operational reality looks different for every vertical. An event production cycle does not look like a surgical case which does not look like a sales deal cycle.

The starter ships with the pattern, the schema for typed memory files, and the conventions for the writeback skill. The skill itself is written per vertical. The maintainers run a non-trivial operating company on top of this, which is why the starter exists in its current shape rather than as a thought experiment. Every primitive in the system has been stress-tested by an operator who needed it to work that day.

Pick your operational unit, name your three categories, write the writeback skill that extracts them, and let the vault compound for ninety days. Then look at the typed memory the system has accumulated and decide whether the compounding is real for your business. If it is, you are running on the company's actual knowledge instead of the demo.
