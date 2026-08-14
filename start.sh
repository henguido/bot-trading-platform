#!/bin/bash

# Ruta al backend y frontend
BACKEND_DIR="./bot"
FRONTEND_DIR="./frontend"

# Comando para backend
BACKEND_CMD="uvicorn backend.main:app --reload"

# Comando para frontend
FRONTEND_CMD="npm run dev"

# Abre nueva terminal para el backend
gnome-terminal -- bash -c "cd $BACKEND_DIR && $BACKEND_CMD; exec bash"

# Abre nueva terminal para el frontend
gnome-terminal -- bash -c "cd $FRONTEND_DIR && $FRONTEND_CMD; exec bash"

echo "🚀 Proyecto iniciado: Backend (bot) y Frontend corriendo en terminales separadas."
