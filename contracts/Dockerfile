# ── MedChain Contracts ────────────────────────────────────────────────────────
# One-shot image: compiles the Solidity contracts and exits.
# The compiled artifacts/ directory is committed to the repo, so you only
# need to run this when the .sol files change.
#
# Usage (from project root):
#   docker build -f contracts/Dockerfile -t medchain-contracts .
#   docker run --rm -v "$(pwd)/contracts/artifacts:/build/artifacts" medchain-contracts
FROM node:20-alpine

WORKDIR /build

COPY contracts/package.json contracts/package-lock.json ./
RUN npm ci

COPY contracts/ .

# hardhat.config.js reads ../backend/.env — supply it at runtime if needed.
# For compile-only (no network), no secrets are needed.
CMD ["npx", "hardhat", "compile"]
