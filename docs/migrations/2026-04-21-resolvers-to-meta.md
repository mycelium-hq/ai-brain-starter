# Migration: RESOLVERs centralized in ⚙️ Meta/Folder Resolvers/

## What changed
Resolver files moved from the folders they describe into a single `⚙️ Meta/Folder Resolvers/` directory. Files are renamed after the folder they describe (with emoji prefix).

Before:
- `👤 CRM/RESOLVER.md`
- `📝 Notes/RESOLVER.md`
- `💡 Originals/RESOLVER.md`

After:
- `⚙️ Meta/Folder Resolvers/👤 CRM.md`
- `⚙️ Meta/Folder Resolvers/📝 Notes.md`
- `⚙️ Meta/Folder Resolvers/💡 Originals.md`

## Why
Having the resolver inline inside each folder had a design virtue (you see it right when you're about to make a mistake) but three real costs:

1. **CRM list pollution.** `👤 CRM/RESOLVER.md` shows up alongside actual people in the Obsidian file browser and in every Dataview query over CRM/.
2. **Duplicate-rename trap.** When imports or scripts try to create a contact named the same as an existing one, Obsidian auto-renames to `Name 2.md`. The RESOLVER being in the same folder didn't prevent this — it just got more company.
3. **Semantic fit.** A resolver is meta — it describes the folder, not a thing that belongs in the folder.

Centralizing under `⚙️ Meta/Folder Resolvers/` keeps the decision tree available without cluttering the folders themselves.

## How to apply (existing vaults)

1. Create the directory: `⚙️ Meta/Folder Resolvers/`
2. Move each existing `RESOLVER.md` into it and rename to match the folder it describes:
   - `👤 CRM/RESOLVER.md` → `⚙️ Meta/Folder Resolvers/👤 CRM.md`
   - `📝 Notes/RESOLVER.md` → `⚙️ Meta/Folder Resolvers/📝 Notes.md`
   - `💡 Originals/RESOLVER.md` → `⚙️ Meta/Folder Resolvers/💡 Originals.md`
3. Update CLAUDE.md rule 3 (or wherever you reference RESOLVERs) to point at the new location. The 2026-04-09 `resolver-md.md` migration doc is superseded by this one.

## Trade-off to know about
You lose the "in-your-face" reminder effect of seeing the resolver when you open the folder. Mitigation: the CLAUDE.md rule pointing at `⚙️ Meta/Folder Resolvers/` is read every session, so Claude still knows to check before creating. If you find yourself (or Claude) creating mis-filed notes despite this, you can symlink each resolver back into its folder or re-centralize per your preference.
