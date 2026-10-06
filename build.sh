#!/usr/bin/env bash
# Render build script: install backend + frontend deps, build frontend
set -e

# Backend dependencies
cd backend
pip install -r requirements.txt
cd ..

# Frontend build
cd frontend
npm install
npm run build
cd ..
