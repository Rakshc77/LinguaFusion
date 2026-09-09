param([string]$Configuration = "debug")

# Builds the APK and stages it where the publish script expects it.
#
# This used to drive aapt2, javac and d8 by hand. That could not resolve Maven
# dependencies or compile native code, both of which the offline work needs, so
# the build is now Gradle and this script is a thin wrapper over it. The
# filename is kept because the publish script points people here.
#
# The Gradle wrapper downloads its own Gradle on first run. The Android SDK
# location comes from local.properties, which is per-machine and not in git.

$ErrorActionPreference = "Stop"
$project = (Resolve-Path $PSScriptRoot).Path

if (-not $env:JAVA_HOME) {
    $jbr = "C:\Program Files\Android\Android Studio\jbr"
    if (-not (Test-Path -LiteralPath $jbr)) {
        throw "Set JAVA_HOME to a JDK 17 or newer; Android Studio's JBR was not found either."
    }
    $env:JAVA_HOME = $jbr
}

$local = Join-Path $project "local.properties"
if (-not (Test-Path -LiteralPath $local)) {
    $sdk = Join-Path $env:LOCALAPPDATA "Android\Sdk"
    if (-not (Test-Path -LiteralPath $sdk)) { throw "No Android SDK found; create local.properties with sdk.dir=..." }
    # Forward slashes on purpose: a Java properties file reads \U as an escape.
    "sdk.dir=" + ($sdk -replace '\\', '/') | Set-Content -LiteralPath $local -Encoding utf8
    Write-Host "Wrote $local" -ForegroundColor Yellow
}

if ($Configuration -ne "debug") {
    # Release is deliberately not offered yet: the release build type is still
    # debug-signed, so a "release" APK would only look like one. Production
    # signing is an open decision -- see OFFLINE_PLAN.md.
    throw "Only -Configuration debug is supported until production signing is decided."
}
& (Join-Path $project "gradlew.bat") stageApk --project-dir $project
if ($LASTEXITCODE -ne 0) { throw "Gradle build failed." }

$output = Join-Path $project "dist\LinguaFusionMobile-debug.apk"
Write-Host "Built $output" -ForegroundColor Green
