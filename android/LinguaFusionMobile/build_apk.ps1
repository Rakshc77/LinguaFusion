param([string]$Configuration = "debug")

$ErrorActionPreference = "Stop"
$project = (Resolve-Path $PSScriptRoot).Path
$sdk = "C:\Users\rajar\AppData\Local\Android\Sdk"
$buildTools = Join-Path $sdk "build-tools\36.1.0"
$platform = Join-Path $sdk "platforms\android-36.1\android.jar"
$javaHome = "C:\Program Files\Android\Android Studio\jbr"
$build = Join-Path $project "build"
$dist = Join-Path $project "dist"

if (-not (Test-Path -LiteralPath $platform)) { throw "Android platform 36.1 is not installed." }
$expectedBuild = [IO.Path]::GetFullPath((Join-Path $project "build"))
if ([IO.Path]::GetFullPath($build) -ne $expectedBuild -or (Split-Path $expectedBuild -Parent) -ne $project) { throw "Unsafe build directory." }
if (Test-Path -LiteralPath $build) { Remove-Item -LiteralPath $build -Recurse -Force }
New-Item -ItemType Directory -Force -Path $build,$dist,(Join-Path $build "gen"),(Join-Path $build "classes"),(Join-Path $build "dex") | Out-Null

$aapt2 = Join-Path $buildTools "aapt2.exe"
$compiled = Join-Path $build "resources.zip"
$baseApk = Join-Path $build "base.apk"
& $aapt2 compile --dir (Join-Path $project "res") -o $compiled
& $aapt2 link -o $baseApk -I $platform --manifest (Join-Path $project "AndroidManifest.xml") --java (Join-Path $build "gen") --min-sdk-version 26 --target-sdk-version 36 --version-code 6 --version-name 1.5 $compiled
if ($LASTEXITCODE -ne 0) { throw "Android resource linking failed." }

$sources = @(Get-ChildItem (Join-Path $project "src") -Recurse -Filter *.java | Select-Object -ExpandProperty FullName)
$sources += @(Get-ChildItem (Join-Path $build "gen") -Recurse -Filter *.java | Select-Object -ExpandProperty FullName)
& (Join-Path $javaHome "bin\javac.exe") -encoding UTF-8 -source 17 -target 17 -classpath $platform -d (Join-Path $build "classes") $sources
if ($LASTEXITCODE -ne 0) { throw "Android compilation failed." }

$classFiles = @(Get-ChildItem (Join-Path $build "classes") -Recurse -Filter *.class | Select-Object -ExpandProperty FullName)
$env:JAVA_HOME = $javaHome
& (Join-Path $buildTools "d8.bat") --lib $platform --min-api 26 --output (Join-Path $build "dex") $classFiles
& (Join-Path $javaHome "bin\jar.exe") uf $baseApk -C (Join-Path $build "dex") classes.dex

$aligned = Join-Path $build "aligned.apk"
& (Join-Path $buildTools "zipalign.exe") -f 4 $baseApk $aligned
$keystore = Join-Path $project "debug.keystore"
if (-not (Test-Path -LiteralPath $keystore)) {
    & (Join-Path $javaHome "bin\keytool.exe") -genkeypair -v -keystore $keystore -storepass android -alias androiddebugkey -keypass android -dname "CN=LinguaFusion Debug,O=LinguaFusion,C=DE" -keyalg RSA -keysize 2048 -validity 10000
}
$output = Join-Path $dist "LinguaFusionMobile-debug.apk"
& (Join-Path $buildTools "apksigner.bat") sign --ks $keystore --ks-key-alias androiddebugkey --ks-pass pass:android --key-pass pass:android --out $output $aligned
& (Join-Path $buildTools "apksigner.bat") verify --verbose $output
Write-Host "Built $output" -ForegroundColor Green
