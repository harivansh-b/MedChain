# ── MedChain Backend ─────────────────────────────────────────────────────────
# Build context → project root.
# Render uses this Dockerfile directly after cloning the repo.
#
# Stage 1: compile the Solidity contracts (no Node.js in the final image)
FROM node:20-alpine AS contract-builder

WORKDIR /contracts

COPY contracts/package.json contracts/package-lock.json ./
RUN npm ci

COPY contracts/ .

# Compile — produces artifacts/contracts/*.json
RUN npx hardhat compile

# ── Stage 2: Python backend ───────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /medchain

# Install Python dependencies (cached layer)
COPY backend/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY backend/app/ app/

# Copy compiled contract artifacts from Stage 1
# evm_blockchain.py resolves: Path(__file__).parents[3] / "contracts/artifacts/contracts"
# from /medchain/app/services/ → /medchain/contracts/artifacts/contracts  ✓
COPY --from=contract-builder /contracts/artifacts/ contracts/artifacts/

EXPOSE 8000

# Secrets are supplied at runtime via environment variables (Render dashboard / .env)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
