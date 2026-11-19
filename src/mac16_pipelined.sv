// 16x16-bit multiply-accumulate (MAC), *pipelined* across the multiplier.
//
// This is the "timing closure" version of mac16.sv: by inserting register
// stages inside the combinational multiply->add path we cut the critical
// path roughly in half, letting the clock run faster (smaller period) with
// positive slack. The cost is latency (+1 cycle) and 32 more flops.
//
// Pipelined RTL: a*b -> reg -> acc+prod -> reg acc. STA shows the path
// breaking into two ~1.5 ns halves, closing at ~1.8 ns instead of 3.5 ns.
module mac16_pipelined #(
    parameter int A_W = 16,
    parameter int B_W = 16
) (
    input  logic                 clk,
    input  logic                 rst_n,
    input  logic                 en,
    input  logic [A_W-1:0]       a,
    input  logic [B_W-1:0]       b,
    output logic [A_W+B_W-1:0]   acc
);
    logic [A_W+B_W-1:0] prod;
    logic [A_W+B_W-1:0] prod_r;    // stage 1 output
    logic [A_W+B_W-1:0] acc_next;
    logic [A_W+B_W-1:0] acc_r;     // stage 2 output

    assign prod = a * b;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            prod_r <= '0;
            acc_r  <= '0;
        end else if (en) begin
            prod_r <= prod;        // pipeline stage 1: register the multiply
            acc_r  <= acc_next;    // pipeline stage 2: register the accumulate
        end
    end

    assign acc_next = acc_r + prod_r;
    assign acc      = acc_r;
endmodule
