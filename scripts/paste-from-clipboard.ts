import { spawnSync } from 'node:child_process'
import process from 'node:process'

function usage(code = 0): never {
  console.log(`Send a real paste keystroke to the frontmost application

Usage:
  bun paste-from-clipboard.ts --app "Google Chrome"
`)
  process.exit(code)
}

function sleepSync(ms: number): void {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms)
}

function pasteMac(targetApp?: string): boolean {
  const script = targetApp
    ? `
      tell application "${targetApp}"
        activate
      end tell
      delay 0.3
      tell application "System Events"
        keystroke "v" using command down
      end tell
    `
    : `
      tell application "System Events"
        keystroke "v" using command down
      end tell
    `

  const result = spawnSync('osascript', ['-e', script], { stdio: 'pipe' })
  return result.status === 0
}

async function main(): Promise<void> {
  const args = process.argv.slice(2)
  let appName: string | undefined

  for (let i = 0; i < args.length; i++) {
    const arg = args[i] || ''
    if (arg === '--help' || arg === '-h')
      usage(0)
    if (arg === '--app' && args[i + 1]) {
      appName = args[++i]
      continue
    }
    if (arg.startsWith('-'))
      usage(1)
  }

  if (process.platform !== 'darwin')
    throw new Error('This bundled paste helper currently supports macOS only.')

  for (let attempt = 0; attempt < 3; attempt++) {
    if (pasteMac(appName))
      return
    sleepSync(400)
  }

  throw new Error('Failed to send paste keystroke')
}

await main()
