import { readdir, readFile } from 'node:fs/promises'
import { join } from 'node:path'

async function bundleText(directory) {
  const assets = join(directory, 'assets')
  const files = (await readdir(assets)).filter((name) => name.endsWith('.js'))
  return (await Promise.all(files.map((name) => readFile(join(assets, name), 'utf8')))).join('\n')
}

const internet = await bundleText('dist/internet')
const intranet = await bundleText('dist/intranet')
const passengerMarkers = ['PORT HEALTH CONTROL', '旅客风险预警', '/passengers/import']
if (passengerMarkers.some((marker) => internet.includes(marker))) {
  throw new Error('隔离验收失败：互联网构建包含旅客内网模块')
}
if (!passengerMarkers.some((marker) => intranet.includes(marker))) {
  throw new Error('隔离验收失败：内网构建缺少旅客模块')
}
if (intranet.includes('/sources/run')) {
  throw new Error('隔离验收失败：内网构建包含互联网采集控制接口')
}
console.log('platform bundle isolation: passed')
