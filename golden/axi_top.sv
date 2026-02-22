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
    // Signals

    typedef enum logic [1:0] { 
        IDLE=2'b00,
        READ=2'b01
    } rd_st_t;

    logic [DATA_W-1:0] reg_wdata, reg_rdata;
    logic [ADDR_W-1:0] reg_addr;
    logic reg_write, reg_read;
    rd_st_t rd_state;
    logic [DATA_W-1:0] wdata_with_strb, wdata_no_strb;
    logic [STRB_W-1:0] reg_wstrb;
    logic aw_done, w_val;
    logic [1:0] access_violation;
    logic       reg_wr_done;
    logic       reg_rd_done;
    // Timeout counters
    logic [$clog2(TXN_TIMEOUT+1)-1:0] write_timer;
    logic [$clog2(TXN_TIMEOUT+1)-1:0] read_timer;

    //--------------------------------
    // Register File
    //--------------------------------

    csr_regfile #(
        .REG_DW (DATA_W),
        .REG_AW (ADDR_W),
        .DATA_REG_ACCESS(DATA_REG_ACCESS)
    ) u_regfile (
        .clk       (clk),
        .arst_n    (arst_n),
        .reg_wdata (reg_wdata),
        .reg_addr  (reg_addr),
        .reg_write (reg_write),
        .reg_read  (reg_read),
        .reg_rdata (reg_rdata),
        .access_violation (access_violation)
    );

    // AW, W and B Channel Handshakes
    always_ff @(posedge clk or negedge arst_n) begin
        if (!arst_n) begin
            awready <= 1'b1;
            wready <= 1'b1;
            write_timer  <= 0;
        end
        else begin
            if (awvalid || wvalid) begin
                if (write_timer < TXN_TIMEOUT)
                    write_timer <= write_timer + 1;
                else begin
                    // Timeout reached: trigger error response
                    bresp    <= 2'b10; // SLVERR
                    bvalid   <= 1'b1;
                    // Reset handshake signals to recover
                    awready  <= 1'b1;
                    wready   <= 1'b1;
                    write_timer <= 0;
                end
            end
            else begin
                write_timer <= 0;
            end

            if (awvalid && awready) begin
                awready <= 1'b0;
            end

            if (wvalid && wready) begin
                wready <= 1'b0;
            end
            else if (bvalid && bready) begin
                reg_wr_done <= 1'b0;
                wready <= 1'b1;
                awready <= 1'b1;
            end
        end
    end
    // Strobe handling
    always_comb begin
        wdata_with_strb = reg_rdata;
        for (int i = 0; i < STRB_W; i++) begin
            if (reg_wstrb[i]) begin
                wdata_with_strb[(i*8) +: 8] = wdata_no_strb[(i*8) +: 8];
            end
        end
    end

    always_ff @(posedge clk or negedge arst_n) begin
        if (!arst_n) begin
            rd_state      <= IDLE;
            arready       <= 1'b1;
            rvalid        <= 'd0;
            rdata         <= 'd0;
            rresp         <= 'd0;
            awready       <= 1'b1;
            wready        <= 1'b1;
            bresp         <= 2'b00;
            bvalid        <= 1'b0;
            reg_addr      <= 'd0;
            reg_wdata     <= 'd0;
            reg_write     <= 'd0;
            reg_read      <= 'd0;
            wdata_no_strb <= 'd0;
            reg_wstrb     <= 'd0;
            aw_done       <= 0;
            w_val         <= 0;
            read_timer    <= 0;
            reg_wr_done   <= 1'b0;
            reg_rd_done   <= 1'b0;
        end 
        else begin           
            // Write address handling
            if (awvalid && awready) begin
                reg_addr <= awaddr;
                bresp <= 2'b00; // OKAY
                aw_done <= 1;
            end
            else
            begin
                aw_done <= 0;
            end

           // Handle write data
            if (wvalid && wready) begin
                wdata_no_strb <= wdata;
                reg_wstrb     <= wstrb;
                w_val         <= 1;
            end

            if (aw_done & w_val) begin
                reg_wdata <= wdata_with_strb;
                reg_write <= 1;
            end

            if(reg_write)
            begin
                reg_wr_done <= 1'b1;
                if (access_violation == 2'b01 || access_violation == 2'b11)
                    bresp <= 2'b10; // SLVERR
                else
                    bresp <= 2'b00; // OKAY
                
                if(reg_wr_done)
                begin
                    reg_write <= 1'b0;
                    bvalid <= 1'b1;
                end
            end

            // Clear bvalid when handshake completes
            if (bvalid && bready) begin
                bvalid <= 1'b0;
            end

            // Timeout counter update for read transactions
            if (arvalid || (rd_state == READ)) begin
                if (read_timer < TXN_TIMEOUT)
                    read_timer <= read_timer + 1;
                else begin
                    // Timeout reached: trigger error response for read channel
                    rresp      <= 2'b10; // SLVERR
                    rvalid     <= 1'b1;
                    arready    <= 1'b1;
                    rd_state   <= IDLE;
                    read_timer <= 0;
                end
            end
            else begin
                read_timer <= 0;
            end

            // Read Address/Data Handling
            case (rd_state)
                IDLE: begin
                    if (arvalid && arready) begin
                        reg_addr <= araddr;
                        rvalid   <= 1'b0;
                        rresp    <= 2'b00;
                        rd_state <= READ;
                        reg_read <= 1'b1;
                        arready  <= 1'b0;
                    end
                end

                READ: begin
                    reg_rd_done <= 1'b1;
                    if(reg_rd_done)
                        rvalid <= 1'b1;
                    rdata <= reg_rdata;

                    if ((access_violation == 2'b10 || access_violation == 2'b11) && (read_timer < TXN_TIMEOUT) )
                        rresp <= 2'b10; // SLVERR

                    if (rvalid && rready) begin
                        reg_rd_done <= 1'b0;
                        rvalid   <= 1'b0;
                        arready  <= 1'b1;
                        reg_read <= 1'b0;
                        rd_state <= IDLE;
                    end
                end
                default: rd_state <= IDLE;
            endcase
        end
    end
    
endmodule
