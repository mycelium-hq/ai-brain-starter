/**
 * whatsapp-vault-sync
 * Exports your personal WhatsApp chat history to markdown files in your Obsidian vault.
 * Uses Baileys to connect via QR code (same as WhatsApp Web).
 *
 * What gets exported:
 *   - Personal conversations (one file per contact)
 *   - Full message history (as far back as WhatsApp retains)
 *   - Text, images/video captions, voice notes, documents (no media downloaded)
 *   - Groups skipped on first pass
 *
 * Files land at: <vault>/🤖 AI Chats/WhatsApp/<Contact Name>.md
 *
 * Setup:
 *   cd scripts/whatsapp
 *   npm install
 *   VAULT_ROOT=/path/to/your/vault node sync.mjs
 *
 * Re-run any time to pick up new messages.
 */

import makeWASocket, {
  useMultiFileAuthState,
  makeInMemoryStore,
  fetchLatestBaileysVersion,
  DisconnectReason,
  isJidGroup,
} from '@whiskeysockets/baileys'
import qrcodeTerminal from 'qrcode-terminal'
import pino from 'pino'
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

// ── Config ────────────────────────────────────────────────────────────────────

const __dir = path.dirname(fileURLToPath(import.meta.url))

if (!process.env.VAULT_ROOT) {
  console.error('Error: VAULT_ROOT environment variable is required.')
  console.error('Example: VAULT_ROOT="/Users/you/My Vault" node sync.mjs')
  process.exit(1)
}

const VAULT_ROOT   = process.env.VAULT_ROOT
const OUTPUT_DIR   = path.join(VAULT_ROOT, process.env.WA_OUTPUT || '🤖 AI Chats/WhatsApp')
const AUTH_DIR     = path.join(__dir, 'baileys_auth')
const STORE_FILE   = path.join(__dir, 'baileys_store.json')
const SYNC_STAMP   = path.join(__dir, '.last_sync')

const silentLogger = pino({ level: 'silent' })

// ── Helpers ───────────────────────────────────────────────────────────────────

function ensureDirs() {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true })
  fs.mkdirSync(AUTH_DIR,   { recursive: true })
}

function formatTime(unixSeconds) {
  return new Date(unixSeconds * 1000).toLocaleTimeString('en-US', {
    hour: '2-digit', minute: '2-digit', hour12: true,
  })
}

function formatDate(unixSeconds) {
  return new Date(unixSeconds * 1000).toISOString().split('T')[0]
}

function sanitizeFilename(name) {
  return name.replace(/[/\\?%*:|"<>[\]]/g, '-').trim()
}

function getContactName(jid, contacts) {
  const c = contacts[jid] || contacts[jid.replace(/@.+$/, '') + '@c.us']
  return c?.notify || c?.name || ('+' + jid.split('@')[0])
}

function extractText(msgObj) {
  if (!msgObj?.message) return null
  const m = msgObj.message

  if (m.conversation)              return m.conversation
  if (m.extendedTextMessage?.text) return m.extendedTextMessage.text
  if (m.imageMessage)              return m.imageMessage.caption ? `[Image: ${m.imageMessage.caption}]` : '[Image]'
  if (m.videoMessage)              return m.videoMessage.caption ? `[Video: ${m.videoMessage.caption}]` : '[Video]'
  if (m.audioMessage)              return m.audioMessage.ptt ? '[Voice note]' : '[Audio]'
  if (m.documentMessage)           return `[Document: ${m.documentMessage.fileName || 'file'}]`
  if (m.stickerMessage)            return '[Sticker]'
  if (m.contactMessage)            return `[Contact shared: ${m.contactMessage.displayName}]`
  if (m.locationMessage)           return '[Location]'
  if (m.reactionMessage)           return null
  if (m.protocolMessage)           return null
  if (m.pollCreationMessage)       return `[Poll: ${m.pollCreationMessage.name}]`
  if (m.ephemeralMessage)          return extractText({ message: m.ephemeralMessage.message })
  if (m.viewOnceMessage)           return '[View-once media]'
  return null
}

// ── Markdown builder ──────────────────────────────────────────────────────────

function buildMarkdown(contactName, phone, messages) {
  const byDate = {}
  let count = 0

  for (const msg of messages) {
    const ts = Number(msg.messageTimestamp)
    if (!ts) continue
    const text = extractText(msg)
    if (!text) continue

    const date = formatDate(ts)
    if (!byDate[date]) byDate[date] = []
    byDate[date].push(`**${formatTime(ts)}** ${msg.key.fromMe ? 'You' : contactName}: ${text}`)
    count++
  }

  const dates = Object.keys(byDate).sort()
  if (dates.length === 0) return null

  const today = new Date().toISOString().split('T')[0]

  const lines = [
    '---',
    `type: whatsapp-chat`,
    `contact: "${contactName}"`,
    `phone: "+${phone}"`,
    `message_count: ${count}`,
    `first_message: ${dates[0]}`,
    `last_message: ${dates[dates.length - 1]}`,
    `last_sync: ${today}`,
    '---',
    '',
    `# WhatsApp: ${contactName}`,
    '',
  ]

  for (const date of dates) {
    lines.push(`## ${date}`, '', ...byDate[date], '')
  }

  return lines.join('\n')
}

// ── Sync core ─────────────────────────────────────────────────────────────────

async function syncToVault(store) {
  console.log('\nExporting to vault...')

  const chats    = store.chats.all()
  const contacts = store.contacts
  let synced = 0, skipped = 0

  for (const chat of chats) {
    const jid = chat.id
    if (isJidGroup(jid) || jid.includes('@broadcast')) { skipped++; continue }

    const phone       = jid.split('@')[0]
    const contactName = getContactName(jid, contacts)
    const messages    = store.messages[jid]?.array || []
    if (messages.length === 0) continue

    const markdown = buildMarkdown(contactName, phone, messages)
    if (!markdown) continue

    const filePath = path.join(OUTPUT_DIR, sanitizeFilename(contactName) + '.md')
    fs.writeFileSync(filePath, markdown, 'utf8')
    synced++
    if (synced % 20 === 0) process.stdout.write(`  ${synced} contacts...\r`)
  }

  store.writeToFile(STORE_FILE)
  fs.writeFileSync(SYNC_STAMP, new Date().toISOString())

  console.log(`\nDone. ${synced} conversations saved to:`)
  console.log(`  ${OUTPUT_DIR}`)
  console.log(`(${skipped} groups skipped)`)
}

// ── Connection ────────────────────────────────────────────────────────────────

async function connect() {
  ensureDirs()

  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR)
  const { version }          = await fetchLatestBaileysVersion()

  const store = makeInMemoryStore({ logger: silentLogger })
  if (fs.existsSync(STORE_FILE)) {
    store.readFromFile(STORE_FILE)
    console.log('Previous session found. Fetching new messages only...')
  } else {
    console.log('First run. Requesting full history from WhatsApp...')
  }

  const sock = makeWASocket({
    version,
    auth:                state,
    logger:              silentLogger,
    printQRInTerminal:   false,
    syncFullHistory:     true,
    markOnlineOnConnect: false,
    browser:             ['WhatsApp Vault Sync', 'Desktop', '1.0.0'],
  })

  store.bind(sock.ev)
  sock.ev.on('creds.update', saveCreds)

  let historyReceived = false

  sock.ev.on('messaging-history.set', async ({ chats, messages, isLatest }) => {
    console.log(`History chunk: ${chats?.length || 0} chats, ${messages?.length || 0} messages (complete: ${isLatest})`)
    if (isLatest && !historyReceived) {
      historyReceived = true
      await new Promise(r => setTimeout(r, 3000))
      await syncToVault(store)
      process.exit(0)
    }
  })

  sock.ev.on('connection.update', async ({ connection, lastDisconnect, qr }) => {
    if (qr) {
      console.clear()
      console.log('────────────────────────────────────────────────')
      console.log(' WhatsApp Vault Sync')
      console.log('────────────────────────────────────────────────')
      console.log(' Phone: Settings > Linked Devices > Link a Device\n')
      qrcodeTerminal.generate(qr, { small: true })
      console.log('\n(QR refreshes automatically if it expires)')
    }

    if (connection === 'open') {
      console.log('\nConnected. Waiting for history...')
      console.log('(Large histories may take a few minutes)\n')
      // Fallback: if history event never fires (already-synced session), export after 30s
      setTimeout(async () => {
        if (!historyReceived) {
          historyReceived = true
          await syncToVault(store)
          process.exit(0)
        }
      }, 30_000)
    }

    if (connection === 'close') {
      const code = lastDisconnect?.error?.output?.statusCode
      if (code === DisconnectReason.loggedOut) {
        console.log('Logged out. Delete baileys_auth/ and run again.')
        process.exit(1)
      } else {
        setTimeout(connect, 3000)
      }
    }
  })
}

connect().catch(err => { console.error('Fatal:', err.message); process.exit(1) })
