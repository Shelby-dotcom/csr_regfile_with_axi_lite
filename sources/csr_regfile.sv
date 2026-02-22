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

    // CSR registers access configuration:
    // mcycle: RO (offset 0), mstatus: RW (offset 1), mcause: RO (offset 2), mip: RO (offset 3)
    localparam NUM_CSR_REGS  = 4;
    localparam RW = 2'b00, RO = 2'b01, WO = 2'b10;
    localparam logic [NUM_CSR_REGS*2-1:0] CSR_REG_ACCESS = {2'b01, 2'b00, 2'b01, 2'b01};

    // Data Registers
    reg [REG_DW-1:0] data_registers [0:NUM_DATA_REGS-1];
    // CSR Registers
    reg [REG_DW-1:0] csr_registers  [0:NUM_CSR_REGS-1];

    logic [2:0] csr_index;
    assign csr_index = reg_addr - NUM_DATA_REGS;
    always @(posedge clk or negedge arst_n) begin
        if (!arst_n) begin
            for (int i = 0; i < NUM_DATA_REGS; i = i + 1)
                data_registers[i] <= {REG_DW{1'b0}};
            for (int i = 0; i < NUM_CSR_REGS; i = i + 1)
                csr_registers[i] <= {REG_DW{1'b0}};
            reg_rdata         <= {REG_DW{1'b0}};
            access_violation  <= 2'b00;
        end 
        else begin
            // Default
            access_violation <= 2'b00;

            if (reg_write)
            begin
                if (reg_addr < NUM_DATA_REGS)
                begin
                    if ((DATA_REG_ACCESS[(reg_addr)*2 +: 2] == RW) ||
                        (DATA_REG_ACCESS[(reg_addr)*2 +: 2] == WO))
                        data_registers[reg_addr] <= reg_wdata;
                    else
                        access_violation <= 2'b01;
                end 
                else if (reg_addr < (NUM_DATA_REGS + NUM_CSR_REGS))
                begin
                    // Allow write if CSR is RW or WO
                    if ((CSR_REG_ACCESS[((NUM_CSR_REGS-1)-csr_index)*2 +: 2] == RW) ||
                        (CSR_REG_ACCESS[((NUM_CSR_REGS-1)-csr_index)*2 +: 2] == WO))
                        csr_registers[csr_index] <= reg_wdata;
                    else
                        access_violation <= 2'b01;
                end 
                else
                begin
                    access_violation <= 2'b11;
                end
            end

            if (reg_read)
            begin
                if (reg_addr < NUM_DATA_REGS)
                begin
                    if ((DATA_REG_ACCESS[(reg_addr)*2 +: 2] == RO) ||
                        (DATA_REG_ACCESS[(reg_addr)*2 +: 2] == RW))
                        reg_rdata <= data_registers[reg_addr];
                    else
                        access_violation <= 2'b10;
                end
                else if (reg_addr < (NUM_DATA_REGS + NUM_CSR_REGS))
                begin
                    if (CSR_REG_ACCESS[((NUM_CSR_REGS-1)-csr_index)*2 +: 2] == WO)
                        access_violation <= 2'b10;
                    else
                        reg_rdata <= csr_registers[csr_index];
                end
                else
                begin
                    access_violation <= 2'b11;
                end
            end
        end
    end

endmodule