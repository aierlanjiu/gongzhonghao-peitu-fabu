import { spawnSync } from 'node:child_process'
import fs from 'node:fs'
import { mkdtemp, rm, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import process from 'node:process'

function usage(code = 0): never {
  console.log(`Copy image or HTML to system clipboard

Usage:
  bun copy-to-clipboard.ts image /path/to/image.jpg
  bun copy-to-clipboard.ts html --file /path/to/content.html
`)
  process.exit(code)
}

async function withTempDir<T>(prefix: string, fn: (tempDir: string) => Promise<T>): Promise<T> {
  const tempDir = await mkdtemp(path.join(os.tmpdir(), prefix))
  try {
    return await fn(tempDir)
  } finally {
    await rm(tempDir, { recursive: true, force: true })
  }
}

function getMacSwiftClipboardSource(): string {
  return `import AppKit
import Foundation

func die(_ message: String, _ code: Int32 = 1) -> Never {
  FileHandle.standardError.write(message.data(using: .utf8)!)
  exit(code)
}

if CommandLine.arguments.count < 3 {
  die("Usage: clipboard.swift <image|html> <path>\\n")
}

let mode = CommandLine.arguments[1]
let inputPath = CommandLine.arguments[2]
let pasteboard = NSPasteboard.general
pasteboard.clearContents()

switch mode {
case "image":
  guard let image = NSImage(contentsOfFile: inputPath) else {
    die("Failed to load image: \\(inputPath)\\n")
  }
  if !pasteboard.writeObjects([image]) {
    die("Failed to write image to clipboard\\n")
  }

case "html":
  let url = URL(fileURLWithPath: inputPath)
  let data: Data
  do {
    data = try Data(contentsOf: url)
  } catch {
    die("Failed to read HTML file: \\(inputPath)\\n")
  }

  _ = pasteboard.setData(data, forType: .html)

  let options: [NSAttributedString.DocumentReadingOptionKey: Any] = [
    .documentType: NSAttributedString.DocumentType.html,
    .characterEncoding: String.Encoding.utf8.rawValue
  ]

  if let attr = try? NSAttributedString(data: data, options: options, documentAttributes: nil) {
    pasteboard.setString(attr.string, forType: .string)
    if let rtf = try? attr.data(
      from: NSRange(location: 0, length: attr.length),
      documentAttributes: [.documentType: NSAttributedString.DocumentType.rtf]
    ) {
      _ = pasteboard.setData(rtf, forType: .rtf)
    }
  } else if let html = String(data: data, encoding: .utf8) {
    pasteboard.setString(html, forType: .string)
  }

default:
  die("Unknown mode: \\(mode)\\n")
}
`
}

async function main(): Promise<void> {
  const args = process.argv.slice(2)
  if (args.length < 2)
    usage(1)

  const mode = args[0]
  let filePath = ''

  if (mode === 'image') {
    filePath = args[1] || ''
  } else if (mode === 'html') {
    if (args[1] === '--file' && args[2]) {
      filePath = args[2]
    } else {
      usage(1)
    }
  } else {
    usage(1)
  }

  const resolved = path.isAbsolute(filePath) ? filePath : path.resolve(process.cwd(), filePath)
  if (!fs.existsSync(resolved))
    throw new Error(`File not found: ${resolved}`)

  if (process.platform !== 'darwin')
    throw new Error('This bundled clipboard helper currently supports macOS only.')

  await withTempDir('copy-to-clipboard-', async (tempDir) => {
    const swiftPath = path.join(tempDir, 'clipboard.swift')
    await writeFile(swiftPath, getMacSwiftClipboardSource(), 'utf8')
    const result = spawnSync('swift', [swiftPath, mode, resolved], { stdio: 'inherit' })
    if (result.status !== 0)
      throw new Error(`Clipboard copy failed with exit code ${result.status}`)
  })
}

await main()
