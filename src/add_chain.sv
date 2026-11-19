// Cascaded-combinational-chain design with explicit retiming.
//
// Demonstrates STA-driven timing closure: a combinational ripple of K
// 16-bit adds (each with a *distinct* operand, so synthesis cannot fold
// them) is the critical path. Retiming (registering between blocks) cuts
// the per-clock combinational depth ~K/STAGES, so the closing period drops
// roughly linearly with STAGES.
//
// Usage (see Makefile):
//   make addchain STAGES=1 K=8   -> one-cycle 8-add chain  (baseline)
//   make addchain STAGES=2 K=8   -> retimed, ~4 adds per cycle
//   make addchain STAGES=4 K=8   -> ~2 adds per cycle
//   make addchain STAGES=8 K=8   -> ~1 add per cycle
//   python3 sta.py --json /tmp/addchain.json --sweep
module add_chain #(
    parameter int W     = 16,
    parameter int K     = 8,        // number of chained adds
    parameter int STAGES = 1        // register boundaries inserted
) (
    input  logic               clk,
    input  logic               rst_n,
    input  logic               en,
    input  logic [W-1:0]       x,
    input  logic [K-1:0][W-1:0] d,   // one distinct operand per stage
    output logic [W-1:0]       out
);
    localparam int NBLK  = STAGES > 0 ? STAGES : 1;   // number of blocks
    localparam int SEG   = K / NBLK;                  // adds per block
    localparam int REMAIN = K - SEG * NBLK;           // leftover adds
    localparam int LAST_SEG = SEG + REMAIN;

    // registered output of each block; block gb's input comes from the
    // *register* blk_sum[gb-1] (not the combinational wire), so each clock
    // only sees ~SEG adds of combinational logic -> retiming works.
    logic [W-1:0] blk_sum [NBLK];

    genvar gb, ga;
    generate
        for (gb = 0; gb < NBLK; gb = gb + 1) begin : g_block
            localparam int NADD = (gb == NBLK-1) ? LAST_SEG : SEG;
            localparam int BASE = gb * SEG;           // first stage index
            wire [W-1:0] st [NADD+1];
            assign st[0] = (gb == 0) ? x : blk_sum[gb-1];
            for (ga = 0; ga < NADD; ga = ga + 1) begin : g_add
                assign st[ga+1] = st[ga] + d[BASE+ga];
            end
            always_ff @(posedge clk or negedge rst_n) begin
                if (!rst_n) blk_sum[gb] <= '0;
                else if (en)    blk_sum[gb] <= st[NADD];
            end
        end
    endgenerate

    assign out = blk_sum[NBLK-1];
endmodule
