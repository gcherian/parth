#!/bin/bash
set -e

PYTHON=/opt/homebrew/bin/python3.11

echo ""
echo "  Setting up Parth AI Server..."
echo ""

# 1. Create virtual environment
if [ ! -d "venv" ]; then
    echo "  Creating Python virtual environment..."
    $PYTHON -m venv venv
fi

source venv/bin/activate

# 2. Install Python dependencies
echo "  Installing FastAPI + dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo ""
echo "  Checking Ollama models..."
ollama list

echo ""
echo "  Setup complete!"
echo "  Run the server with:  ./start.sh"
echo ""
