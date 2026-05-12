#!/usr/bin/env bash
# ============================================================================
# Bootstrap Infisical for development
# ============================================================================
# Idempotent: safe to run multiple times.
#   - Fresh instance: creates admin, org, project, machine identity, writes .env
#   - Already bootstrapped: skips gracefully
#
# Usage: ./scripts/bootstrap-infisical.sh
# ============================================================================

set -euo pipefail

INFISICAL_URL="${INFISICAL_URL:-http://localhost:8089}"
ENV_FILE=".env"
SENTINEL_FILE=".infisical-bootstrapped"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[infisical]${NC} $1"; }
warn()  { echo -e "${YELLOW}[infisical]${NC} $1"; }

# --- Wait for Infisical to be ready ---
info "Waiting for Infisical at ${INFISICAL_URL}..."
for i in $(seq 1 30); do
  if curl -sf "${INFISICAL_URL}/api/status" > /dev/null 2>&1; then
    break
  fi
  sleep 2
done

if ! curl -sf "${INFISICAL_URL}/api/status" > /dev/null 2>&1; then
  warn "Infisical not reachable after 60s — skipping bootstrap (secrets will use env vars)"
  exit 0
fi

# --- Check if already bootstrapped locally ---
if [ -f "$SENTINEL_FILE" ]; then
  info "Already bootstrapped (${SENTINEL_FILE} exists). Skipping."
  exit 0
fi

# --- Step 1: Bootstrap (admin + org + machine identity) ---
info "Bootstrapping Infisical instance..."
BOOTSTRAP=$(curl -sf -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@cellar.local",
    "password": "Cellar2024!Dev",
    "organization": "Cellar"
  }' \
  "${INFISICAL_URL}/api/v1/admin/bootstrap" 2>&1) || {
    # Already bootstrapped by someone else (manual UI signup)
    warn "Instance already initialized (manual setup detected)."
    warn "To complete setup: open ${INFISICAL_URL}, create a project, and set INFISICAL_TOKEN in .env"
    warn "Or run: make nuke && make up  — for a fresh auto-bootstrap"
    touch "$SENTINEL_FILE"
    exit 0
  }

ADMIN_TOKEN=$(echo "$BOOTSTRAP" | python3 -c "import sys,json; print(json.load(sys.stdin)['identity']['credentials']['token'])")
ORG_ID=$(echo "$BOOTSTRAP" | python3 -c "import sys,json; print(json.load(sys.stdin)['organization']['id'])")
info "Admin account created (admin@cellar.local)"

# --- Step 2: Create project ---
info "Creating project 'cellar'..."
PROJECT=$(curl -sf -X POST \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"projectName":"cellar","slug":"cellar","type":"secret-manager"}' \
  "${INFISICAL_URL}/api/v1/projects")

PROJECT_ID=$(echo "$PROJECT" | python3 -c "import sys,json; print(json.load(sys.stdin)['project']['id'])")
info "Project created: ${PROJECT_ID}"

# --- Step 3: Create service identity ---
info "Creating machine identity 'cellar-backend'..."
IDENTITY=$(curl -sf -X POST \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"cellar-backend\",\"organizationId\":\"${ORG_ID}\",\"role\":\"admin\"}" \
  "${INFISICAL_URL}/api/v1/identities")

IDENTITY_ID=$(echo "$IDENTITY" | python3 -c "import sys,json; print(json.load(sys.stdin)['identity']['id'])")

# --- Step 4: Attach Universal Auth ---
curl -sf -X POST \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"accessTokenTTL":2592000,"accessTokenMaxTTL":2592000,"accessTokenNumUsesLimit":0}' \
  "${INFISICAL_URL}/api/v1/auth/universal-auth/identities/${IDENTITY_ID}" > /dev/null

UA_INFO=$(curl -sf -X GET \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  "${INFISICAL_URL}/api/v1/auth/universal-auth/identities/${IDENTITY_ID}")

CLIENT_ID=$(echo "$UA_INFO" | python3 -c "import sys,json; print(json.load(sys.stdin)['identityUniversalAuth']['clientId'])")

# --- Step 5: Create client secret ---
SECRET_RESP=$(curl -sf -X POST \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"description":"dev bootstrap","ttl":0,"numUsesLimit":0}' \
  "${INFISICAL_URL}/api/v1/auth/universal-auth/identities/${IDENTITY_ID}/client-secrets")

CLIENT_SECRET=$(echo "$SECRET_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['clientSecret'])")

# --- Step 6: Add identity to project ---
curl -sf -X POST \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"role":"admin"}' \
  "${INFISICAL_URL}/api/v1/projects/${PROJECT_ID}/memberships/identities/${IDENTITY_ID}" > /dev/null

info "Machine identity configured"

# --- Step 7: Login to get access token ---
LOGIN=$(curl -sf -X POST \
  -H "Content-Type: application/json" \
  -d "{\"clientId\":\"${CLIENT_ID}\",\"clientSecret\":\"${CLIENT_SECRET}\"}" \
  "${INFISICAL_URL}/api/v1/auth/universal-auth/login")

ACCESS_TOKEN=$(echo "$LOGIN" | python3 -c "import sys,json; print(json.load(sys.stdin)['accessToken'])")

# --- Step 8: Write to .env ---
info "Writing Infisical credentials to ${ENV_FILE}..."

# Create .env if it doesn't exist
touch "$ENV_FILE"

# Remove old Infisical vars if present
grep -v '^INFISICAL_' "$ENV_FILE" > "${ENV_FILE}.tmp" 2>/dev/null || true
mv "${ENV_FILE}.tmp" "$ENV_FILE"

cat >> "$ENV_FILE" << EOF

# Infisical (auto-generated by scripts/bootstrap-infisical.sh)
INFISICAL_TOKEN=${ACCESS_TOKEN}
INFISICAL_PROJECT_ID=${PROJECT_ID}
INFISICAL_CLIENT_ID=${CLIENT_ID}
INFISICAL_CLIENT_SECRET=${CLIENT_SECRET}
EOF

# --- Mark as done ---
echo "${PROJECT_ID}" > "$SENTINEL_FILE"

info "Bootstrap complete!"
info "  Infisical UI:  ${INFISICAL_URL}"
info "  Admin login:   admin@cellar.local / Cellar2024!Dev"
info "  Project ID:    ${PROJECT_ID}"
info "  Credentials written to .env"
