from __future__ import annotations

import os
import random
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
from cocotb_tools.runner import get_runner
import cocotb.simulator

cocotb.simulator.dump_enabled = True

LANGUAGE = os.getenv("HDL_TOPLEVEL_LANG", "verilog").lower().strip()

class AxiLiteDriver:
    def __init__(self, dut, *, clk_period_ns: int = 10):
        self.dut = dut
        self.clk_period_ns = clk_period_ns

    async def init(self) -> None:
        for signal in self.dut:
            if getattr(signal, "_type", None) == "GPI_NET":
                signal.value = 0

    async def write(self, *, data: int, addr: int, strb: int) -> int:
        dut = self.dut
        dut.awaddr.value = addr
        dut.wdata.value = data
        dut.wstrb.value = strb

        delay_cycles = random.randint(1, 10)
        await Timer(delay_cycles * self.clk_period_ns, units="ns")
        dut.bready.value = 1

        while not (int(dut.awready.value) and int(dut.wready.value)):
            await RisingEdge(dut.clk)

        await RisingEdge(dut.clk)
        dut.awvalid.value = 1
        dut.wvalid.value = 1
        await RisingEdge(dut.clk)
        dut.awvalid.value = 0
        dut.wvalid.value = 0
        dut.awaddr.value = 0

        while not int(dut.bvalid.value):
            await RisingEdge(dut.clk)

        bresp = int(dut.bresp.value)
        await RisingEdge(dut.clk)
        dut.bready.value = 0
        return bresp

    async def read(self, *, addr: int) -> tuple[int, int]:
        dut = self.dut
        dut.araddr.value = addr
        dut.arvalid.value = 1

        await RisingEdge(dut.clk)
        while not int(dut.arready.value):
            await RisingEdge(dut.clk)

        dut.araddr.value = 0
        dut.arvalid.value = 0

        delay_cycles = 2
        await Timer(delay_cycles * self.clk_period_ns, units="ns")
        dut.rready.value = 1
        await RisingEdge(dut.clk)

        while not int(dut.rvalid.value):
            await RisingEdge(dut.clk)

        rdata = int(dut.rdata.value)
        rresp = int(dut.rresp.value)
        await RisingEdge(dut.clk)
        dut.rready.value = 0
        return rdata, rresp


def dut_init(dut) -> None:
    return AxiLiteDriver(dut).init()


def axi_write(dut, data, addr, strb):
    return AxiLiteDriver(dut).write(data=data, addr=addr, strb=strb)


def axi_read(dut, rd_addr):
    return AxiLiteDriver(dut).read(addr=rd_addr)

# Define access codes: RW = 0, RO = 1, WO = 2
RW = 0
RO = 1
WO = 2

def get_data_reg_access(dut, index):
    """
    Extract the 2-bit access code for a given index from the packed DATA_REG_ACCESS parameter.
    Assumes that the LSB corresponds to index 0.
    """
    # Convert DATA_REG_ACCESS to integer
    data_access_val = int(dut.DATA_REG_ACCESS.value)
    # Each register is represented by 2 bits.
    return (data_access_val >> (index * 2)) & 0x3

def find_rw_index(dut, num_data_regs):
    """Return the index of the first RW register."""
    for i in range(num_data_regs):
        if get_data_reg_access(dut, i) == RW:
            return i
    return None

def find_ro_index(dut, num_data_regs):
    """Return the index of the first RO register."""
    for i in range(num_data_regs):
        if get_data_reg_access(dut, i) == RO:
            return i
    return None

def find_wo_index(dut, num_data_regs):
    """Return the index of the first WO register."""
    for i in range(num_data_regs):
        if get_data_reg_access(dut, i) == WO:
            return i
    return None

@cocotb.test(timeout_time=500, timeout_unit="ns")
async def test_data_registers_with_axi(dut):
    """
    Test the data register region via the AXI interface.
    This test dynamically searches DATA_REG_ACCESS for a data register configured as RW
    and then performs a write/read transaction on that register.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await dut_init(dut)

    # Apply reset sequence.
    dut.arst_n.value = 0
    await Timer(50, unit="ns")
    dut.arst_n.value = 1
    await RisingEdge(dut.clk)

    NUM_DATA_REGS = int(dut.NUM_DATA_REGS.value)
    rw_idx = None
    for i in range(NUM_DATA_REGS):
        if get_data_reg_access(dut, i) == RW:
            rw_idx = i
            break
    assert rw_idx is not None, "No read-write data register found in DATA_REG_ACCESS"

    dut._log.info(f"Using data register index {rw_idx} for valid data register test.")

    write_value = 0x12345678

    # Write transaction via AXI interface.
    dut.awaddr.value = rw_idx
    dut.awvalid.value = 1
    dut.wdata.value = write_value
    dut.wstrb.value = 0xF  # Enable all bytes
    dut.wvalid.value = 1
    dut.bready.value = 1  # Allow handshake to complete
    await RisingEdge(dut.clk)
    dut.awvalid.value = 0
    dut.wvalid.value = 0
    dut.bready.value = 0
    await RisingEdge(dut.clk)

    # Wait for the write handshake to complete: bvalid should be asserted.
    while int(dut.bvalid.value) == 0:
        await RisingEdge(dut.clk)
    assert int(dut.bvalid.value) == 1, "Write transaction did not complete (bvalid not asserted)"
    # Now check the response.
    assert int(dut.bresp.value) == 0, f"Data register write failed: bresp = {int(dut.bresp.value)}"
    assert int(dut.access_violation.value) == 0, "Unexpected access violation during data register write"


    # Read transaction via AXI interface.
    dut.araddr.value = rw_idx
    dut.arvalid.value = 1
    dut.rready.value = 1
    await RisingEdge(dut.clk)
    dut.arvalid.value = 0
    await RisingEdge(dut.clk)
    dut.rready.value = 0
    await RisingEdge(dut.clk)

    # Verify that the read data matches the written value and that rresp indicates OKAY (0)
    while int(dut.rvalid.value) == 0:
        await RisingEdge(dut.clk)
    # await RisingEdge(dut.clk)
    assert int(dut.rdata.value) == write_value, \
        f"Data register read-back failed, expected 0x{write_value:x}, got 0x{int(dut.rdata.value):x}"
    assert int(dut.rresp.value) == 0, \
        f"Unexpected read response: expected 0, got {int(dut.rresp.value)}"

    dut._log.info("Data registers AXI test passed.")

@cocotb.test(timeout_time=500, timeout_unit="ns")
async def test_csr_registers_with_axi(dut):
    """
    Test the CSR region via the AXI interface.
    Assumes the CSR region starts at address NUM_DATA_REGS and is mapped as follows:
      - mcycle (offset 0): Read-Only (RO)
      - mstatus (offset 1): Read/Write (RW)
      - mcause (offset 2): Read-Only (RO)
      - mip (offset 3): Read-Only (RO)
    
    This test performs two parts:
      1. Write and read mstatus (RW) should succeed.
      2. Write to mcycle (RO) should trigger a write violation.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await dut_init(dut)
    
    # Apply reset sequence.
    dut.arst_n.value = 0
    await Timer(50, units="ns")
    dut.arst_n.value = 1
    await RisingEdge(dut.clk)
    
    NUM_DATA_REGS = int(dut.NUM_DATA_REGS.value)
    # CSR region addresses start at NUM_DATA_REGS.
    mcycle_addr  = NUM_DATA_REGS + 0  # mcycle (RO)
    mstatus_addr = NUM_DATA_REGS + 1  # mstatus (RW)
    
    # Part 1: Write and read mstatus (RW).
    write_value = 0xA5A5A5A5
    # Write transaction to mstatus.
    dut.awaddr.value = mstatus_addr
    dut.awvalid.value = 1
    dut.wdata.value = write_value
    dut.wstrb.value = 0xF
    dut.wvalid.value = 1
    dut.bready.value = 1
    # Wait until bvalid is asserted.
    while int(dut.bvalid.value) == 0:
        await RisingEdge(dut.clk)
    # Check that bresp is OKAY (0).
    assert int(dut.bresp.value) == 0, f"CSR write (mstatus) failed: bresp = {int(dut.bresp.value)}"
    # Clear write signals.
    dut.awvalid.value = 0
    dut.wvalid.value = 0
    dut.bready.value = 0
    await RisingEdge(dut.clk)
    
    # Read transaction from mstatus.
    dut.araddr.value = mstatus_addr
    dut.arvalid.value = 1
    dut.rready.value = 1
    while int(dut.rvalid.value) == 0:
        await RisingEdge(dut.clk)
    # Check that rdata matches the written value and that rresp indicates OKAY (0).
    assert int(dut.rdata.value) == write_value, \
        f"CSR read-back (mstatus) failed, expected 0x{write_value:x}, got 0x{int(dut.rdata.value):x}"
    assert int(dut.rresp.value) == 0, f"Unexpected read response for mstatus, got {int(dut.rresp.value)}"
    # Clear read signals.
    dut.arvalid.value = 0
    dut.rready.value = 0
    await RisingEdge(dut.clk)
    
    # Part 2: Attempt to write to mcycle (RO) to trigger a violation.
    dut.awaddr.value = mcycle_addr
    dut.awvalid.value = 1
    dut.wdata.value = 0xDEADBEEF
    dut.wstrb.value = 0xF
    dut.wvalid.value = 1
    dut.bready.value = 1
    while int(dut.bvalid.value) == 0:
        await RisingEdge(dut.clk)
    # Expect bresp to be SLVERR (assume SLVERR is coded as 2'b10).
    assert int(dut.bresp.value) == 2, f"CSR write violation not flagged for mcycle (RO), bresp = {int(dut.bresp.value)}"
    # Clear write signals.
    dut.awvalid.value = 0
    dut.wvalid.value = 0
    dut.bready.value = 0
    await RisingEdge(dut.clk)
    
    # Reading from mcycle should return the default value (0) since the write was rejected.
    dut.araddr.value = mcycle_addr
    dut.arvalid.value = 1
    dut.rready.value = 1
    while int(dut.rvalid.value) == 0:
        await RisingEdge(dut.clk)
    # Check that rdata is 0 and rresp indicates OKAY (0) because read itself is allowed.
    assert int(dut.rdata.value) == 0, "CSR read (mcycle) did not return default value after write violation"
    assert int(dut.rresp.value) == 0, f"Unexpected read response for mcycle, got {int(dut.rresp.value)}"
    # Clear read signals.
    dut.arvalid.value = 0
    dut.rready.value = 0
    await RisingEdge(dut.clk)
    
    dut._log.info("CSR registers AXI test passed.")

@cocotb.test(timeout_time=500, timeout_unit="ns")
async def test_out_of_range_addr_with_axi(dut):
    """
    Test that accessing an out-of-range address triggers an address violation.
    Out-of-range is defined as reg_addr >= NUM_DATA_REGS + NUM_CSR_REGS.
    The expected behavior:
      - A write transaction to an out-of-range address results in bresp = SLVERR (2).
      - A read transaction from an out-of-range address results in rresp = SLVERR (2)
        and rdata = 0xFFFFFFFF.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await dut_init(dut)
    
    # Apply reset sequence.
    dut.arst_n.value = 0
    await Timer(50, unit="ns")
    dut.arst_n.value = 1
    await RisingEdge(dut.clk)
    
    NUM_DATA_REGS = int(dut.NUM_DATA_REGS.value)
    NUM_CSR_REGS = 4  # As defined in the regfile RTL.
    out_addr = NUM_DATA_REGS + NUM_CSR_REGS  # First invalid address

    # Write transaction to out-of-range address.
    dut.awaddr.value = out_addr
    dut.awvalid.value = 1
    dut.wdata.value = 0xDEADDEAD
    dut.wstrb.value = 0xF
    dut.wvalid.value = 1
    dut.bready.value = 1
    # Wait until bvalid is asserted.
    while int(dut.bvalid.value) == 0:
        await RisingEdge(dut.clk)
    assert int(dut.bresp.value) == 2, f"Out-of-range write: expected bresp=2, got {int(dut.bresp.value)}"
    # Clear signals.
    dut.awvalid.value = 0
    dut.wvalid.value = 0
    dut.bready.value = 0
    await RisingEdge(dut.clk)
    
    # Read transaction from out-of-range address.
    dut.araddr.value = out_addr
    dut.arvalid.value = 1
    dut.rready.value = 1
    while int(dut.rvalid.value) == 0:
        await RisingEdge(dut.clk)
    assert int(dut.rresp.value) == 2, f"Out-of-range read: expected rresp=2, got {int(dut.rresp.value)}"
    dut.arvalid.value = 0
    dut.rready.value = 0
    await RisingEdge(dut.clk)
    
    dut._log.info("Out-of-range address AXI test passed.")

@cocotb.test(timeout_time=500, timeout_unit="ns")
async def test_edge_cases_with_axi(dut):
    """
    Test edge cases via the AXI interface by writing extreme values (all zeros and all ones)
    to a valid RW data register and then reading them back.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await dut_init(dut)
    
    # Apply reset.
    dut.arst_n.value = 0
    await Timer(50, unit="ns")
    dut.arst_n.value = 1
    await RisingEdge(dut.clk)
    
    NUM_DATA_REGS = int(dut.NUM_DATA_REGS.value)
    rw_idx = find_rw_index(dut, NUM_DATA_REGS)
    assert rw_idx is not None, "No RW data register found for edge cases test."
    dut._log.info(f"Using data register index {rw_idx} for edge cases test.")

    # Test edge case: Write all zeros.
    zero_val = 0x00000000
    dut.awaddr.value = rw_idx
    dut.awvalid.value = 1
    dut.wdata.value = zero_val
    dut.wstrb.value = 0xF
    dut.wvalid.value = 1
    dut.bready.value = 1
    while int(dut.bvalid.value) == 0:
        await RisingEdge(dut.clk)
    assert int(dut.bresp.value) == 0, f"Edge case write (0) failed: bresp = {int(dut.bresp.value)}"
    dut.awvalid.value = 0
    dut.wvalid.value = 0
    dut.bready.value = 0
    await RisingEdge(dut.clk)
    
    dut.araddr.value = rw_idx
    dut.arvalid.value = 1
    dut.rready.value = 1
    while int(dut.rvalid.value) == 0:
        await RisingEdge(dut.clk)
    assert int(dut.rdata.value) == zero_val, \
        f"Edge case read (0) failed, expected 0x{zero_val:x}, got 0x{int(dut.rdata.value):x}"
    assert int(dut.rresp.value) == 0, f"Edge case read (0) unexpected rresp: {int(dut.rresp.value)}"
    dut.arvalid.value = 0
    dut.rready.value = 0
    await RisingEdge(dut.clk)
    
    # Test edge case: Write all ones.
    ones_val = 0xFFFFFFFF
    dut.awaddr.value = rw_idx
    dut.awvalid.value = 1
    dut.wdata.value = ones_val
    dut.wstrb.value = 0xF
    dut.wvalid.value = 1
    dut.bready.value = 1
    while int(dut.bvalid.value) == 0:
        await RisingEdge(dut.clk)
    assert int(dut.bresp.value) == 0, f"Edge case write (ones) failed: bresp = {int(dut.bresp.value)}"
    dut.awvalid.value = 0
    dut.wvalid.value = 0
    dut.bready.value = 0
    await RisingEdge(dut.clk)
    
    dut.araddr.value = rw_idx
    dut.arvalid.value = 1
    dut.rready.value = 1
    while int(dut.rvalid.value) == 0:
        await RisingEdge(dut.clk)
    assert int(dut.rdata.value) == ones_val, \
        f"Edge case read (ones) failed, expected 0x{ones_val:x}, got 0x{int(dut.rdata.value):x}"
    assert int(dut.rresp.value) == 0, f"Edge case read (ones) unexpected rresp: {int(dut.rresp.value)}"
    dut.arvalid.value = 0
    dut.rready.value = 0
    await RisingEdge(dut.clk)
    
    dut._log.info("Edge cases AXI test passed.")

@cocotb.test(timeout_time=500, timeout_unit="ns")
async def test_read_violation_with_axi(dut):
    """
    Test that a read from a write-only data register via the AXI interface triggers a read violation.
    The test scans DATA_REG_ACCESS to find a register configured as write-only (WO) and attempts a read.
    Expected behavior: rresp = SLVERR (2) and rdata = error code (all ones).
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await dut_init(dut)
    
    # Apply reset.
    dut.arst_n.value = 0
    await Timer(50, unit="ns")
    dut.arst_n.value = 1
    await RisingEdge(dut.clk)
    
    NUM_DATA_REGS = int(dut.NUM_DATA_REGS.value)
    wo_idx = None
    for i in range(NUM_DATA_REGS):
        if get_data_reg_access(dut, i) == WO:
            wo_idx = i
            break
    assert wo_idx is not None, "No write-only data register found for read violation test."
    dut._log.info(f"Using data register index {wo_idx} (WO) for read violation test.")
    
    # Attempt to read from the write-only register.
    dut.araddr.value = wo_idx
    dut.arvalid.value = 1
    dut.rready.value = 1
    while int(dut.rvalid.value) == 0:
        await RisingEdge(dut.clk)
    assert int(dut.rresp.value) == 2, f"Read violation not flagged on WO register (index {wo_idx}), got rresp = {int(dut.rresp.value)}"
    dut.arvalid.value = 0
    dut.rready.value = 0
    await RisingEdge(dut.clk)
    
    dut._log.info("Read violation AXI test passed.")

@cocotb.test(timeout_time=500, timeout_unit="ns")
async def test_write_violation_with_axi(dut):
    """
    Test that a write to a read-only data register via the AXI interface triggers a write violation.
    The test scans DATA_REG_ACCESS to find a register configured as read-only (RO) and attempts a write.
    Expected behavior: bresp = SLVERR (2) and the write is rejected.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await dut_init(dut)
    
    # Apply reset.
    dut.arst_n.value = 0
    await Timer(50, unit="ns")
    dut.arst_n.value = 1
    await RisingEdge(dut.clk)
    
    NUM_DATA_REGS = int(dut.NUM_DATA_REGS.value)
    ro_idx = None
    for i in range(NUM_DATA_REGS):
        if get_data_reg_access(dut, i) == RO:
            ro_idx = i
            break
    assert ro_idx is not None, "No read-only data register found for write violation test."
    dut._log.info(f"Using data register index {ro_idx} (RO) for write violation test.")
    
    # Attempt to write to the read-only register.
    dut.awaddr.value = ro_idx
    dut.awvalid.value = 1
    dut.wdata.value = 0xCAFEBABE
    dut.wstrb.value = 0xF
    dut.wvalid.value = 1
    dut.bready.value = 1
    while int(dut.bvalid.value) == 0:
        await RisingEdge(dut.clk)
    # Expect bresp = SLVERR (2)
    assert int(dut.bresp.value) == 2, f"Write violation not flagged on RO register (index {ro_idx}), got bresp = {int(dut.bresp.value)}"
    dut.awvalid.value = 0
    dut.wvalid.value = 0
    dut.bready.value = 0
    await RisingEdge(dut.clk)
    
    dut._log.info("Write violation AXI test passed.")


def test_simple_dff_hidden_runner():
   sim = os.getenv("SIM", "icarus")

   proj_path = Path(__file__).resolve().parent.parent

   sources = [proj_path / "sources/axi_top.sv" , proj_path / "sources/csr_regfile.sv"]

   runner = get_runner(sim)
   runner.build(
       sources=sources,
       hdl_toplevel="axi_top",
       always=True,
       waves=True
   )

   runner.test(hdl_toplevel="axi_top", test_module="test_axi_top_hidden", waves=1)