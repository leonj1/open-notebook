#!/bin/bash

echo "🔧 Setting up Open Notebook Playwright Scripts..."
echo ""

# Check if we're in the right directory
if [ ! -f "package.json" ]; then
    echo "❌ Error: package.json not found. Please run this script from the scripts/playwright directory."
    exit 1
fi

# Install Node.js dependencies
echo "📦 Installing Node.js dependencies..."
npm install

if [ $? -eq 0 ]; then
    echo "✅ Dependencies installed successfully!"
    echo ""
    echo "🎉 Setup complete!"
    echo ""
    echo "📖 Usage:"
    echo "  npm run submit-podcast  - Submit Wikipedia URL and generate podcast"
    echo ""
    echo "⚠️  Make sure Open Notebook is running before executing scripts:"
    echo "  cd ../../ && make start-sqlite"
else
    echo "❌ Failed to install dependencies"
    exit 1
fi
