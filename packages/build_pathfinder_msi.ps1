param(
    [string]$Version = "0.1.0",
    [string]$Python = "python",
    [string]$Configuration = "Release"
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Build = Join-Path $Root ".build"
$Dist = Join-Path $Root "dist"
$Venv = Join-Path $Build "venv-sys"
$WixDir = Join-Path $Build "wix314"
$AppSource = Join-Path $Build "dist\Pathfinder"
$WixObj = Join-Path $Build "wix-obj"
$MsiPath = Join-Path $Dist "Pathfinder-$Version-x64.msi"

New-Item -ItemType Directory -Force -Path $Build, $Dist, $WixObj | Out-Null

if (-not (Test-Path (Join-Path $Venv "bin\python.exe"))) {
    & $Python -m venv --system-site-packages $Venv
}

$VenvPython = Join-Path $Venv "bin\python.exe"
try {
    & $VenvPython -m PyInstaller --version | Out-Null
} catch {
    & $VenvPython -m pip install pyinstaller
}

& $VenvPython -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --console `
    --name Pathfinder `
    --distpath (Join-Path $Build "dist") `
    --workpath (Join-Path $Build "pyinstaller-msys") `
    --specpath $PSScriptRoot `
    --add-data "$Root\25.py;." `
    --add-data "$Root\pathfinder.md;." `
    --add-data "$Root\pathfinder_instruction_template.py;." `
    --add-data "$Root\17.txt;." `
    --add-binary "$Root\basis_tensor.exe;." `
    --hidden-import PIL.Image `
    --hidden-import PIL.ImageTk `
    --hidden-import tkinter `
    --hidden-import tkinter.filedialog `
    --hidden-import tkinter.messagebox `
    --exclude-module numpy `
    --exclude-module pygame `
    (Join-Path $Root "pathfinder.py")

if (-not (Test-Path (Join-Path $WixDir "candle.exe"))) {
    $WixZip = Join-Path $Build "wix314-binaries.zip"
    if (-not (Test-Path $WixZip)) {
        Invoke-WebRequest `
            -Uri "https://github.com/wixtoolset/wix3/releases/download/wix3141rtm/wix314-binaries.zip" `
            -OutFile $WixZip
    }
    Expand-Archive -LiteralPath $WixZip -DestinationPath $WixDir -Force
}

$Heat = Join-Path $WixDir "heat.exe"
$Candle = Join-Path $WixDir "candle.exe"
$Light = Join-Path $WixDir "light.exe"

& $Heat dir $AppSource `
    -cg PathfinderFiles `
    -dr INSTALLFOLDER `
    -srd `
    -sreg `
    -gg `
    -var var.AppSource `
    -platform x64 `
    -out (Join-Path $PSScriptRoot "PathfinderFiles.wxs")

Remove-Item -LiteralPath $WixObj -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $WixObj | Out-Null

& $Candle `
    -nologo `
    -arch x64 `
    "-dAppSource=$AppSource" `
    -out "$WixObj\" `
    (Join-Path $PSScriptRoot "Product.wxs") `
    (Join-Path $PSScriptRoot "PathfinderFiles.wxs")

& $Light `
    -nologo `
    -sval `
    -ext WixUIExtension `
    -cultures:en-us `
    -spdb `
    -out $MsiPath `
    (Join-Path $WixObj "Product.wixobj") `
    (Join-Path $WixObj "PathfinderFiles.wixobj")

Write-Host "Built $MsiPath"
