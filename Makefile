# Project 05 - STA / timing closure
# Targets:
#   make all      - synth + STA sweep + functional check (via run.sh)
#   make sta      - STA/timing-closure sweep on a single netlist
#   make addchain - synth add_chain at given STAGES/K
#   make clean    - remove yosys outputs

YOSYS ?= yosys
PY    ?= python3
STAGES ?= 1
K      ?= 8

NETLIST = /tmp/addchain_$(STAGES).json

all:
	./run.sh

addchain:
	$(YOSYS) -q -p "read -sv src/add_chain.sv; hierarchy -top add_chain; \
	chparam -set STAGES $(STAGES) add_chain; chparam -set K $(K) add_chain; \
	synth -top add_chain; write_json $(NETLIST)"

mac16:
	$(YOSYS) -q -p "read -sv src/mac16.sv; synth -top mac16; \
	write_json /tmp/mac16.json"
	$(YOSYS) -q -p "read -sv src/mac16_pipelined.sv; \
	synth -top mac16_pipelined; write_json /tmp/mac16p.json"

sta: addchain
	$(PY) sta.py --json $(NETLIST) --sweep

clean:
	rm -f /tmp/addchain_*.json /tmp/mac16*.json
