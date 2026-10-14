#!/bin/bash
# Live view of a running AMBER step chain, for the Horus UI.
#
# Horus pulls every file in $HORUS_SIDE_ARTIFACTS_DIR off the cluster every
# ~30 s while a task runs (and once more when it fails or is cancelled), so
# anything written there shows up in the task's side products before the
# task ends. Declared outputs only upload on success. This loop keeps a
# small, viewer-friendly digest of <watch_dir> there:
#
#   current_mdout.log   newest mdout (AMBER errors land here)
#   current_mdinfo.txt  newest mdinfo (ns/day, ETA, current energies)
#   energies.csv        every MD energy record of every mdout so far
#   energies.svg        EPtot / Temp / Density vs. record, step boundaries marked
#   trajectory.pdb      newest .nc, stripped of solvent/H, <= LIVE_FRAMES models (Mol*)
#   rmsd.csv            CA RMSD of those frames vs. their first frame
#
# Usage: live_monitor.sh [--once] <watch_dir> <prmtop>
#        live_monitor.sh --selftest
# Knobs: LIVE_INTERVAL (s, default 60), LIVE_FRAMES (default 50).
# A no-op outside Horus (HORUS_SIDE_ARTIFACTS_DIR unset). Never fails the
# caller: every pass is best-effort and keeps the previous files on error.
set -uo pipefail

# --- mdout -> CSV ---------------------------------------------------------
# Reads mdout files given as args, in order. Only `NSTEP =` MD records are
# taken; minimization tables have no `=` and are skipped, and each file's
# trailing AVERAGES / RMS FLUCTUATIONS blocks are cut off.
mdout_to_csv() {
    awk '
    function val(key,   s) {
        if (match($0, "(^| )" key " *= *[^ ]+")) {
            s = substr($0, RSTART, RLENGTH); sub(/.*= */, "", s); return s
        }
        return ""
    }
    BEGIN { print "step,nstep,time_ps,temp_K,press,etot,eptot,density" }
    FNR == 1 { stop = 0; have = 0; name = FILENAME
               sub(/.*\//, "", name); sub(/\.[^.]*$/, "", name) }
    /A V E R A G E S/ { stop = 1 }
    stop { next }
    /(^| )NSTEP *=/ { nstep = val("NSTEP"); time = val("TIME\\(PS\\)")
                      temp = val("TEMP\\(K\\)"); press = val("PRESS")
                      etot = eptot = density = ""; have = 1 }
    have && / Etot *=/    { etot = val("Etot"); eptot = val("EPtot") }
    have && / Density *=/ { density = val("Density") }
    have && /^ -----/ { print name "," nstep "," time "," temp "," press "," \
                              etot "," eptot "," density; have = 0 }
    ' "$@"
}

# --- CSV -> SVG -----------------------------------------------------------
# Three stacked panels against record index (time resets between steps, so
# index is the honest x axis). Downsampled to <= 2000 points per line.
csv_to_svg() {
    awk -F, '
    NR == 1 { next }
    { n++; step[n] = $1; y[1, n] = $7; y[2, n] = $4; y[3, n] = $8 }
    END {
        W = 900; H = 170; L = 70; R = 20; T = 24; B = 20
        split("EPtot (kcal/mol),Temp (K),Density (g/cc)", title, ",")
        split("#2563eb,#dc2626,#059669", color, ",")
        print "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"" W "\" height=\"" 3 * H "\" font-family=\"sans-serif\" font-size=\"11\">"
        print "<rect width=\"100%\" height=\"100%\" fill=\"#fff\"/>"
        if (n == 0) { print "<text x=\"20\" y=\"30\">No MD energy records yet</text></svg>"; exit }
        every = int((n + 1999) / 2000)
        for (p = 1; p <= 3; p++) {
            top = (p - 1) * H; lo = ""; hi = ""
            for (i = 1; i <= n; i++) if (y[p, i] ~ /^-?[0-9.]+$/) {
                v = y[p, i] + 0
                if (lo == "" || v < lo) lo = v
                if (hi == "" || v > hi) hi = v
            }
            printf "<text x=\"%d\" y=\"%d\" font-weight=\"bold\">%s</text>\n", L, top + 15, title[p]
            if (lo == "") { printf "<text x=\"%d\" y=\"%d\" fill=\"#888\">no data</text>\n", L, top + 60; continue }
            if (hi == lo) { hi = lo + 1 }
            pw = W - L - R; ph = H - T - B
            printf "<rect x=\"%d\" y=\"%d\" width=\"%d\" height=\"%d\" fill=\"none\" stroke=\"#ccc\"/>\n", L, top + T, pw, ph
            printf "<text x=\"%d\" y=\"%d\" text-anchor=\"end\">%.4g</text>\n", L - 4, top + T + 10, hi
            printf "<text x=\"%d\" y=\"%d\" text-anchor=\"end\">%.4g</text>\n", L - 4, top + T + ph, lo
            for (i = 2; i <= n; i++) if (step[i] != step[i - 1]) {
                x = L + (i - 1) / (n > 1 ? n - 1 : 1) * pw
                printf "<line x1=\"%.1f\" y1=\"%d\" x2=\"%.1f\" y2=\"%d\" stroke=\"#bbb\" stroke-dasharray=\"3,3\"/>\n", x, top + T, x, top + T + ph
                if (p == 1) printf "<text x=\"%.1f\" y=\"%d\" fill=\"#666\">%s</text>\n", x + 2, top + T + 10, step[i]
            }
            if (p == 1) printf "<text x=\"%d\" y=\"%d\" fill=\"#666\">%s</text>\n", L + 2, top + T + 10, step[1]
            printf "<polyline fill=\"none\" stroke=\"%s\" stroke-width=\"1.2\" points=\"", color[p]
            for (i = 1; i <= n; i++) if ((i % every == 0 || i == n) && y[p, i] ~ /^-?[0-9.]+$/)
                printf "%.1f,%.1f ", L + (i - 1) / (n > 1 ? n - 1 : 1) * pw, top + T + (hi - y[p, i]) / (hi - lo) * ph
            print "\"/>"
        }
        print "</svg>"
    }' "$1"
}

# --- one pass ---------------------------------------------------------------
newest() { ls -t "$@" 2>/dev/null | head -n 1; }

one_pass() {
    local watch="$1" prmtop="$2" side="$3" tmp f nc n stride
    # Built beside (not inside) the side dir, then mv'd in: same filesystem,
    # so the collector never reads a half-written file and never sees tmp.
    tmp=$(mktemp -d "$(dirname "$side")/.live_monitor.XXXXXX") || return 0

    f=$(newest "$watch"/*.out "$watch"/*.mdout)
    [ -n "$f" ] && cp "$f" "$tmp/current_mdout.log"
    f=$(newest "$watch"/*.info "$watch"/*.mdinf "$watch"/*.mdinfo)
    [ -n "$f" ] && cp "$f" "$tmp/current_mdinfo.txt"

    # mdout files oldest-first so the CSV reads in run order.
    # shellcheck disable=SC2046
    set -- $(ls -tr "$watch"/*.out "$watch"/*.mdout 2>/dev/null)
    if [ $# -gt 0 ] && mdout_to_csv "$@" > "$tmp/energies.csv"; then
        csv_to_svg "$tmp/energies.csv" > "$tmp/energies.svg" || rm -f "$tmp/energies.svg"
    else
        rm -f "$tmp/energies.csv"
    fi

    nc=$(newest "$watch"/*.nc)
    if [ -n "$nc" ] && [ -s "$nc" ] && command -v cpptraj >/dev/null; then
        cp "$nc" "$tmp/cur.nc"
        n=$(cpptraj -p "$prmtop" -y "$tmp/cur.nc" -tl 2>/dev/null | awk '/Frames:/ {print $2}')
        if [ "${n:-0}" -gt 0 ] 2>/dev/null; then
            stride=$(( (n + ${LIVE_FRAMES:-50} - 1) / ${LIVE_FRAMES:-50} ))
            if cpptraj > "$tmp/cpptraj.log" 2>&1 <<EOF
parm $prmtop
trajin $tmp/cur.nc 1 last $stride
autoimage
strip :WAT,HOH,Na+,Cl-,K+
strip @H=
rms first @CA out $tmp/rmsd.dat
trajout $tmp/trajectory.pdb pdb model
run
EOF
            then
                [ -f "$tmp/rmsd.dat" ] && awk -v s="$stride" -v src="$(basename "$nc")" \
                    'NR == 1 { print "source,frame,rmsd_A"; next } { print src "," ($1 - 1) * s + 1 "," $2 }' \
                    "$tmp/rmsd.dat" > "$tmp/rmsd.csv"
            else
                rm -f "$tmp/trajectory.pdb"   # keep the last good one
            fi
        fi
        rm -f "$tmp/cur.nc" "$tmp/rmsd.dat" "$tmp/cpptraj.log"
    fi

    for f in "$tmp"/*; do [ -s "$f" ] && mv -f "$f" "$side/"; done
    rm -rf "$tmp"
}

# --- self-check -------------------------------------------------------------
selftest() {
    local d; d=$(mktemp -d)
    cat > "$d/3_npt.out" <<'EOF'
   NSTEP       ENERGY          RMS            GMAX         NAME    NUMBER
      1      -2.0611E+04     1.3301E+01     1.2412E+02     O       12

 NSTEP =      500   TIME(PS) =       1.000  TEMP(K) =   299.50  PRESS =   -12.3
 Etot   =    -43210.1234  EKtot   =     11000.0000  EPtot      =    -54210.1234
 Density    =         1.0123
 ------------------------------------------------------------------------------

 NSTEP =     1000   TIME(PS) =       2.000  TEMP(K) =   300.10  PRESS =     5.0
 Etot   =    -43200.0000  EKtot   =     11010.0000  EPtot      =-154210.1234
 Density    =         1.0130
 ------------------------------------------------------------------------------

      A V E R A G E S   O V E R       2 S T E P S

 NSTEP =     1000   TIME(PS) =       2.000  TEMP(K) =   299.80  PRESS =    -3.6
 Etot   =    -43205.0000  EKtot   =     11005.0000  EPtot      =    -54210.0000
 ------------------------------------------------------------------------------
EOF
    mdout_to_csv "$d/3_npt.out" > "$d/e.csv"
    [ "$(wc -l < "$d/e.csv" | tr -d ' ')" = 3 ] || { cat "$d/e.csv"; echo "FAIL: row count"; exit 1; }
    [ "$(sed -n 2p "$d/e.csv")" = "3_npt,500,1.000,299.50,-12.3,-43210.1234,-54210.1234,1.0123" ] \
        || { cat "$d/e.csv"; echo "FAIL: row 1"; exit 1; }
    [ "$(sed -n 3p "$d/e.csv" | cut -d, -f7)" = "-154210.1234" ] || { echo "FAIL: '=' glued value"; exit 1; }
    csv_to_svg "$d/e.csv" | grep -q '<polyline' || { echo "FAIL: svg"; exit 1; }
    rm -rf "$d"
    echo "live_monitor.sh: self-check OK"
}

# --- main -------------------------------------------------------------------
[ "${1:-}" = "--selftest" ] && { selftest; exit 0; }
once=0; [ "${1:-}" = "--once" ] && { once=1; shift; }
watch="$1"; prmtop="$2"
side="${HORUS_SIDE_ARTIFACTS_DIR:-}"
[ -n "$side" ] && mkdir -p "$side" || exit 0

if [ "$once" = 1 ]; then one_pass "$watch" "$prmtop" "$side"; exit 0; fi
trap 'exit 0' TERM   # deferred until the current cpptraj returns, so tmp is cleaned
while :; do
    one_pass "$watch" "$prmtop" "$side"
    sleep "${LIVE_INTERVAL:-60}" & wait $!
done
