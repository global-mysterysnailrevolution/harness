#!/usr/bin/env bash
# /usr/local/sbin/openclaw_apply_config
# Root-owned apply script for the OpenClaw self-upgrade pipeline.
# Reads proposed changes from config_desired/, validates, applies atomically,
# health-checks, and rolls back on failure.
#
# This script is the ONLY way the agent's proposed changes reach the host.
# It is called via sudo by the openclaw-bot user.
#
# Owner: root:root  Mode: 0755
# Location on VPS: /usr/local/sbin/openclaw_apply_config

set -euo pipefail

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
HARNESS_ROOT="/opt/harness"
DESIRED_DIR="$HARNESS_ROOT/config_desired"
BACKUP_ROOT="$HARNESS_ROOT/config_backups"
APPLIED_ROOT="$HARNESS_ROOT/config_applied"
MANIFEST="$DESIRED_DIR/manifest.json"
MAX_APPLIES_PER_HOUR=5
MAX_FILE_SIZE_BYTES=1048576  # 1 MB
MAX_BACKUPS=20
RATE_FILE="$BACKUP_ROOT/.rate_log"

# Whitelisted destination prefixes (agent cannot write outside these)
ALLOWED_PREFIXES=(
    "/opt/harness/igfetch/"
    "/opt/harness/openclaw/"
    "/opt/harness/scripts/"
    "/opt/harness/adapters/"
    "/opt/harness/ai/supervisor/"
    "/opt/harness/config_desired/"
    "/opt/harness/secrets/"
)

# Whitelisted exact paths (for system files outside /opt/harness)
ALLOWED_EXACT=(
    "/etc/systemd/system/igfetch.service"
    "/docker/openclaw-kx9d/docker-compose.yml"
)

# Allowed services to restart
ALLOWED_SERVICES=(
    "igfetch"
)

# Allowed docker compose restarts
ALLOWED_DOCKER_RESTARTS=(
    "openclaw"
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_FILE=""
log() {
    local msg="[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"
    echo "$msg"
    [[ -n "$LOG_FILE" ]] && echo "$msg" >> "$LOG_FILE"
}

die() {
    log "FATAL: $*"
    exit 1
}

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

is_path_allowed() {
    local dest="$1"

    # Resolve to absolute, block path traversal
    local resolved
    resolved=$(realpath -m "$dest" 2>/dev/null) || return 1
    if [[ "$resolved" != "$dest" ]] && [[ "$resolved" != "${dest%/}" ]]; then
        # Path has traversal components (../ etc)
        # Allow only if resolved path is also in whitelist
        dest="$resolved"
    fi

    # Check exact matches
    for exact in "${ALLOWED_EXACT[@]}"; do
        [[ "$dest" == "$exact" ]] && return 0
    done

    # Check prefix matches
    for prefix in "${ALLOWED_PREFIXES[@]}"; do
        [[ "$dest" == "$prefix"* ]] && return 0
    done

    return 1
}

is_service_allowed() {
    local svc="$1"
    for allowed in "${ALLOWED_SERVICES[@]}"; do
        [[ "$svc" == "$allowed" ]] && return 0
    done
    return 1
}

is_docker_restart_allowed() {
    local svc="$1"
    for allowed in "${ALLOWED_DOCKER_RESTARTS[@]}"; do
        [[ "$svc" == "$allowed" ]] && return 0
    done
    return 1
}

is_text_file() {
    local f="$1"
    file --brief --mime "$f" 2>/dev/null | grep -q "text/" && return 0
    # Also allow empty files and JSON
    [[ ! -s "$f" ]] && return 0
    python3 -c "open('$f','r').read()" 2>/dev/null && return 0
    return 1
}

validate_file_content() {
    local src="$1" dest="$2"

    # systemd unit validation
    if [[ "$dest" == *.service ]]; then
        if command -v systemd-analyze &>/dev/null; then
            systemd-analyze verify "$src" 2>&1 || {
                log "WARN: systemd-analyze verify failed for $src (non-fatal)"
            }
        fi
    fi

    # JSON validation
    if [[ "$dest" == *.json ]]; then
        python3 -c "import json; json.load(open('$src'))" 2>&1 || {
            log "ERROR: Invalid JSON: $src"
            return 1
        }
    fi

    # YAML validation (docker-compose)
    if [[ "$dest" == *docker-compose*.yml ]] || [[ "$dest" == *docker-compose*.yaml ]]; then
        if command -v docker &>/dev/null; then
            docker compose -f "$src" config --quiet 2>&1 || {
                log "WARN: docker compose config failed for $src (non-fatal)"
            }
        fi
    fi

    # Shell script syntax check
    if [[ "$dest" == *.sh ]]; then
        bash -n "$src" 2>&1 || {
            log "ERROR: Bash syntax error in $src"
            return 1
        }
    fi

    # Python syntax check
    if [[ "$dest" == *.py ]]; then
        python3 -m py_compile "$src" 2>&1 || {
            log "ERROR: Python syntax error in $src"
            return 1
        }
    fi

    return 0
}

# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------
check_rate_limit() {
    mkdir -p "$BACKUP_ROOT"
    touch "$RATE_FILE"

    local cutoff
    cutoff=$(date -u -d '1 hour ago' +%s 2>/dev/null) || cutoff=$(date -u -v-1H +%s 2>/dev/null) || cutoff=0

    local count=0
    while IFS= read -r ts; do
        [[ -z "$ts" ]] && continue
        (( ts > cutoff )) && (( count++ ))
    done < "$RATE_FILE"

    if (( count >= MAX_APPLIES_PER_HOUR )); then
        die "Rate limit exceeded: $count applies in the last hour (max $MAX_APPLIES_PER_HOUR)"
    fi

    echo "$(date -u +%s)" >> "$RATE_FILE"
}

# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------
create_backup() {
    local backup_dir="$1"
    shift
    local changes=("$@")

    mkdir -p "$backup_dir"
    log "Creating backup at $backup_dir"

    for change_json in "${changes[@]}"; do
        local dest
        dest=$(echo "$change_json" | python3 -c "import sys,json; print(json.load(sys.stdin)['dest'])")
        if [[ -f "$dest" ]]; then
            local rel="${dest#/}"
            local bk_path="$backup_dir/$rel"
            mkdir -p "$(dirname "$bk_path")"
            cp -a "$dest" "$bk_path"
            log "  Backed up: $dest"
        fi
    done
}

# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------
apply_changes() {
    local changes=("$@")

    for change_json in "${changes[@]}"; do
        local source dest owner mode
        source=$(echo "$change_json" | python3 -c "import sys,json; print(json.load(sys.stdin)['source'])")
        dest=$(echo "$change_json" | python3 -c "import sys,json; print(json.load(sys.stdin)['dest'])")
        owner=$(echo "$change_json" | python3 -c "import sys,json; print(json.load(sys.stdin).get('owner','root:root'))")
        mode=$(echo "$change_json" | python3 -c "import sys,json; print(json.load(sys.stdin).get('mode','0644'))")

        local src_path="$DESIRED_DIR/$source"

        # Validate source exists
        [[ -f "$src_path" ]] || die "Source file not found: $src_path"

        # Validate destination is whitelisted
        is_path_allowed "$dest" || die "Destination not whitelisted: $dest"

        # Validate file size
        local size
        size=$(stat -c%s "$src_path" 2>/dev/null || stat -f%z "$src_path" 2>/dev/null)
        (( size > MAX_FILE_SIZE_BYTES )) && die "File too large: $src_path ($size bytes, max $MAX_FILE_SIZE_BYTES)"

        # Validate text file
        is_text_file "$src_path" || die "Binary file not allowed: $src_path"

        # Validate content
        validate_file_content "$src_path" "$dest" || die "Content validation failed: $src_path -> $dest"

        # Atomic write: copy to .tmp, then mv
        local dest_dir
        dest_dir=$(dirname "$dest")
        mkdir -p "$dest_dir"

        local tmp_path="${dest}.openclaw-tmp"
        cp "$src_path" "$tmp_path"
        chown "$owner" "$tmp_path"
        chmod "$mode" "$tmp_path"
        mv "$tmp_path" "$dest"

        log "  Applied: $source -> $dest (owner=$owner mode=$mode)"

        # Diff logging
        if [[ -n "$LOG_FILE" ]]; then
            echo "--- DIFF for $dest ---" >> "$LOG_FILE"
            diff -u "$DESIRED_DIR/$source" "$dest" >> "$LOG_FILE" 2>&1 || true
            echo "--- END DIFF ---" >> "$LOG_FILE"
        fi
    done
}

# ---------------------------------------------------------------------------
# Restart services
# ---------------------------------------------------------------------------
restart_services() {
    local services=("$@")
    local restarted=()

    for svc in "${services[@]}"; do
        [[ -z "$svc" ]] && continue

        if is_service_allowed "$svc"; then
            log "  Restarting systemd service: $svc"
            systemctl restart "$svc" || log "WARN: Failed to restart $svc"
            restarted+=("systemd:$svc")
        elif is_docker_restart_allowed "$svc"; then
            log "  Restarting docker service: $svc"
            cd /docker/openclaw-kx9d && docker compose restart "$svc" || log "WARN: Failed to restart docker $svc"
            restarted+=("docker:$svc")
        else
            log "WARN: Service '$svc' not in allowed restart list, skipping"
        fi
    done

    # Wait for services to settle
    sleep 3
}

# ---------------------------------------------------------------------------
# Health checks
# ---------------------------------------------------------------------------
run_health_checks() {
    local checks=("$@")
    local all_ok=true

    for check_json in "${checks[@]}"; do
        local check_type
        check_type=$(echo "$check_json" | python3 -c "import sys,json; print(json.load(sys.stdin)['type'])")

        if [[ "$check_type" == "http" ]]; then
            local url expect
            url=$(echo "$check_json" | python3 -c "import sys,json; print(json.load(sys.stdin)['url'])")
            expect=$(echo "$check_json" | python3 -c "import sys,json; print(json.load(sys.stdin).get('expect',200))")

            local status
            status=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$url" 2>/dev/null) || status="000"
            if [[ "$status" == "$expect" ]]; then
                log "  Health OK: HTTP $url -> $status"
            else
                log "  Health FAIL: HTTP $url -> $status (expected $expect)"
                all_ok=false
            fi

        elif [[ "$check_type" == "systemd" ]]; then
            local service expect
            service=$(echo "$check_json" | python3 -c "import sys,json; print(json.load(sys.stdin)['service'])")
            expect=$(echo "$check_json" | python3 -c "import sys,json; print(json.load(sys.stdin).get('expect','active'))")

            local actual
            actual=$(systemctl is-active "$service" 2>/dev/null) || actual="unknown"
            if [[ "$actual" == "$expect" ]]; then
                log "  Health OK: systemd $service -> $actual"
            else
                log "  Health FAIL: systemd $service -> $actual (expected $expect)"
                all_ok=false
            fi
        fi
    done

    $all_ok
}

# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------
rollback() {
    local backup_dir="$1"
    shift
    local services=("$@")

    log "ROLLING BACK from $backup_dir"

    # Restore files
    if [[ -d "$backup_dir" ]]; then
        cd "$backup_dir"
        find . -type f | while read -r f; do
            local dest="/${f#./}"
            local dest_dir
            dest_dir=$(dirname "$dest")
            mkdir -p "$dest_dir"
            cp -a "$f" "$dest"
            log "  Restored: $dest"
        done
    fi

    # Restart services again
    restart_services "${services[@]}"

    log "Rollback complete"
}

# ---------------------------------------------------------------------------
# Cleanup old backups
# ---------------------------------------------------------------------------
prune_backups() {
    local count
    count=$(ls -1d "$BACKUP_ROOT"/2* 2>/dev/null | wc -l)
    if (( count > MAX_BACKUPS )); then
        local to_delete=$(( count - MAX_BACKUPS ))
        ls -1d "$BACKUP_ROOT"/2* | head -n "$to_delete" | while read -r d; do
            rm -rf "$d"
            log "  Pruned old backup: $d"
        done
    fi
}

# ---------------------------------------------------------------------------
# Rollback to latest backup (standalone mode)
# ---------------------------------------------------------------------------
do_rollback() {
    local latest
    latest=$(ls -1d "$BACKUP_ROOT"/2* 2>/dev/null | tail -1)
    [[ -z "$latest" ]] && die "No backups found to roll back to"

    LOG_FILE="$latest/rollback.log"
    log "=== openclaw_apply_config --rollback ==="
    log "Restoring from: $latest"

    # Read the corresponding applied manifest to know which services to restart
    local ts_name
    ts_name=$(basename "$latest")
    local applied_manifest="$APPLIED_ROOT/$ts_name/manifest.json"
    local services=()

    if [[ -f "$applied_manifest" ]]; then
        local num_changes
        num_changes=$(python3 -c "import json; m=json.load(open('$applied_manifest')); print(len(m.get('changes',[])))" 2>/dev/null) || num_changes=0
        for (( i=0; i<num_changes; i++ )); do
            local restart
            restart=$(python3 -c "import json; m=json.load(open('$applied_manifest')); print(m['changes'][$i].get('restart',''))" 2>/dev/null) || true
            [[ -n "$restart" ]] && services+=("$restart")
        done
    fi

    rollback "$latest" "${services[@]}"

    log "=== Rollback complete ==="
    echo '{"ok":true,"rolled_back_from":"'"$latest"'"}'
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    # Handle --rollback mode
    if [[ "${1:-}" == "--rollback" ]]; then
        check_rate_limit
        do_rollback
        exit 0
    fi

    # Validate manifest exists
    [[ -f "$MANIFEST" ]] || die "No manifest found at $MANIFEST"

    # Parse manifest
    local description changes_json health_json services_json
    description=$(python3 -c "import json; m=json.load(open('$MANIFEST')); print(m.get('description','(no description)'))")
    log "=== openclaw_apply_config ==="
    log "Description: $description"

    # Rate limit
    check_rate_limit

    # Setup backup and log
    local ts
    ts=$(date -u +%Y%m%d-%H%M%S)
    local backup_dir="$BACKUP_ROOT/$ts"
    mkdir -p "$backup_dir"
    LOG_FILE="$backup_dir/apply.log"
    log "Backup dir: $backup_dir"

    # Extract changes array
    local num_changes
    num_changes=$(python3 -c "import json; m=json.load(open('$MANIFEST')); print(len(m.get('changes',[])))")
    (( num_changes == 0 )) && die "No changes in manifest"
    log "Changes: $num_changes"

    # Validate all paths before doing anything
    log "--- Validating paths ---"
    local changes=()
    local all_services=()
    for (( i=0; i<num_changes; i++ )); do
        local cj
        cj=$(python3 -c "import json,sys; m=json.load(open('$MANIFEST')); json.dump(m['changes'][$i],sys.stdout)")
        changes+=("$cj")

        local dest
        dest=$(echo "$cj" | python3 -c "import sys,json; print(json.load(sys.stdin)['dest'])")
        is_path_allowed "$dest" || die "Path not whitelisted: $dest"
        log "  OK: $dest"

        local restart
        restart=$(echo "$cj" | python3 -c "import sys,json; print(json.load(sys.stdin).get('restart',''))")
        [[ -n "$restart" ]] && all_services+=("$restart")
    done

    # Extract health checks
    local num_checks
    num_checks=$(python3 -c "import json; m=json.load(open('$MANIFEST')); print(len(m.get('health_checks',[])))")
    local checks=()
    for (( i=0; i<num_checks; i++ )); do
        local hj
        hj=$(python3 -c "import json,sys; m=json.load(open('$MANIFEST')); json.dump(m['health_checks'][$i],sys.stdout)")
        checks+=("$hj")
    done

    # Backup
    log "--- Creating backup ---"
    create_backup "$backup_dir" "${changes[@]}"

    # Apply
    log "--- Applying changes ---"
    apply_changes "${changes[@]}"

    # Restart services
    if (( ${#all_services[@]} > 0 )); then
        log "--- Restarting services ---"
        # Deduplicate
        local unique_services
        unique_services=($(printf '%s\n' "${all_services[@]}" | sort -u))
        restart_services "${unique_services[@]}"
    fi

    # Health checks
    if (( ${#checks[@]} > 0 )); then
        log "--- Running health checks ---"
        if ! run_health_checks "${checks[@]}"; then
            log "!!! HEALTH CHECKS FAILED - ROLLING BACK !!!"
            rollback "$backup_dir" "${all_services[@]}"
            # Archive as failed
            mkdir -p "$APPLIED_ROOT"
            mv "$DESIRED_DIR" "$APPLIED_ROOT/${ts}-FAILED" 2>/dev/null || true
            mkdir -p "$DESIRED_DIR"
            die "Applied but health checks failed. Rolled back to previous state."
        fi
    fi

    log "--- Success ---"

    # Archive applied config
    mkdir -p "$APPLIED_ROOT"
    cp -r "$DESIRED_DIR" "$APPLIED_ROOT/$ts" 2>/dev/null || true

    # Clean desired dir
    rm -f "$DESIRED_DIR"/manifest.json
    find "$DESIRED_DIR" -mindepth 1 -maxdepth 1 -type d -exec rm -rf {} + 2>/dev/null || true

    # Prune old backups
    prune_backups

    log "=== Apply complete ==="
    echo '{"ok":true,"backup":"'"$backup_dir"'","timestamp":"'"$ts"'"}'
}

main "$@"
