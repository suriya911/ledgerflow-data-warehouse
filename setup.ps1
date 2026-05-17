# Bootstrap script for Windows PowerShell
# Run once after cloning:  .\setup.ps1
# If execution policy blocks it:  Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

Write-Host "=== LedgerFlow Environment Setup ===" -ForegroundColor Cyan

# 1. Check / install Miniconda
$condaCmd = Get-Command conda -ErrorAction SilentlyContinue
if (-not $condaCmd) {
    Write-Host "conda not found. Downloading Miniconda3 for Windows..." -ForegroundColor Yellow
    $installer = "$env:TEMP\Miniconda3.exe"
    Invoke-WebRequest `
        "https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe" `
        -OutFile $installer
    Write-Host "Running installer (silent)..."
    Start-Process -FilePath $installer `
        -ArgumentList "/InstallationType=JustMe /RegisterPython=0 /S /D=$env:USERPROFILE\Miniconda3" `
        -Wait
    # Add to PATH for this session
    $env:PATH = "$env:USERPROFILE\Miniconda3\Scripts;$env:USERPROFILE\Miniconda3;$env:PATH"
    Write-Host "Miniconda installed at $env:USERPROFILE\Miniconda3" -ForegroundColor Green
    Write-Host "NOTE: Open a new PowerShell window after setup to use 'conda' normally." -ForegroundColor Yellow
}

# 2. Refresh conda in this session
$condaBase = conda info --base 2>$null
if (-not $condaBase) { $condaBase = "$env:USERPROFILE\Miniconda3" }
$condaHook = "$condaBase\shell\condabin\conda-hook.ps1"
if (Test-Path $condaHook) { & $condaHook }

# 3. Create or update environment
$envExists = conda env list 2>$null | Select-String "^ledgerflow"
if ($envExists) {
    Write-Host "Updating existing ledgerflow environment..." -ForegroundColor Cyan
    conda env update -f environment.yml --prune
} else {
    Write-Host "Creating ledgerflow conda environment (this takes 2-5 minutes)..." -ForegroundColor Cyan
    conda env create -f environment.yml
}

Write-Host ""
Write-Host "Done!" -ForegroundColor Green
Write-Host "Activate with:   conda activate ledgerflow"
Write-Host "Then run:        python data_generator/generate_transactions.py"
