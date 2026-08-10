#!/usr/bin/env bash
# Regression suite for the local guards.
#
#     bash .claude/hooks/test_guards.sh
#
# If a guard stops blocking, the team silently loses its protection. This script
# detects that. The `guards` CI job runs it on every PR.
#
# Two design details that look convoluted and are not:
#
#  1. The cases live in a file rather than on the command line, because
#     guard_bash.py inspects the whole command: if the forbidden commands were
#     in the `bash -c`, the guard would block its own test.
#  2. The credential fixtures are base64-encoded. In plain text, guard_edit.py
#     would block writing this file and gitleaks would flag the repository.

set -uo pipefail

root="$(git rev-parse --show-toplevel)"
hooks="$root/.claude/hooks"
failures=0
cases=0

# Throwaway repository standing on a valid working branch, so the rules other than
# the protected-branch one can be exercised.
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/repo/docs"
git -C "$tmp/repo" init -q -b feature/infra-guard-tests
git -C "$tmp/repo" commit -q --allow-empty -m "chore(infra): base"

d() { printf '%s' "$1" | base64 -d; }
MP_TOKEN="$(d 'QVBQX1VTUi0xMjM0NTY3ODkwMTIzNDU2LWFiY2RlZmdoaWo=')"
SECRET="$(d 'YXBpX2tleSA9ICJhQjN4WTl6UTd3TG0yIg==')"
PRIVATE_KEY="$(d 'LS0tLS1CRUdJTiBSU0EgUFJJVkFURSBLRVktLS0tLQ==')"
FLOAT_DECIMAL="$(d 'eCA9IERlY2ltYWwoMC4xKQ==')"

check() { # <expected> <actual> <description>
  cases=$((cases + 1))
  if [ "$2" = "$1" ]; then
    printf '  ok    %s\n' "$3"
  else
    printf '  FAIL  %s  (expected %s, got %s)\n' "$3" "$1" "$2"
    failures=$((failures + 1))
  fi
}

decision() { # JSON payload on stdin -> prints "deny" or "ALLOW"
  local output
  output="$(python3 "$1")"
  if printf '%s' "$output" | jq -e '.hookSpecificOutput.permissionDecision == "deny"' \
    > /dev/null 2>&1; then
    echo deny
  else
    echo ALLOW
  fi
}

bash_case() { # <expected> <command> [description]
  local actual
  actual="$(jq -nc --arg c "$2" '{tool_input:{command:$c}}' | decision "$hooks/guard_bash.py")"
  check "$1" "$actual" "${3:-$2}"
}

edit_case() { # <expected> <relative path> <content> <description>
  local actual
  actual="$(jq -nc --arg p "$tmp/repo/$2" --arg c "$3" \
    '{tool_input:{file_path:$p,content:$c}}' | decision "$hooks/guard_edit.py")"
  check "$1" "$actual" "$4"
}

echo "guard_bash.py — workflow"
bash_case deny "git commit $(d 'LS1uby12ZXJpZnk=') -m x" 'commit skipping the checks'
bash_case deny 'git push origin main'                    'direct push to main'
bash_case deny 'git push origin develop'                 'direct push to develop'
bash_case deny 'git push --force origin feature/x'       'forced push'
bash_case deny 'git checkout -b my-branch'               'branch without the naming scheme'
bash_case deny 'git checkout -b Feature/Billing_X'       'branch with capitals and underscore'
bash_case deny 'rm -rf /'                                'recursive delete of the root'
bash_case ALLOW 'git checkout -b feature/billing-cuit-validation'   'valid feature branch'
bash_case ALLOW 'git checkout -b fix/payments-duplicate-webhook'    'valid fix branch'
bash_case ALLOW 'git checkout -b hotfix/mercadopago-webhook-error'  'valid hotfix branch'
bash_case ALLOW 'git push -u origin feature/billing-cuit-validation' 'push of a working branch'
bash_case ALLOW 'pytest -q'                              'harmless command'
bash_case ALLOW 'rm -rf .venv'                           'narrowly scoped delete'

echo "guard_edit.py — paths and content"
edit_case deny  '.env'          'X=1'                'a .env file'
edit_case deny  '.env.production' 'X=1'              'an environment-specific .env file'
edit_case ALLOW 'backend/.env.example' 'MP_ACCESS_TOKEN=' 'the versioned .env template is exempt from the credential-file rule'
edit_case deny  'docs/afip.key' 'x'                  'private key by extension'
edit_case deny  'billing/x.py'  'x = 1'              'unauthorized top-level directory'
edit_case deny  'docs/a.py'     "MP = \"$MP_TOKEN\"" 'MercadoPago token'
edit_case deny  'docs/a.py'     "$SECRET"            'hardcoded secret'
edit_case deny  'docs/a.py'     "$PRIVATE_KEY"       'private key in the content'
edit_case deny  'docs/a.py'     "$FLOAT_DECIMAL"     'Decimal from a float literal'
edit_case ALLOW 'docs/a.md'     "wrong: $FLOAT_DECIMAL" 'the antipattern quoted in documentation'
edit_case ALLOW 'docs/a.py'     'api_key = "<your-token-here>"' 'placeholder value'
edit_case ALLOW 'docs/a.py'     'api_key = os.environ["K"]'     'read from the environment'
edit_case ALLOW 'docs/adr/1.md' 'text'               'subdirectory of docs/'
edit_case ALLOW 'setup.cfg'     '[x]'                'repo-wide loose file at the root'

echo "guard_edit.py — monorepo root versus package"
edit_case deny  'package.json'   '{}'                'dashboard config dropped at the root'
edit_case deny  'requirements.txt' 'fastapi'         'backend app dependencies at the root'
edit_case deny  'tsconfig.json'  '{}'                'TypeScript config at the root'
edit_case deny  '.env.example'   'X='                'env template at the root instead of per package'
edit_case ALLOW 'dashboard/package.json'    '{}'     'dashboard config inside its package'
edit_case ALLOW 'backend/requirements.txt'  'fastapi' 'backend dependencies inside its package'
edit_case ALLOW 'dashboard/.env.example'    'NEXT_PUBLIC_API_BASE_URL=' 'dashboard env template'
edit_case ALLOW 'pyproject.toml' '[tool.ruff]'       'repo-wide tooling config at the root'

echo "guard_architecture.py — hexagonal and bounded-context boundaries"
B="backend/src/cheatsheet"
arch_case() { # <expected> <relative path> <content> <description>
  local actual
  actual="$(jq -nc --arg p "$root/$2" --arg c "$3" \
    '{tool_input:{file_path:$p,content:$c}}' | decision "$hooks/guard_architecture.py")"
  check "$1" "$actual" "$4"
}
arch_case deny "$B/contexts/billing/domain/comprobante.py" \
  'from sqlalchemy import Column' 'R1 domain imports an ORM'
arch_case deny "$B/contexts/billing/domain/comprobante.py" \
  'from cheatsheet.contexts.billing.infrastructure.repo import R' 'R1 domain imports its own infrastructure'
arch_case deny "$B/contexts/billing/application/emitir.py" \
  'from cheatsheet.contexts.billing.infrastructure.arca import A' 'R2 application imports infrastructure'
arch_case deny "$B/contexts/payments/application/cobrar.py" \
  'from cheatsheet.contexts.billing.domain.comprobante import C' "R3 reaches into another context's domain"
arch_case deny "$B/shared/tenant.py" \
  'from cheatsheet.contexts.billing.application import X' 'R4 shared kernel depends on a context'
arch_case ALLOW "$B/contexts/billing/domain/comprobante.py" \
  'from decimal import Decimal' 'domain using the standard library'
arch_case ALLOW "$B/contexts/billing/domain/comprobante.py" \
  'from cheatsheet.shared.money import Monto' 'domain using the shared kernel'
arch_case ALLOW "$B/contexts/payments/application/cobrar.py" \
  'from cheatsheet.contexts.billing.application import EmitirComprobante' 'cross-context via application layer'
arch_case ALLOW "$B/contexts/billing/infrastructure/arca.py" \
  'from cheatsheet.contexts.billing.domain.comprobante import C' 'infrastructure using its own domain'
arch_case ALLOW "$B/contexts/billing/infrastructure/arca.py" \
  'import zeep' 'infrastructure using a SOAP client'
arch_case ALLOW "$B/api/main.py" \
  'from fastapi import FastAPI' 'composition root using FastAPI'
D="dashboard/src"
arch_case deny "$D/features/billing/components/Form.tsx" \
  'import { x } from "@/features/payments/api/client";' 'R5 reaches into another feature via alias'
arch_case deny "$D/features/billing/components/Form.tsx" \
  'import { x } from "../../payments/hooks/useCobro";' 'R5 reaches into another feature via relative path'
arch_case deny "$D/shared/table.tsx" \
  'import { x } from "@/features/billing";' 'R5 shared depends on a feature'
arch_case ALLOW "$D/features/billing/components/Form.tsx" \
  'import { x } from "@/features/payments";' 'cross-feature via public entry point'
arch_case ALLOW "$D/features/billing/components/Form.tsx" \
  'import { Button } from "@/shared";' 'feature using shared'
arch_case ALLOW "$D/features/billing/components/Form.tsx" \
  'import { api } from "../api/client";' 'internal import within the same feature'
arch_case ALLOW "$D/app/(panel)/billing/page.tsx" \
  'import { B } from "@/features/billing";
import { P } from "@/features/payments";' 'a route composing several contexts'
arch_case ALLOW "$D/features/billing/api/client.ts" \
  'import { z } from "zod";' 'third-party package'

echo
if [ "$failures" -eq 0 ]; then
  echo "$cases cases, all correct — the guards are active."
  exit 0
fi
echo "$cases cases, $failures failure(s) — the guards are NOT protecting the repository."
exit 1
