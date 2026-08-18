param(
  [string]$OutputDirectory = "runtime\offline-bundle"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$target = [IO.Path]::GetFullPath((Join-Path $projectRoot $OutputDirectory))
if (-not $target.StartsWith($projectRoot + [IO.Path]::DirectorySeparatorChar)) {
  throw "离线包输出目录必须位于项目目录内"
}
if (Test-Path -LiteralPath $target) {
  throw "输出目录已存在，请改用新的目录：$target"
}

New-Item -ItemType Directory -Path $target | Out-Null
docker compose --project-directory $projectRoot --env-file (Join-Path $projectRoot ".env.example") pull --ignore-buildable
docker compose --project-directory $projectRoot --env-file (Join-Path $projectRoot ".env.example") build
$images = docker compose --project-directory $projectRoot --env-file (Join-Path $projectRoot ".env.example") config --images | Sort-Object -Unique
docker save --output (Join-Path $target "images.tar") $images

$release = Join-Path $target "release"
New-Item -ItemType Directory -Path $release | Out-Null
$null = robocopy $projectRoot $release /E /XD .git .venv node_modules dist runtime __pycache__ .pytest_cache /XF .coverage
if ($LASTEXITCODE -ge 8) { throw "复制离线部署文件失败，robocopy=$LASTEXITCODE" }

Get-ChildItem -LiteralPath $target -Recurse -File | Where-Object Name -ne "SHA256SUMS.txt" | ForEach-Object {
  $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()
  $relative = [IO.Path]::GetRelativePath($target, $_.FullName).Replace('\','/')
  "$hash  $relative"
} | Set-Content -Encoding ascii (Join-Path $target "SHA256SUMS.txt")

Write-Host "离线交付包已生成：$target"
Write-Host "将整个目录复制到内网后运行 release\scripts\load_offline_bundle.ps1"
