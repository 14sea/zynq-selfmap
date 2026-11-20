// zynq-selfmap probe design s2a — bench: an AXI3 master, as M_AXI_GP0 is one, in front of the
// copied AXI3 front and the register file, with Vivado's simulation models of the memories.
//
// What it holds: every register does what pl/s2a/design.json says; bit k of the data register
// goes into memory k and nowhere else, at the address given and at no other (looked at inside
// the models, not only through the outputs); the shift registers are not shifted by anything but
// a write of SRL_DATA; and every transfer is answered — every wait here is bounded, and running
// out of cycles is a failure with the place named, never a bench that stands still.
//
// It is what stands in for the board before the board: a slave that does not answer cannot be
// met by the prober's twin, and on the board it costs a power cycle.

`timescale 1ns/1ps
`default_nettype none

module tb_s2a;
    localparam integer TIMEOUT = 200;
    localparam [1:0] OKAY = 2'b00;
    localparam [31:0] R_ID = 32'h00, R_SCRATCH = 32'h04, R_COUNT = 32'h08, R_RAM_ADDR = 32'h0C,
                      R_RAM_DATA = 32'h10, R_SRL_ADDR = 32'h14, R_SRL_DATA = 32'h18, R_WRITES = 32'h1C;

    integer failures = 0, checks = 0;
    reg clk = 0; always #5 clk = ~clk;
    reg rst_n = 0;

    reg  [11:0] awid = 0, wid = 0, arid = 0;
    reg  [31:0] awaddr = 0, wdata = 0, araddr = 0;
    reg  [3:0]  awlen = 0, arlen = 0, wstrb = 4'hF;
    reg  [2:0]  awsize = 3'b010, arsize = 3'b010;
    reg  [1:0]  awburst = 2'b01, arburst = 2'b01;
    reg         awvalid = 0, wvalid = 0, wlast = 0, bready = 0, arvalid = 0, rready = 0;
    wire        awready, wready, bvalid, arready, rvalid, rlast;
    wire [11:0] bid, rid;
    wire [1:0]  bresp, rresp;
    wire [31:0] rdata;

    wire [15:0] m_awaddr, m_araddr;
    wire [31:0] m_wdata, m_rdata;
    wire [3:0]  m_wstrb;
    wire [1:0]  m_bresp, m_rresp;
    wire        m_awvalid, m_awready, m_wvalid, m_wready, m_bvalid, m_bready, m_arvalid, m_arready, m_rvalid, m_rready;

    carrier_axi3_lite #(.ID_W(12), .ADDR_W(16)) front (
        .clk(clk), .rst_n(rst_n),
        .s_awid(awid), .s_awaddr(awaddr), .s_awlen(awlen), .s_awsize(awsize), .s_awburst(awburst), .s_awvalid(awvalid), .s_awready(awready),
        .s_wid(wid), .s_wdata(wdata), .s_wstrb(wstrb), .s_wlast(wlast), .s_wvalid(wvalid), .s_wready(wready),
        .s_bid(bid), .s_bresp(bresp), .s_bvalid(bvalid), .s_bready(bready),
        .s_arid(arid), .s_araddr(araddr), .s_arlen(arlen), .s_arsize(arsize), .s_arburst(arburst), .s_arvalid(arvalid), .s_arready(arready),
        .s_rid(rid), .s_rdata(rdata), .s_rresp(rresp), .s_rlast(rlast), .s_rvalid(rvalid), .s_rready(rready),
        .m_awaddr(m_awaddr), .m_awvalid(m_awvalid), .m_awready(m_awready), .m_wdata(m_wdata), .m_wstrb(m_wstrb), .m_wvalid(m_wvalid), .m_wready(m_wready),
        .m_bresp(m_bresp), .m_bvalid(m_bvalid), .m_bready(m_bready),
        .m_araddr(m_araddr), .m_arvalid(m_arvalid), .m_arready(m_arready), .m_rdata(m_rdata), .m_rresp(m_rresp), .m_rvalid(m_rvalid), .m_rready(m_rready));

    s2a_regs regs (
        .clk(clk), .rst_n(rst_n),
        .s_awaddr(m_awaddr), .s_awvalid(m_awvalid), .s_awready(m_awready), .s_wdata(m_wdata), .s_wstrb(m_wstrb), .s_wvalid(m_wvalid), .s_wready(m_wready),
        .s_bresp(m_bresp), .s_bvalid(m_bvalid), .s_bready(m_bready),
        .s_araddr(m_araddr), .s_arvalid(m_arvalid), .s_arready(m_arready), .s_rdata(m_rdata), .s_rresp(m_rresp), .s_rvalid(m_rvalid), .s_rready(m_rready));

    task fail(input [8*96-1:0] what);
        begin failures = failures + 1; $display("FAIL at %0t: %0s", $time, what); end
    endtask
    task check(input ok, input [8*96-1:0] what);
        begin checks = checks + 1; if (!ok) fail(what); end
    endtask

    // A channel's handshake, as a clocked master sees it: the valid is raised after a falling edge, and at each
    // rising edge the ready is looked at as it stood before that edge. Every wait is bounded.
    reg seen;
    // one write of one beat, as the general-purpose master makes it
    reg [11:0] next_id = 12'h5A0;
    task axi_write(input [31:0] addr, input [31:0] data, input [3:0] strb);
        integer n;
        begin
            next_id = next_id + 1;
            @(negedge clk);
            awid = next_id; awaddr = addr; awlen = 0; awvalid = 1;
            seen = 0; n = 0;
            while (!seen && n < TIMEOUT) begin @(posedge clk); seen = awready; n = n + 1; end
            if (!seen) fail("the write address was never taken");
            @(negedge clk); awvalid = 0;
            wid = next_id; wdata = data; wstrb = strb; wlast = 1; wvalid = 1;
            seen = 0; n = 0;
            while (!seen && n < TIMEOUT) begin @(posedge clk); seen = wready; n = n + 1; end
            if (!seen) fail("the write data was never taken");
            @(negedge clk); wvalid = 0; wlast = 0; bready = 1;
            seen = 0; n = 0;
            while (!seen && n < TIMEOUT) begin
                @(posedge clk); seen = bvalid; n = n + 1;
                if (seen) begin
                    if (bid !== next_id) fail("the write response has another ID");
                    if (bresp !== OKAY) fail("the write response is not OKAY");
                end
            end
            if (!seen) fail("no write response");
            @(negedge clk); bready = 0;
        end
    endtask

    // one read of `beats` beats; the data of the last beat is returned
    reg [31:0] got;
    task axi_read(input [31:0] addr, input integer beats);
        integer n, b;
        begin
            next_id = next_id + 1;
            @(negedge clk);
            arid = next_id; araddr = addr; arlen = beats - 1; arvalid = 1;
            seen = 0; n = 0;
            while (!seen && n < TIMEOUT) begin @(posedge clk); seen = arready; n = n + 1; end
            if (!seen) fail("the read address was never taken");
            @(negedge clk); arvalid = 0; rready = 1;
            for (b = 0; b < beats; b = b + 1) begin
                seen = 0; n = 0;
                while (!seen && n < TIMEOUT) begin
                    @(posedge clk); seen = rvalid; n = n + 1;
                    if (seen) begin
                        got = rdata;
                        if (rid !== next_id) fail("the read data has another ID");
                        if (rresp !== OKAY) fail("the read response is not OKAY");
                        if (rlast !== (b == beats - 1)) fail("RLAST is not on the last beat and only there");
                    end
                end
                if (!seen) fail("no read data");
            end
            @(negedge clk); rready = 0;
        end
    endtask

    function [3:0] pattern(input integer state, input integer a);
        pattern = state == 0 ? 4'h0 : state == 1 ? 4'hF : state == 2 ? a[3:0] : ~a[3:0];
    endfunction

    integer s, a, k;
    reg [31:0] c0, c1;
    reg [3:0]  want;
    reg [31:0] srl_init [0:3];
    reg [63:0] was [0:3];
    initial begin
        srl_init[0] = 32'hA5C30F69; srl_init[1] = 32'h0F1E2D3C; srl_init[2] = 32'h13579BDF; srl_init[3] = 32'hFEDCBA98;
        repeat (4) @(negedge clk); rst_n = 1; repeat (2) @(negedge clk);

        // the identification, the scratch register, the counter
        axi_read(R_ID, 1);       check(got === 32'h53324131, "the identification register");
        axi_write(R_ID, 32'hFFFFFFFF, 4'hF);
        axi_read(R_ID, 1);       check(got === 32'h53324131, "the identification register after a write to it");
        axi_read(R_SCRATCH, 1);  check(got === 32'h0, "the scratch register after reset");
        axi_write(R_SCRATCH, 32'hFFFFFFFF, 4'hF); axi_read(R_SCRATCH, 1); check(got === 32'hFFFFFFFF, "scratch all ones");
        axi_write(R_SCRATCH, 32'hA5A55A5A, 4'hF); axi_read(R_SCRATCH, 1); check(got === 32'hA5A55A5A, "scratch a pattern");
        axi_write(R_SCRATCH, 32'h5A5AA5A5, 4'hF); axi_read(R_SCRATCH, 1); check(got === 32'h5A5AA5A5, "scratch its complement");
        axi_write(R_SCRATCH, 32'h00000000, 4'h3); axi_read(R_SCRATCH, 1); check(got === 32'h5A5AA5A5, "a write of part of a word changes nothing");
        axi_read(R_COUNT, 1); c0 = got; axi_read(R_COUNT, 1); c1 = got;
        check(c1 !== c0 && c1 - c0 < 32'd100, "the counter goes on between two reads");

        // the LUT RAM: four states, each written to every address and read back from every address
        axi_read(R_WRITES, 1); check(got === 32'h0, "no write and no shift counted before any was made");
        for (s = 0; s < 4; s = s + 1) begin
            for (a = 0; a < 64; a = a + 1) begin
                axi_write(R_RAM_ADDR, a, 4'hF);
                axi_write(R_RAM_DATA, {28'd0, pattern(s, a)}, 4'hF);
            end
            for (a = 0; a < 64; a = a + 1) begin
                axi_write(R_RAM_ADDR, a, 4'hF);
                axi_read(R_RAM_DATA, 1);
                check(got === {28'd0, pattern(s, a)}, "the RAM reads back what the state wrote");
                // inside the models: bit k of the data is in memory k at this address
                want = pattern(s, a);
                check(regs.ram0.mem[a] === want[0] && regs.ram1.mem[a] === want[1] && regs.ram2.mem[a] === want[2] && regs.ram3.mem[a] === want[3],
                      "bit k of the data is in memory k");
            end
        end
        // one write changes one address and nothing else: all four memories before and after
        was[0] = regs.ram0.mem; was[1] = regs.ram1.mem; was[2] = regs.ram2.mem; was[3] = regs.ram3.mem;
        axi_write(R_RAM_ADDR, 32'd37, 4'hF);
        axi_read(R_RAM_DATA, 1); c0 = got;
        axi_write(R_RAM_DATA, {28'd0, ~c0[3:0] & 4'b0100 | c0[3:0] & 4'b1011}, 4'hF);      // bit 2 turned over, the others as they were
        repeat (3) @(negedge clk);
        check(regs.ram0.mem === was[0] && regs.ram1.mem === was[1] && regs.ram3.mem === was[3], "a write of one bit leaves the other three memories as they were");
        check(regs.ram2.mem === (was[2] ^ (64'd1 << 37)), "and changes one bit of the fourth, at the address given");
        axi_read(R_RAM_ADDR, 1); check(got === 32'd37, "the address register reads back");
        axi_read(R_WRITES, 1);   check(got === 32'd257, "the design counted 257 RAM writes and no shift");

        // the shift registers: what was loaded, at every address, twice; then one shift
        for (k = 0; k < 2; k = k + 1)
            for (a = 0; a < 32; a = a + 1) begin
                axi_write(R_SRL_ADDR, a, 4'hF);
                axi_read(R_SRL_DATA, 1);
                check(got === {28'd0, srl_init[3][a], srl_init[2][a], srl_init[1][a], srl_init[0][a]}, "the shift registers hold what was loaded");
            end
        check(regs.srl0.data === srl_init[0] && regs.srl3.data === srl_init[3], "nothing has shifted them");
        axi_write(R_SRL_DATA, 32'h0000_0005, 4'hF);
        repeat (3) @(negedge clk);
        check(regs.srl0.data === {srl_init[0][30:0], 1'b1} && regs.srl1.data === {srl_init[1][30:0], 1'b0}
              && regs.srl2.data === {srl_init[2][30:0], 1'b1} && regs.srl3.data === {srl_init[3][30:0], 1'b0}, "one write of SRL_DATA is one shift of each");
        axi_read(R_WRITES, 1); check(got === 32'h0001_0101, "the design counted the shift");
        repeat (50) @(negedge clk);
        check(regs.srl0.data === {srl_init[0][30:0], 1'b1}, "and nothing shifts while nothing is asked");
        check(regs.ram2.mem === (was[2] ^ (64'd1 << 37)), "nor is the RAM written while nothing is asked");

        // what is no register: reads zero, takes a write and does nothing — and answers
        axi_read(32'h0000_0020, 1); check(got === 32'h0, "an address above the eight registers reads zero");
        axi_read(32'h0000_8004, 1); check(got === 32'h0, "a far address does not read the scratch register");
        axi_write(32'h0000_8004, 32'h12345678, 4'hF);
        axi_read(R_SCRATCH, 1);     check(got === 32'h5A5AA5A5, "nor does a write there reach it");
        // a read of two beats is answered beat for beat, the last one marked
        axi_read(R_ID, 2);          check(got === 32'h5A5AA5A5, "a read of two beats: the second beat is the next register");

        if (failures == 0) $display("S2A BENCH PASS: %0d checks", checks);
        else               $display("S2A BENCH FAIL: %0d of %0d checks", failures, checks);
        $finish;
    end

    initial begin #20_000_000; $display("S2A BENCH FAIL: the bench did not come to its end"); $finish; end
endmodule

`default_nettype wire
