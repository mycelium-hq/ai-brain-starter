# Why Teams Are Different

The personal version of ai-brain-starter works beautifully for one person. You install it. Your context file knows you. Your vault grows with you. Your AI remembers what you decided last Tuesday.

Running the same system across a team introduces problems the personal version never had to solve. Here are the four big ones, in the order they usually break things.

## 1. Concurrent editing

Obsidian was built for one user per vault. When two people edit the same note at the same time, the last save wins and the other person's work disappears. You can layer Git, Google Drive, or iCloud on top, but each of those has tradeoffs: merge conflicts, sync lag, permissions gaps, or broken wikilinks.

A real team vault needs a concurrent-editing strategy. That strategy depends on team size, tooling, offline habits, and which people are allowed to touch which folders. There is no one right answer, but the wrong answer loses work.

## 2. Permissions and boundaries

Not every person on the team should see every note. HR, legal, financial, and founder-level strategy notes need scoping. The personal vault has no concept of permissions. Run a shared vault with no boundaries and someone eventually reads something they should not have, and you have a problem.

Options exist: multiple linked vaults, folder-level permissions in Google Drive or Dropbox, read-only subsets, symlinks that selectively include or exclude. Each option has tradeoffs. You need to decide on the model before the team is in the vault, not after.

## 3. Meeting-to-decision routing

In a personal vault, you dump a meeting transcript into a note and move on. Claude can process it later. In a team vault, every meeting has multiple owners, multiple action items routed to different people, and multiple decisions that need to land in the right file, not in the wrong person's inbox or a forgotten Slack thread.

The meeting-to-decision pipeline has to route by role, not by person. That routing logic is not in the personal version. It has to be designed.

## 4. Institutional memory that survives turnover

In a personal vault, everything lives in your head plus your vault. If you leave your own company, the vault leaves with you. In a team vault, the whole point is that the vault survives individual turnover. When your operations lead quits, the institutional memory stays. When a new hire joins, they can ask Claude "what did we decide about X six months ago" and get an answer with context attached.

Making that true requires a different information architecture: roles as first-class, decisions logged with rationale and tradeoffs, meeting artifacts linked to decisions, decisions linked to outcomes. This is a design decision, not just an install.

## What this means practically

You can build a team vault yourself using the personal version as a starting point. The path is real. The cost is time: the four problems above each have several solutions with tradeoffs, and most teams learn which tradeoffs matter only after the first one breaks.

The team version is not different magic. It is the same system with these four decisions pre-made based on how your specific team works.

If that sounds like the right trade, [team-workflows.md](team-workflows.md) covers what the installed version actually runs. If you want it built for you, [working-with-me.md](working-with-me.md) is the menu.
