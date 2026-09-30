<#
.SYNOPSIS
    Instala (silenciosamente) o Tesseract no Windows quando ele estiver ausente.

.DESCRIPTION
    Chamado pelo instalador Inno Setup. Baixa o instalador do UB-Mannheim
    (versao/URL/SHA256 fixados em tesseract.json), verifica o hash, roda
    /VERYSILENT, garante `por.traineddata` e valida com `tesseract --list-langs`.

    Codigos de saida:
      0 = ok (ja instalado ou instalado com sucesso)
      1 = erro geral (ex.: config ausente)
      2 = falha de download (provavel falta de rede)
      3 = verificacao SHA256 falhou
      4 = instalacao/validacao falhou

    Rode com: powershell.exe -ExecutionPolicy Bypass -NoProfile -File install-tesseract.ps1

.PARAMETER ConfigPath
    Caminho do tesseract.json (default: ao lado deste script).

.PARAMETER InstallDir
    Diretorio de instalacao esperado do Tesseract.
#>
[CmdletBinding()]
param(
    [string]$ConfigPath = (Join-Path $PSScriptRoot 'tesseract.json'),
    [string]$InstallDir = 'C:\Program Files\Tesseract-OCR'
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

function Exit-With {
    param([int]$Code, [string]$Message)
    Write-Host $Message
    exit $Code
}

function Get-RemoteFile {
    param([string]$Url, [string]$Dest)
    try {
        Invoke-WebRequest -Uri $Url -OutFile $Dest -UseBasicParsing -TimeoutSec 600
    } catch {
        Exit-With -Code 2 -Message "download falhou: $Url ($($_.Exception.Message))"
    }
}

function Assert-Sha256 {
    param([string]$Path, [string]$Expected)
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
    if ($actual -ne $Expected.ToUpperInvariant()) {
        Exit-With -Code 3 -Message "SHA256 divergente para $Path (esperado $Expected, obtido $actual)"
    }
}

function Get-TesseractExe {
    $candidates = @(
        (Join-Path $InstallDir 'tesseract.exe'),
        (Join-Path $env:ProgramFiles 'Tesseract-OCR\tesseract.exe')
    )
    if (${env:ProgramFiles(x86)}) {
        $candidates += (Join-Path ${env:ProgramFiles(x86)} 'Tesseract-OCR\tesseract.exe')
    }
    $onPath = Get-Command 'tesseract.exe' -ErrorAction SilentlyContinue
    if ($onPath) { $candidates = @($onPath.Source) + $candidates }
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) { return $candidate }
    }
    return $null
}

# 1) Ja instalado? Nada a fazer.
$existing = Get-TesseractExe
if ($existing) {
    Exit-With -Code 0 -Message "Tesseract ja instalado: $existing"
}

if (-not (Test-Path -LiteralPath $ConfigPath)) {
    Exit-With -Code 1 -Message "config do Tesseract nao encontrada: $ConfigPath"
}
$config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json

$temp = Join-Path $env:TEMP ('screen-watch-tesseract-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temp -Force | Out-Null

try {
    $installer = Join-Path $temp 'tesseract-setup.exe'
    Get-RemoteFile -Url $config.installer.url -Dest $installer
    Assert-Sha256 -Path $installer -Expected $config.installer.sha256

    $process = Start-Process -FilePath $installer -Wait -PassThru -ArgumentList @(
        '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-'
    )
    if ($process.ExitCode -ne 0) {
        Exit-With -Code 4 -Message "o instalador do Tesseract retornou $($process.ExitCode)"
    }

    $tesseract = Get-TesseractExe
    if (-not $tesseract) {
        Exit-With -Code 4 -Message 'tesseract.exe nao encontrado apos a instalacao'
    }

    # 2) Garante `por.traineddata` (o pacote traz `eng`, mas nao `por`).
    $tessdata = Join-Path (Split-Path -Parent $tesseract) 'tessdata'
    if (-not (Test-Path -LiteralPath $tessdata)) {
        New-Item -ItemType Directory -Path $tessdata -Force | Out-Null
    }
    $portuguese = Join-Path $tessdata 'por.traineddata'
    $needDownload = $true
    if (Test-Path -LiteralPath $portuguese) {
        $current = (Get-FileHash -LiteralPath $portuguese -Algorithm SHA256).Hash
        if ($current -eq $config.traineddata.sha256.ToUpperInvariant()) { $needDownload = $false }
    }
    if ($needDownload) {
        $staged = Join-Path $temp 'por.traineddata'
        Get-RemoteFile -Url $config.traineddata.url -Dest $staged
        Assert-Sha256 -Path $staged -Expected $config.traineddata.sha256
        Copy-Item -LiteralPath $staged -Destination $portuguese -Force
    }

    # 3) Valida os idiomas exigidos pelo modo advanced (`por+eng`).
    $langs = (& $tesseract --list-langs 2>&1) | Out-String
    $hasEnglish = $langs -match '(?m)^\s*eng\s*$'
    $hasPortuguese = $langs -match '(?m)^\s*por\s*$'
    if (-not ($hasEnglish -and $hasPortuguese)) {
        Exit-With -Code 4 -Message "idiomas insuficientes no Tesseract: $langs"
    }

    Exit-With -Code 0 -Message 'Tesseract instalado e validado (eng+por).'
}
finally {
    Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue
}
