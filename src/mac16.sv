// 16x16-bit multiply-accumulate (MAC) with a real combinational critical
// path (the multiplier tree). Used by project 07 to demonstrate STA and
// timing closure via pipelining.
module mac16 #(
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
    logic [A_W+B_W-1:0] acc_next;

    // Unsigned combinational multiply: partial products + adder tree.
    // This is the deep combinational path STA must close.
    assign prod = a * b;
    assign acc_next = acc + prod;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            acc <= '0;
        else if (en)
            acc <= acc_next;
    end
endmodule
