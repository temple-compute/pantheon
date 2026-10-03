# Test double for env/amber.sh (see README "Verification without AMBER").
#
# Materializes fake pmemd/pmemd.cuda executables into a fixed temp bin dir
# and puts it on PATH, instead of loading a real AMBER module, so the whole
# replica DAG (fan-out, per-step chaining, gather) can be exercised with no
# AMBER installed. Written as files (not shell functions: task commands run
# under plain `/bin/sh`, which rejects a function named `pmemd.cuda` -- the
# dot is not a valid identifier character there) to a fixed location (not
# relative to this file: it is copied into every replica slot, so `$0`
# would point at the copy, not this file's original directory) so PATH
# resolves it regardless of where this script was sourced from or by which
# shell. Idempotent: safe to source repeatedly/concurrently.
#
# Parses just enough of the real pmemd/pmemd.cuda CLI (-o/-r/-x/-inf) to
# touch the declared output files; every other flag is ignored.

_stub_bin="${TMPDIR:-/tmp}/horus-w04-cmd-amber-stub/bin"
mkdir -p "$_stub_bin"

cat > "$_stub_bin/pmemd" <<'PMEMD_STUB'
#!/bin/sh
out=""; rst=""; nc=""; inf=""
while [ $# -gt 0 ]; do
  case "$1" in
    -o) out="$2"; shift 2 ;;
    -r) rst="$2"; shift 2 ;;
    -x) nc="$2"; shift 2 ;;
    -inf) inf="$2"; shift 2 ;;
    -O) shift 1 ;;
    -i|-p|-c|-ref) shift 2 ;;
    *) shift 1 ;;
  esac
done
for f in "$out" "$rst" "$nc" "$inf"; do
  [ -n "$f" ] && : > "$f"
done
echo "stub pmemd: wrote ${rst:-<none>}"
PMEMD_STUB
chmod +x "$_stub_bin/pmemd"
cp "$_stub_bin/pmemd" "$_stub_bin/pmemd.cuda"

export PATH="$_stub_bin:$PATH"
unset _stub_bin
