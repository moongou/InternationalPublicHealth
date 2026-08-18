param(
  [string]$BundleDirectory = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
  [switch]$Start
)

$ErrorActionPreference = "Stop"
$bundle = (Resolve-Path -LiteralPath $BundleDirectory).Path
$sums = Join-Path $bundle "SHA256SUMS.txt"
if (-not (Test-Path -LiteralPath $sums)) { throw "缺少 SHA256SUMS.txt" }
foreach ($line in Get-Content -LiteralPath $sums) {
  if ($line -notmatch '^([0-9a-f]{64})  (.+)$') { throw "校验和文件格式错误" }
  $file = Join-Path $bundle $Matches[2]
  if (-not (Test-Path -LiteralPath $file)) { throw "离线包缺少文件：$($Matches[2])" }
  $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $file).Hash.ToLowerInvariant()
  if ($actual -ne $Matches[1]) { throw "离线包文件校验失败：$($Matches[2])" }
}

docker load --input (Join-Path $bundle "images.tar")
$release = Join-Path $bundle "release"
if (-not (Test-Path -LiteralPath (Join-Path $release ".env"))) {
  Copy-Item -LiteralPath (Join-Path $release ".env.example") -Destination (Join-Path $release ".env")
  Write-Warning "已生成 .env，请先替换全部占位密钥再启动"
}
if ($Start) {
  docker compose --project-directory $release --env-file (Join-Path $release ".env") up -d --no-build --pull never
}
Write-Host "镜像加载和完整性校验完成。"
