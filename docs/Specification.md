# CSR Register File with AXI4-Lite Slave

A parameterized SystemVerilog AXI4-Lite slave that bridges AXI-Lite reads/writes into an internal `csr_regfile` module. The design supports byte-lane writes, enforces access permissions via the register file, and returns AXI responses.

---

## Global Requirements
- **No X optimism**: outputs must be fully defined on reset.
- **SystemVerilog**: use `logic`, `always_ff`, `always_comb` appropriately.
- **Synthesizable**: no DPI, no delays, no $display in the design.

---

## AXI4-Lite Interface (axi_top.sv)

### Module name
`module axi_top #(...params...) ( ...ports... );`

### Parameters
| Parameter         | Default                  | Notes                                        |
|-------------------|--------------------------|----------------------------------------------|
| `DATA_W`          | 32                       | AXI data width.                              |
| `ADDR_W`          | 8                        | Width of `awaddr/araddr` register index.     |
| `STRB_W`          | `DATA_W/8`               | Strobe width (byte lanes).                   |
| `NUM_DATA_REGS`   | 8                        | Number of data registers.                    |
| `NUM_CSR_REGS`    | 4                        | Number of CSR registers.                     |
| `DATA_REG_ACCESS` | 16'hA500                 | Packed 2-bit access field per data register. |



### Ports
Inputs:

| Signal Name | Description                                                       |
|-------------|-------------------------------------------------------------------|
| `clk`       | Global clock signal (rising-edge triggered).                      |
| `arst_n`    | Active-low asynchronous reset.                                    |
| `awaddr`    | Write address for the AXI transaction.                            |
| `awvalid`   | Indicates that the write address is valid.                        |
| `wdata`     | Write data for the AXI transaction.                               |
| `wstrb`     | Write strobe (byte enables) for the write data.                   |
| `wvalid`    | Indicates that the write data is valid.                           |
| `bready`    | Indicates that the master is ready to receive the write response. |
| `araddr`    | Read address for the AXI transaction.                             |
| `arvalid`   | Indicates that the read address is valid.                         |
| `rready`    | Indicates that the master is ready to receive the read data.      |


Outputs:

| Signal Name | Description                                                          |
|-------------|----------------------------------------------------------------------|
| `awready`   | Indicates that the module is ready to accept the write address.      |
| `wready`    | Indicates that the module is ready to accept the write data.         |
| `bresp`     | Write response (`OKAY = 0`, `SLVERR = 2`) for the AXI write channel. |
| `bvalid`    | Indicates that the write response is valid.                          |
| `arready`   | Indicates that the module is ready to accept the read address.       |
| `rdata`     | Read data output from the register file for the AXI read channel.    |
| `rresp`     | Read response (`OKAY = 0`, `SLVERR = 2`) for the AXI read channel.   |
| `rvalid`    | Indicates that the read data is valid.                               |

### AXI-Lite write behavior
- AW and W channels may arrive in any order and may be backpressured independently.
- The slave must accept **exactly one write transaction at a time**.
- The write transaction completes when:
  - one AW handshake has occurred
  - one W handshake has occurred.
- After completion, the slave must:
  - perform the write into the addressed register and handle the byte enables
  - Give a proper write response and keep it stable until handshake.

Byte enables:
- `wstrb` is **byte enables** (one bit per byte lane).
- For **partial writes** (`wstrb` not all 1s), the slave must implement **read-modify-write** semantics:
  - start with the current addressed register value (the existing contents)
  - for each lane where `wstrb[i] == 1`, replace that byte with `wdata[(i*8)+:8]`
  - for each lane where `wstrb[i] == 0`, **preserve** the existing byte (do not zero it)
- For **full writes** (`wstrb == {STRB_W{1'b1}}`), write `wdata` directly.

Error response on write:
- If address out of range OR write not permitted, respond SLVERR on B channel (and must not modify the register contents).

### AXI-Lite read behavior
- The slave must accept **exactly one read transaction at a time**.
- On AR handshake, capture the address.
- The slave must produce one read response:
  - assert `rvalid`,
  - drive `rdata` and `rresp`,
  - hold them stable until the ready handshake.
-   The read data is fetched from the register file using the provided address. The valid read data and its response are asserted until the master signals readiness via `rready`. After a successful handshake, the module returns to the idle state. A small read state machine should be implemented (`IDLE`/`READ`) to correctly capture this behaviour.

Read latency:
- `rvalid` must not assert in the same cycle as the AR handshake.
- `rvalid` typically asserts after the read data is available (after about 2 cycles).
- For an error read (out of range or read not permitted), `rdata` must be 0 and `rresp` must be `SLVERR` when `rvalid` asserts.

---

## csr_regfile.sv Details

### Module name
`module csr_regfile #(...params...) ( ...ports... );`

### Parameters

| Parameter         | Description                                                                                                                                                   |
|-------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `REG_DW`          | Data width (default is 32 bits).                                                                                                                              |
| `REG_AW`          | Address width (default is 4 bits). This width allows addressing multiple registers; the implemented range depends on `NUM_DATA_REGS` plus the fixed CSR bank. |
| `NUM_DATA_REGS`   | Number of data registers (default is 8 ).                                                                                                                     |
| `DATA_REG_ACCESS` | Packed access permissions for data registers (2 bits per register)                                                                                            |

### Local parameters

Declare a fixed **4-entry CSR bank**:

- `NUM_CSR_REGS = 4`

CSR register map (word offsets):

| CSR     | Offset | Access        |
|---------|--------|---------------|
| mcycle  | 0      | Read Only     |
| mstatus | 1      | Read Write    |
| mcause  | 2      | Read Only     |
| mip     | 3      | Read Only     |

### Ports
| Signal Name | Direction | Width                       | Description                                                                                                                                                          |
|-------------|-----------|-----------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `clk`       | Input     | 1 bit                       | Clock signal used for synchronizing the read and write operations.                                                                                                   |
| `arst_n`    | Input     | 1 bit                       | Active-low asynchronous reset. When low, all registers and output data are cleared to zero.                                                                          |
| `reg_wdata` | Input     | `REG_DW` (default: 32 bits) | Data to be written into the register file during a write operation.                                                                                                  |
| `reg_addr`  | Input     | `REG_AW` (default: 4 bits)  | Address/index input used to select which register to read from or write to (data regs first, then CSR regs, then out-of-range). |
| `reg_write` | Input     | 1 bit                       | Write enable signal. When high, triggers a write operation at the rising edge of the clock.                                                                          |
| `reg_read`  | Input     | 1 bit                       | Read enable signal. When high, triggers a read operation at the rising edge of the clock.                                                                            |
| `reg_rdata` | Output    | `REG_DW` (default: 32 bits) | Data output from the register file corresponding to the selected register indicated by `reg_addr`.                                                                   |
| `access_violation` | Output | 2 bits | Access status: 0=no violation, 1=write violation, 2=read violation, 3=address out of range. |

Required behavior:
- On reset: all registers clear to 0.
- On register write :
  - If address is in range and writable per permissions: update that register with data.
  - Do not modify storage if no write enable.
- On register read:
  - If address is in range and readable per permissions read data with the addressed register value on the next cycle.
  - If no read enable, hold `reg_rdata` stable (do not generate spurious access violations).

## Register Map
The AXI address (`awaddr`/`araddr`) represents a **register index** (word addressing), not a byte address.

Total registers:
- Data regs: indices `[0 .. NUM_DATA_REGS-1]`
- CSR regs:  indices `[NUM_DATA_REGS .. NUM_DATA_REGS+NUM_CSR_REGS-1]`

Any access with `addr_index >= (NUM_DATA_REGS + NUM_CSR_REGS)` must return **SLVERR**.

Data width:
- All registers are `DATA_W` bits wide.
- `WSTRB` is `STRB_W = DATA_W/8` byte enables.

---

## Access Permissions
Each register has a 2-bit access type:
- `2'b00`: RW (read/write allowed)
- `2'b01`: RO (read-only)
- `2'b10`: WO (write-only)
- `2'b11`: reserved (treat as no-access)

Permissions are provided via parameters:
- `DATA_REG_ACCESS`: packed array of 2-bit fields, one per data reg
- `CSR_REG_ACCESS`:  packed array of 2-bit fields, one per CSR reg

Behavior:
- Writing to RO => SLVERR (write response)
- Reading from WO => SLVERR (read response)
- Reserved/no-access => SLVERR

## Deliverables

### 1) `axi_top.sv`
Top-level AXI4-Lite slave that:
- Accepts AXI-Lite read/write transactions.
- Decodes the address to a register index.
- Performs byte-lane writes using WSTRB.
- Returns OKAY/SLVERR responses.
- Instantiates `csr_regfile` through a simple internal read/write interface.

### 2) `csr_regfile.sv`
Register file that:
- Implements `NUM_DATA_REGS` data registers and internal `NUM_CSR_REGS` CSR registers.
- Enforces per-register access permissions (RW/RO/WO).
- Provides synchronous read and synchronous write behavior.
- Indicates access errors.