import { readdir, readFile } from 'node:fs/promises'
import { extname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('../dist/intranet/', import.meta.url))
const files = []

async function walk(directory) {
  for (const item of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, item.name)
    if (item.isDirectory()) await walk(path)
    else files.push(path)
  }
}

await walk(root)
const violations = []
for (const path of files) {
  if (!['.html', '.js', '.css'].includes(extname(path))) continue
  const source = await readFile(path, 'utf8')
  const extension = extname(path)
  const patterns = extension === '.html' ? [
    /(?:src|href)=["']https?:\/\//gi,
  ] : extension === '.css' ? [
    /url\(\s*["']?https?:\/\//gi,
  ] : [
    /(?:fetch|importScripts|WebSocket)\s*\(\s*["'`]https?:\/\//gi,
    /\.open\s*\(\s*["'][A-Z]+["']\s*,\s*["'`]https?:\/\//gi,
  ]
  for (const pattern of patterns) {
    if (pattern.test(source)) violations.push(`${path}: ${pattern}`)
  }
}
if (violations.length) throw new Error(`内网产物包含外部网络请求：\n${violations.join('\n')}`)
console.log(`offline verification passed (${files.length} bundled files, no external request targets)`)
