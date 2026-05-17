#!/usr/bin/env bash
# Bootstrap script for Mac / Linux
# Run once after cloning: bash setup.sh
set -e

echo "=== LedgerFlow Environment Setup ==="

# 1. Check conda
if ! command -v conda &>/dev/null; then
  echo "conda not found. Installing Miniconda..."
  OS=$(uname -s)
  if [ "$OS" = "Darwin" ]; then
    curl -fsSL https://repo.anaconda.com/miniconda/Miniconda3-latest-MacOSX-x86_64.sh -o /tmp/miniconda.sh
  else
    curl -fsSL https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -o /tmp/miniconda.sh
  fi
  bash /tmp/miniconda.sh -b -p "$HOME/miniconda3"
  export PATH="$HOME/miniconda3/bin:$PATH"
  conda init bash
  echo "Miniconda installed. Restart your shell or run: source ~/.bashrc"
fi

# 2. Create / update environment
if conda env list | grep -q "^ledgerflow "; then
  echo "Updating existing ledgerflow environment..."
  conda env update -f environment.yml --prune
else
  echo "Creating ledgerflow conda environment..."
  conda env create -f environment.yml
fi

echo ""
echo "Done! Activate with:  conda activate ledgerflow"
echo "Then run:             python data_generator/generate_transactions.py"
