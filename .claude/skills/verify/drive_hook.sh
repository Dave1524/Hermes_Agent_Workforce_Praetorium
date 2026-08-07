#!/usr/bin/env bash
# Drive a unit's delivery hook exactly as systemd would: same binary, the same
# Environment= block read back off the INSTALLED unit, same empty ambient env.
# Extra KEY=VALUE overrides may follow the unit name.
set -uo pipefail
unit="$1"; shift
hook=$(systemctl show "$unit" -p ExecStartPost --value | sed -n 's/.*path=\([^ ;]*\).*/\1/p' | head -1)
[ -n "$hook" ] || hook=$(systemctl show "$unit" -p ExecStopPost --value | sed -n 's/.*path=\([^ ;]*\).*/\1/p' | head -1)
mapfile -t envs < <(systemctl show "$unit" -p Environment --value | python3 -c 'import shlex,sys; [print(t) for t in shlex.split(sys.stdin.read())]')
echo "### unit=$unit  hook=$hook"
printf '### env: %s\n' "${envs[@]}"
env -i HOME=/home/dave USER=dave LOGNAME=dave \
    PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    "${envs[@]}" "$@" "$hook"
echo "### hook exit=$?"
