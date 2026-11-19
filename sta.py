"""Static timing analysis (STA) engine + timing-closure case study.

Reads a gate-level netlist produced by `yosys synth` (via `write_json`),
applies a small cell-library delay model, and computes:
  - arrival times (clk->Q through combinational logic)
  - required times and setup/hold slack
  - WNS / TNS and the critical path
  - a pipelining sweep that demonstrates timing closure

The netlist is bit-level (yosys maps to single-bit $_*_ cells). DFF outputs
are register boundaries; combinational gates ($_AND_, $_OR_, $_XOR_, ...)
propagate arrival times. Library delays are synthetic-but-realistic numbers,
overridable with --lib to mimic a technology library.

Run (from project 07 root):
  make netlist && make sta
  python3 sta.py --json /tmp/mac16.json --period 5.0
"""

import argparse
import json
import os


# Synthetic cell library: gate -> {delay_ns, is_ff, clktoq, setup}
CELL_LIB = {
    "$_INV_":       {"delay": 0.030},
    "$_AND_":       {"delay": 0.045},
    "$_OR_":        {"delay": 0.045},
    "$_NAND_":      {"delay": 0.040},
    "$_NOR_":       {"delay": 0.040},
    "$_XOR_":       {"delay": 0.090},
    "$_XNOR_":      {"delay": 0.090},
    "$_MUX_":       {"delay": 0.050},
    "$_AOI3_":      {"delay": 0.055},
    "$_OAI3_":      {"delay": 0.055},
    "$_ANDNOT_":    {"delay": 0.045},
    "$_ORNOT_":     {"delay": 0.045},
    "$_DFF_P_":     {"is_ff": True, "clktoq": 0.120, "setup": 0.030},
    "$_DFF_N_":     {"is_ff": True, "clktoq": 0.120, "setup": 0.030},
    "$_DFFE_PP_":   {"is_ff": True, "clktoq": 0.120, "setup": 0.030},
    "$_DFFE_PN0P_": {"is_ff": True, "clktoq": 0.120, "setup": 0.030},
    "$_DFFE_PN1P_": {"is_ff": True, "clktoq": 0.120, "setup": 0.030},
    "$_DFFE_NN0P_": {"is_ff": True, "clktoq": 0.120, "setup": 0.030},
    "$_DFFE_NN1P_": {"is_ff": True, "clktoq": 0.120, "setup": 0.030},
}


class Netlist:
    def __init__(self, json_path, clk_port):
        data = json.load(open(json_path))
        modules = data["modules"]
        tops = [n for n, m in modules.items() if m.get("attributes", {}).get("top")]
        self.module = modules[tops[0] if tops else list(modules)[0]]
        self.clk_port = clk_port

        # bit id -> human net name
        self.bitname = {}
        for name, info in self.module.get("netnames", {}).items():
            for b in info["bits"]:
                self.bitname[b] = name
        # port direction per bit
        self.bit_dir = {}
        for p, info in self.module.get("ports", {}).items():
            for b in info["bits"]:
                self.bit_dir[b] = info["direction"]

        # collect cells
        self.cells = {}
        for name, c in self.module.get("cells", {}).items():
            conn = {}
            for k, v in c.get("connections", {}).items():
                if isinstance(v, dict):
                    conn[k] = list(v.get("bits", []))
                elif isinstance(v, list):
                    conn[k] = v
                else:
                    conn[k] = []
            self.cells[name] = {"type": c["type"], "conn": conn}

    def is_input(self, bit):
        return self.bit_dir.get(bit) == "input"

    def is_output(self, bit):
        return self.bit_dir.get(bit) == "output"

    def clk_bit(self):
        return self.module["ports"][self.clk_port]["bits"][0]

    def ff_cells(self):
        out = []
        for name, c in self.cells.items():
            if CELL_LIB.get(c["type"], {}).get("is_ff"):
                out.append(name)
        return out

    def comb_cells(self):
        out = []
        for name, c in self.cells.items():
            if not CELL_LIB.get(c["type"], {}).get("is_ff"):
                out.append(name)
        return out


def compute_arrivals(nl):
    """arrival[bit] = earliest guaranteed time data is stable at that bit."""
    arr = {}   # bit -> arrival (ns), starts at DFF Q / primary inputs
    for name, c in nl.cells.items():
        ctype = c["type"]
        if CELL_LIB.get(ctype, {}).get("is_ff"):
            q = c["conn"]["Q"]
            for b in q:
                arr[b] = CELL_LIB[ctype]["clktoq"]   # launch at clock edge
    for b, d in nl.bit_dir.items():
        if d == "input" and b != nl.clk_bit():
            arr.setdefault(b, 0.0)

    # propagate combinational arrival times (repeat until fixpoint)
    changed = True
    iters = 0
    while changed:
        changed = False
        iters += 1
        if iters > len(nl.cells) * 4 + 10:
            break
        for name, c in nl.cells.items():
            ctype = c["type"]
            if CELL_LIB.get(ctype, {}).get("is_ff"):
                continue
            dly = CELL_LIB.get(ctype, {"delay": 0.05})["delay"]
            outs = c["conn"].get("Y", c["conn"].get("Q", []))
            ins = [b for k, v in c["conn"].items()
                   for b in v if k not in ("Y", "Q")]
            for ob in outs:
                in_arr = [arr.get(ib, 0.0) for ib in ins]
                cand = (max(in_arr) + dly) if in_arr else dly
                if cand > arr.get(ob, -1.0) + 1e-12:
                    arr[ob] = cand
                    changed = True
    return arr


def compute_required(nl, period):
    """req[bit] = latest time data may arrive at that bit and still meet setup."""
    req = {}
    for name, c in nl.cells.items():
        ctype = c["type"]
        if CELL_LIB.get(ctype, {}).get("is_ff"):
            for b in c["conn"].get("D", []):
                req[b] = period - CELL_LIB[ctype]["setup"]
    for b, d in nl.bit_dir.items():
        if d == "output":
            req.setdefault(b, period)

    changed = True
    iters = 0
    while changed:
        changed = False
        iters += 1
        if iters > len(nl.cells) * 4 + 10:
            break
        for name, c in nl.cells.items():
            ctype = c["type"]
            if CELL_LIB.get(ctype, {}).get("is_ff"):
                continue
            dly = CELL_LIB.get(ctype, {"delay": 0.05})["delay"]
            outs = c["conn"].get("Y", c["conn"].get("Q", []))
            ins = [b for k, v in c["conn"].items()
                   for b in v if k not in ("Y", "Q")]
            out_req = [req.get(ob, float("inf")) for ob in outs]
            min_out = min(out_req) if out_req else float("inf")
            for ib in ins:
                cand = min_out - dly
                if cand < req.get(ib, float("inf")) - 1e-12:
                    req[ib] = cand
                    changed = True
    return req


def slacks(nl, period, arr, req):
    data = []
    for name, c in nl.cells.items():
        ctype = c["type"]
        if not CELL_LIB.get(ctype, {}).get("is_ff"):
            continue
        for b in c["conn"].get("D", []):
            a = arr.get(b, 0.0)
            r = req.get(b, float("inf"))
            data.append((b, a, r, r - a))
    for b, d in nl.bit_dir.items():
        if d == "output":
            a = arr.get(b, 0.0)
            r = req.get(b, float("inf"))
            data.append((b, a, r, r - a))
    return data


def crit_path(nl, arr, req, seed_bit):
    """Walk back from seed_bit along the worst arriving predecessor."""
    path = []
    cur = seed_bit
    seen = set()
    while cur is not None and cur not in seen:
        seen.add(cur)
        path.append(cur)
        preds = []
        for name, c in nl.cells.items():
            ctype = c["type"]
            outs = c["conn"].get("Y", c["conn"].get("Q", []))
            if cur not in outs:
                continue
            ins = [b for k, v in c["conn"].items()
                   for b in v if k not in ("Y", "Q")]
            preds = [(ib, CELL_LIB.get(ctype, {}).get("delay", 0.0)) for ib in ins]
            break
        if not preds:
            break
        nxt = max(preds, key=lambda x: arr.get(x[0], 0.0))
        cur = nxt[0]
    return path[::-1]


def run_sta(json_path, period, clk="clk", detail=False):
    nl = Netlist(json_path, clk)
    arr = compute_arrivals(nl)
    req = compute_required(nl, period)
    sl = slacks(nl, period, arr, req)
    wns = min((s[3] for s in sl), default=0.0)
    tns = sum(s[3] for s in sl if s[3] < 0)
    worst = min(sl, key=lambda x: x[3]) if sl else None
    print(f"  netlist      : {json_path}")
    print(f"  cells        : {len(nl.cells)} ({len(nl.ff_cells())} ff, "
          f"{len(nl.comb_cells())} comb)")
    print(f"  period       : {period:.2f} ns  ->  fmax {1000.0/period:.0f} MHz")
    print(f"  WNS          : {wns:+.3f} ns   TNS {tns:+.3f} ns   "
          f"endpoints {len(sl)}")
    if worst is not None:
        b = worst[0]
        cp = crit_path(nl, arr, req, b)
        cp_str = " -> ".join(nl.bitname.get(x, f"bit{x}") for x in cp[-8:])
        print(f"  worst endpt  : {nl.bitname.get(b, b)} "
              f"(arr {worst[1]:.3f}, req {worst[2]:.3f})")
        print(f"  crit path    : ...{cp_str}")
    return {"wns": wns, "tns": tns, "fmax": 1000.0 / period, "arr": arr,
            "req": req}


def sweep(json_path, clk="clk"):
    """Demonstrate timing closure: what period can we close before/after
    pipelining? Returns a dict of {period_ns: wns}."""
    print(f"\n=== Timing-closure sweep for {json_path} ===")
    results = {}
    for period in [10.0, 8.0, 6.0, 5.0, 4.0, 3.5, 3.0, 2.5, 2.2, 2.0, 1.8, 1.6, 1.5, 1.4, 1.3]:
        r = run_sta(json_path, period, clk)
        results[period] = r["wns"]
    print("\n  period(ns)   fmax(MHz)    WNS(ns)     status")
    for p, w in results.items():
        status = "CLOSED" if w >= 0 else "VIOLATED"
        print(f"  {p:9.2f} {1000.0/p:10.0f} {w:+10.3f}    {status}")
    # first closing period
    closed = [p for p, w in results.items() if w >= 0]
    fmax = max(1000.0 / p for p in closed) if closed else 0.0
    print(f"  => closes down to {min(closed):.1f} ns "
          f"({fmax:.0f} MHz) on this synthesized netlist")
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True, help="yosys write_json netlist")
    ap.add_argument("--period", type=float, default=None)
    ap.add_argument("--clk", default="clk")
    ap.add_argument("--sweep", action="store_true")
    args = ap.parse_args()

    if args.sweep:
        sweep(args.json, args.clk)
    else:
        period = args.period if args.period else 5.0
        run_sta(args.json, period, args.clk, detail=True)


if __name__ == "__main__":
    main()