#!/bin/bash

echo ""
echo "========================================"
echo "WhatsApp + Gmail Agent"
echo "========================================"
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed"
    exit 1
fi

# Create virtual environment if not exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install requirements
echo "Installing dependencies..."
pip install -r requirements.txt -q

# Check for .env
if [ ! -f ".env" ]; then
    echo ""
    echo "WARNING: .env file not found!"
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo ""
    echo "Please edit .env with your API keys before continuing."
    read -p "Press Enter to continue..."
fi

# Run the app
echo ""
echo "Starting agent..."
echo "Dashboard: http://localhost:5000"
echo ""
python main.py
