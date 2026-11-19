#!/bin/bash
# M1-native runner: synth -> cocotb functional check -> STA -> timing closure.
# Usage: ./run.sh   (sweeps STAGES=1,2,4,8 for the add_chain demo)
set -euo pipefail
cd "$(dirname "$0")"
# Optional venv ($HW_VENV, default /tmp/hw-portfolio-venv); otherwise any python with cocotb installed.
VENV="${HW_VENV:-/tmp/hw-portfolio-venv}"
export PATH="$VENV/bin:$PATH"
command -v cocotb-config >/dev/null || { echo "error: cocotb not found - run: pip install -r requirements.txt"; exit 1; }
export PYTHONPATH="$(pwd)"
export COCOTB_RESULTS_FILE="$(mktemp -d /tmp/cocotb_results.XXXXXX)/results.xml"

echo "== 1. Synthesize MAC16 and add_chain to gate-level netlists =="
for S in 1 2 4 8; do
  yosys -q -p "read -sv src/add_chain.sv; hierarchy -top add_chain; chparam -set STAGES $S add_chain; synth -top add_chain; write_json /tmp/addchain_$S.json"
done
yosys -q -p "read -sv src/mac16.sv; synth -top mac16; write_json /tmp/mac16.json"
yosys -q -p "read -sv src/mac16_pipelined.sv; synth -top mac16_pipelined; write_json /tmp/mac16p.json"

echo
echo "== 2. STA / timing-closure sweep on synthesized netlists =="
python3 sta.py --json /tmp/mac16.json --sweep
python3 sta.py --json /tmp/addchain_1.json --sweep

echo
echo "== 3. Functional check of retimed add_chain (cocotb + Verilator) =="
TMP="$(mktemp -d /tmp/sta_sim.XXXXXX)"
cp -r src "$TMP/"
cp tb/test_add_chain.py "$TMP/"
cat > "$TMP/Makefile" << 'EOF'
SIM ?= verilator
TOPLEVEL_LANG ?= verilog
VERILOG_SOURCES = $(CURDIR)/src/*.sv
TOPLEVEL = add_chain
MODULE = test_add_chain
PYTHONPATH = $(CURDIR)
EXTRA_ARGS += --timing -Wno-fatal -Wno-DECLFILENAME
include $(shell cocotb-config --makefiles)/Makefile.sim
EOF
(cd "$TMP" && make sim) \
  > "$TMP/sim.log" 2>&1 || { tail -40 "$TMP/sim.log"; exit 1; }
grep -E "PASSED|FAILED|TESTS=" "$TMP/sim.log" | tail -4
