#!/bin/bash
# Count core agent lines (excluding channels/, cli/, providers/ adapters)
cd "$(dirname "$0")" || exit 1

echo "nanobot core agent line count"
echo "================================"
echo ""

# Core directories (including new memory and security modules)
core_dirs=(
    "agent:Agent loop, tools, routing"
    "memory:Memory system (TurboMemoryStore, embeddings, etc.)"
    "security:Security scanner and skill verification"
    "bus:Message bus"
    "config:Configuration system"
    "cron:Scheduled tasks"
    "heartbeat:Proactive wake-up"
    "session:Session management"
    "utils:Utilities"
)

total_lines=0

for dir_info in "${core_dirs[@]}"; do
    dir="${dir_info%%:*}"
    desc="${dir_info##*:}"
    if [ -d "nanobot/$dir" ]; then
        count=$(find "nanobot/$dir" -name "*.py" -exec cat {} + 2>/dev/null | wc -l)
        printf "  %-16s %5s lines  # %s\n" "$dir/" "$count" "$desc"
        total_lines=$((total_lines + count))
    fi
done

# Root files
root_count=$(cat nanobot/__init__.py nanobot/__main__.py 2>/dev/null | wc -l)
printf "  %-16s %5s lines  # Package root\n" "(root)" "$root_count"
total_lines=$((total_lines + root_count))

echo ""
printf "  %-16s %5s lines\n" "Core total:" "$total_lines"
echo ""
echo "  (excludes: channels/, cli/, providers/, bridge/, skills/, tests/)"
