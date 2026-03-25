#!/bin/bash

# Script de inicio rápido para Atlas AI Backend
# Este script activa el entorno virtual e inicia el servidor

echo "🚀 Starting Atlas AI Backend..."
echo ""

# Activar entorno virtual
if [ -d "venv" ]; then
    echo "✅ Activating virtual environment..."
    source venv/Scripts/activate
else
    echo "❌ Virtual environment not found!"
    echo "Please run: python -m venv venv && source venv/Scripts/activate && pip install -r requirements.txt"
    exit 1
fi

# Verificar que las dependencias estén instaladas
if ! python -c "import fastapi" 2>/dev/null; then
    echo "❌ Dependencies not installed!"
    echo "Please run: pip install -r requirements.txt"
    exit 1
fi

echo "✅ Dependencies OK"
echo ""

# Iniciar servidor
echo "🌐 Starting server on http://0.0.0.0:8000"
echo "📚 API Docs available at http://localhost:8000/docs"
echo "🔌 WebSocket endpoint: ws://localhost:8000/api/ws"
echo ""
echo "Press CTRL+C to stop"
echo ""

python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
