# Security

This repo sets up an Obsidian vault plus Claude Code on your own machine. It is a local tool. There is no web app, no server, no shared database, no user accounts. That shapes what "security" means here.

If you are used to web-app security advice (Row-Level Security, CORS, Security Headers), those concepts do not apply to this project. They are about protecting shared services from remote attackers. This project has neither.

What DOES apply: four practical habits that protect your own data and machine.

---

## 1. Keep secrets out of the repo

Some setup steps ask for API keys (Gemini for image generation, OpenAI, etc.). Put them in your shell profile (`~/.zshrc` on Mac, `setx` on Windows) or a secrets manager. Never paste them into a tracked file.

The `.gitignore` in this repo already blocks the most common leak paths:

- `.env`, `.env.local`, `.env.production` (local secrets files)
- `*.key`, `*.pem`, `*.pfx` (private keys)
- `secrets.json`
- `.claude/settings.local.json` (your per-machine Claude Code settings)

If you accidentally commit a secret: rotate the key immediately, then remove it from git history. Deleting the file in a new commit is NOT enough, the old commit still contains it.

---

## 2. Skills and hooks run code on your machine

Claude Code skills and hooks are shell scripts, Python scripts, or instructions that tell Claude to run commands. Before you install a skill or hook from anywhere other than this repo, open the files and read them. You are looking for:

- Shell commands that call external URLs you do not recognize
- Scripts that read files outside the vault
- Hooks that run on every prompt or every file save (these run a lot)

Installing a skill blindly is like running a shell script someone DM'd you. The skills in this repo are reviewed by the maintainer. Third-party skills are not.

---

## 3. MCP servers can read your whole vault

MCP servers are helpers that let Claude talk to external tools (Google Workspace, Linear, Slack, etc.). Once connected, an MCP server typically has read access to whatever context you give it in conversation. Some have read access to your filesystem.

Before connecting an MCP server:

- Check who publishes it (official vendor vs. community fork)
- Check what scopes it requests (read-only is safer than read-write)
- Prefer official MCP servers from the vendor over third-party mirrors

The `docs/POWER_TOOLS.md` file lists MCPs this project recommends. If you add others, apply the same filter.

---

## 4. Claude Code permissions

Claude Code asks before running commands by default. You can allowlist command patterns to skip the prompt. Every allowlist entry is a tradeoff: less friction, but also less chance for you to catch a bad command.

Good defaults:

- Review your `.claude/settings.json` and `.claude/settings.local.json` allowlists occasionally
- Never allowlist `rm -rf` or `git push --force` broadly
- Prefer narrow patterns (`Bash(git status)`) over wildcards (`Bash(*)`)

If Claude asks for permission to do something and you are not sure what it does, say no and ask Claude to explain first.

---

## Reporting a security issue

If you find a security issue in this repo (a leaked secret, a script that does something unexpected, a hook that can be exploited), open a GitHub issue with the label `security` or contact the maintainer directly. Do not include the full exploit details in a public issue if the fix requires coordination.

There is no bounty program. This is a personal project maintained by one person.
