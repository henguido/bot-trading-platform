#!/bin/bash

# Ruta al backend y frontend
BACKEND_DIR="./bot"
FRONTEND_DIR="./frontend"

# Comando para backend
# Sin recarga automatica y con un unico worker, a proposito (P0-13): la recarga
# respawnea el proceso y varios workers crean varios procesos, cada uno
# intentando operar. El candado de liderazgo lo impediria, pero no conviene
# provocarlo en un script que pretende parecerse a produccion.
BACKEND_CMD="uvicorn backend.main:app --workers 1"

# Comando para frontend
FRONTEND_CMD="npm run dev"

# Abre nueva terminal para el backend
gnome-terminal -- bash -c "cd $BACKEND_DIR && $BACKEND_CMD; exec bash"

# Abre nueva terminal para el frontend
gnome-terminal -- bash -c "cd $FRONTEND_DIR && $FRONTEND_CMD; exec bash"

echo "🚀 Proyecto iniciado: Backend (bot) y Frontend corriendo en terminales separadas."
