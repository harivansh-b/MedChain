# ── MedChain Frontend ────────────────────────────────────────────────────────
# Build context → project root (e:\MedChain).
# docker-compose sets:
#   context: .
#   dockerfile: frontend/Dockerfile
#
# The backend API URL is baked into the bundle at build time.
# Override with: docker compose build --build-arg VITE_MEDCHAIN_API_URL=https://api.example.com

FROM node:20-alpine

WORKDIR /app

# Install deps (cached layer when package files unchanged)
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# Copy full source
COPY frontend/ .

# Bake the API URL at build time via Vite env var
ARG VITE_MEDCHAIN_API_URL=http://localhost:8000
ENV VITE_MEDCHAIN_API_URL=$VITE_MEDCHAIN_API_URL

RUN npm run build

EXPOSE 4173

# vite preview serves the built /dist on port 4173
CMD ["npm", "run", "preview", "--", "--host", "0.0.0.0", "--port", "4173"]
