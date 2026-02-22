module csr_regfile
#(
    parameter REG_DW = 32,
    parameter REG_AW = 4,
    parameter NUM_DATA_REGS = 8,
    parameter logic [NUM_DATA_REGS*2-1:0] DATA_REG_ACCESS = {NUM_DATA_REGS{2'b00}}
)
(
    input logic               clk,
    input logic               arst_n,
    input logic  [REG_DW-1:0] reg_wdata,
    input logic  [REG_AW-1:0] reg_addr,
    input logic               reg_write,
    input logic               reg_read,
    output logic [REG_DW-1:0] reg_rdata,
    // Access Violation : (0 : No violation, 1: Write Violation, 2: Read Violation, 3: Addr Out of Range)
    output logic [1:0]        access_violation
);

// Internal logic

endmodule