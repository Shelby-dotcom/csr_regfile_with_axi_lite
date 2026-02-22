`timescale 1ns/1ns

module axi_top #(
    parameter DATA_W = 32,
    parameter STRB_W = 4,
    parameter ADDR_W = 4,
    parameter TXN_TIMEOUT = 50, // Timeout in clk cycles
    parameter NUM_DATA_REGS = 8,
    parameter logic [NUM_DATA_REGS*2-1:0] DATA_REG_ACCESS = 16'hA500
) (
    input logic clk,
    input logic arst_n,
    // AXI-Lite Interface Signals
    input  logic [ADDR_W-1:0] awaddr,
    input  logic awvalid,
    output logic awready,
    
    input  logic [DATA_W-1:0] wdata,
    input  logic [STRB_W-1:0] wstrb,
    input  logic wvalid,
    output logic wready,
    
    output logic [1:0] bresp,
    output logic bvalid,
    input  logic bready,
    
    input  logic [ADDR_W-1:0] araddr,
    input  logic arvalid,
    output logic arready,
    
    output logic [DATA_W-1:0] rdata,
    output logic [1:0] rresp,
    output logic rvalid,
    input  logic rready
);

// Internal logic

endmodule
