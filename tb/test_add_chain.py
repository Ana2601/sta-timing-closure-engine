import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ReadOnly, NextTimeStep


def chain_golden(x, d, stages):
    """Golden model for add_chain: x + d[0] + d[1] + ... + d[K-1]."""
    acc = x
    for i in range(stages):
        acc = acc + d[i]
    return acc & 0xFFFF


@cocotb.test()
async def test_add_chain_functional(dut):
    """Drives the retimed add_chain and checks out == x + sum(d)."""
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.rst_n.value = 0
    dut.en.value = 0
    dut.x.value = 0
    dut.d.value = 0
    await RisingEdge(dut.clk)
    await NextTimeStep()
    dut.rst_n.value = 1

    nblk = int(len(dut.d)) // 16
    for trial in range(50):
        x = (trial * 3 + 1) & 0xFFFF
        d = [((i + 1) * 7 + trial * 13) & 0xFFFF for i in range(nblk)]
        dut.x.value = x
        # pack d[K-1] as the MSB slice
        packed = 0
        for i in range(nblk):
            packed |= d[i] << (16 * i)
        dut.d.value = packed
        await NextTimeStep()
        dut.en.value = 1
        await RisingEdge(dut.clk)
        await ReadOnly()
        got = int(dut.out.value)
        exp = chain_golden(x, d, nblk)
        assert got == exp, f"trial {trial}: got {got:#x}, exp {exp:#x}"
        await NextTimeStep()
        dut.en.value = 0

    dut._log.info("add_chain functional check PASSED (50 trials)")
