// zynq-selfmap probe design s2b — bench: an AXI3 master, as M_AXI_GP0 is one, in front of the
// copied AXI3 front and the register file, with Vivado's simulation model of the memory.
// The master's tasks are those of pl/s2a/tb_s2a.v, word for word.
//
// What it holds: every register does what pl/s2b/design.json says; every memory of every site
// is loaded with its own word and reads it back through its site's number; a write goes into
// memory k of the site named and of no other, or of every site, at the address given and at no
// other (looked at inside the models, not only through the outputs); CHECK says of all sites
// together what they hold; a site number that names no site reads zero and writes nothing; and
// every transfer is answered — every wait here is bounded, and the bench ends by itself after 25 failures.

`timescale 1ns/1ps
`default_nettype none

module tb_s2b;
    localparam integer TIMEOUT = 200;
    localparam [1:0] OKAY = 2'b00;
    localparam [31:0] R_ID = 32'h00, R_SITE = 32'h04, R_COUNT = 32'h08, R_RAM_ADDR = 32'h0C,
                      R_RAM_DATA = 32'h10, R_NONE = 32'h14, R_CHECK = 32'h18, R_WRITES = 32'h1C;
    localparam integer N = 110;
    localparam [31:0] EVERY = 32'h100;

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

    s2b_regs regs (
        .clk(clk), .rst_n(rst_n),
        .s_awaddr(m_awaddr), .s_awvalid(m_awvalid), .s_awready(m_awready), .s_wdata(m_wdata), .s_wstrb(m_wstrb), .s_wvalid(m_wvalid), .s_wready(m_wready),
        .s_bresp(m_bresp), .s_bvalid(m_bvalid), .s_bready(m_bready),
        .s_araddr(m_araddr), .s_arvalid(m_arvalid), .s_arready(m_arready), .s_rdata(m_rdata), .s_rresp(m_rresp), .s_rvalid(m_rvalid), .s_rready(m_rready));

    // A design that fails at all fails often, and a slave that does not answer makes every transfer run out its
    // wait: after 25 failures the bench says where it stands and ends.
    task fail(input [8*96-1:0] what);
        begin
            failures = failures + 1; $display("FAIL at %0t: %0s", $time, what);
            if (failures >= 25) begin $display("S2B BENCH FAIL: %0d failures, and the bench goes no further", failures); $finish; end
        end
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

    // the word memory number n is loaded with: written here again, not taken from the design
    function [63:0] init_of(input integer n);
        reg [63:0] x;
        begin
            x = 64'h9E3779B97F4A7C15 * n;
            x = x ^ (x >> 29);
            x = x * 64'hBF58476D1CE4E5B9;
            x = x ^ (x >> 32);
            init_of = x;
        end
    endfunction

    // inside the models: what memory k of site g holds, all 64 bits
    wire [63:0] m0 [0:N-1], m1 [0:N-1], m2 [0:N-1], m3 [0:N-1];
    genvar g;
    generate
        for (g = 0; g < N; g = g + 1) begin : look
            assign m0[g] = regs.at[g].ram0.mem;
            assign m1[g] = regs.at[g].ram1.mem;
            assign m2[g] = regs.at[g].ram2.mem;
            assign m3[g] = regs.at[g].ram3.mem;
        end
    endgenerate

    integer s, a, k, others;
    reg [31:0] c0, c1;
    reg [3:0]  want, any1, all1, par;
    reg [63:0] was0 [0:N-1], was1 [0:N-1], was2 [0:N-1], was3 [0:N-1];

    task remember;
        integer i;
        begin for (i = 0; i < N; i = i + 1) begin was0[i] = m0[i]; was1[i] = m1[i]; was2[i] = m2[i]; was3[i] = m3[i]; end end
    endtask
    // how many sites other than `but` hold something else than remembered
    function integer changed_elsewhere(input integer but);
        integer i;
        begin
            changed_elsewhere = 0;
            for (i = 0; i < N; i = i + 1)
                if (i != but && (m0[i] !== was0[i] || m1[i] !== was1[i] || m2[i] !== was2[i] || m3[i] !== was3[i]))
                    changed_elsewhere = changed_elsewhere + 1;
        end
    endfunction
    // what CHECK must read at address `at`, from inside the models
    task expect_check(input integer at);
        integer i;
        begin
            any1 = 0; all1 = 4'hF; par = 0;
            for (i = 0; i < N; i = i + 1) begin
                want = {m3[i][at], m2[i][at], m1[i][at], m0[i][at]};
                any1 = any1 | want; all1 = all1 & want; par = par ^ want;
            end
        end
    endtask

    initial begin
        repeat (4) @(negedge clk); rst_n = 1; repeat (2) @(negedge clk);

        // the identification, the site register, the counter, what is no register
        axi_read(R_ID, 1);       check(got === 32'h53324231, "the identification register");
        axi_write(R_ID, 32'hFFFFFFFF, 4'hF);
        axi_read(R_ID, 1);       check(got === 32'h53324231, "the identification register after a write to it");
        axi_read(R_SITE, 1);     check(got === 32'h0, "the site register after reset");
        axi_write(R_SITE, 32'hFFFFFFFF, 4'hF); axi_read(R_SITE, 1); check(got === 32'h0000017F, "the site register keeps seven bits and the one of every site");
        axi_write(R_SITE, 32'h00000000, 4'h3); axi_read(R_SITE, 1); check(got === 32'h0000017F, "a write of part of a word changes nothing");
        axi_write(R_SITE, 32'd0, 4'hF);
        axi_read(R_COUNT, 1); c0 = got; axi_read(R_COUNT, 1); c1 = got;
        check(c1 !== c0 && c1 - c0 < 32'd100, "the counter goes on between two reads");
        axi_read(R_NONE, 1);     check(got === 32'h0, "the offset that is no register reads zero");
        axi_write(R_NONE, 32'hFFFFFFFF, 4'hF);
        axi_read(R_WRITES, 1);   check(got === 32'h0, "no write counted before any was made");

        // as loaded: every memory of every site holds its own word, inside the model and through its site's number
        for (s = 0; s < N; s = s + 1) begin
            check(m0[s] === init_of(4 * s + 1) && m1[s] === init_of(4 * s + 2) && m2[s] === init_of(4 * s + 3) && m3[s] === init_of(4 * s + 4),
                  "a memory is loaded with the word of its number");
            axi_write(R_SITE, s, 4'hF);
            for (a = 0; a < 64; a = a + (s % 7 == 0 ? 1 : 13)) begin        // every address at every seventh site, every thirteenth at the others
                axi_write(R_RAM_ADDR, a, 4'hF);
                axi_read(R_RAM_DATA, 1);
                check(got === {28'd0, m3[s][a], m2[s][a], m1[s][a], m0[s][a]}, "a site reads back what it is loaded with");
            end
        end
        for (a = 0; a < 64; a = a + 1) begin
            axi_write(R_RAM_ADDR, a, 4'hF);
            axi_read(R_CHECK, 1); expect_check(a);
            check(got === {20'd0, par, all1, any1}, "CHECK as loaded");
        end
        axi_write(R_CHECK, 32'hFFFFFFFF, 4'hF);
        axi_read(R_WRITES, 1);   check(got === 32'h0, "nothing of that was a write to a memory");

        // a write to one site: bit k into memory k of that site at that address, and nothing anywhere else
        remember;
        axi_write(R_SITE, 32'd57, 4'hF);
        axi_write(R_RAM_ADDR, 32'd37, 4'hF);
        axi_read(R_RAM_DATA, 1); c0 = got;
        axi_write(R_RAM_DATA, {28'd0, ~c0[3:0] & 4'b0100 | c0[3:0] & 4'b1011}, 4'hF);      // bit 2 turned over, the others as they were
        repeat (3) @(negedge clk);
        check(m0[57] === was0[57] && m1[57] === was1[57] && m3[57] === was3[57], "a write of one bit leaves the other three memories of the site as they were");
        check(m2[57] === (was2[57] ^ (64'd1 << 37)), "and changes one bit of the fourth, at the address given");
        check(changed_elsewhere(57) == 0, "and no memory of any other site");
        axi_read(R_RAM_DATA, 1); check(got === {28'd0, c0[3:0] ^ 4'b0100}, "the site reads the write back");
        axi_read(R_CHECK, 1); expect_check(37); check(got === {20'd0, par, all1, any1}, "CHECK after it: the parity of that memory has turned");
        axi_read(R_WRITES, 1);   check(got === 32'd1, "one write counted");

        // a site number that names no site: writes nothing, reads zero
        remember;
        axi_write(R_SITE, 32'd110, 4'hF);
        axi_write(R_RAM_DATA, 32'hF, 4'hF);
        repeat (3) @(negedge clk);
        check(changed_elsewhere(-1) == 0, "a write under a number that is no site goes nowhere");
        axi_read(R_RAM_DATA, 1); check(got === 32'h0, "and a read under it reads zero");
        axi_write(R_SITE, 32'd127, 4'hF);
        axi_write(R_RAM_DATA, 32'hF, 4'hF);
        repeat (3) @(negedge clk);
        check(changed_elsewhere(-1) == 0, "nor under the highest number");

        // a write to every site: four states over every address, held by CHECK and inside the models
        axi_write(R_SITE, EVERY | 32'd3, 4'hF);
        for (s = 0; s < 4; s = s + 1) begin
            for (a = 0; a < 64; a = a + 1) begin
                axi_write(R_RAM_ADDR, a, 4'hF);
                axi_write(R_RAM_DATA, {28'd0, s == 0 ? 4'h0 : s == 1 ? 4'hF : s == 2 ? a[3:0] : ~a[3:0]}, 4'hF);
            end
            for (a = 0; a < 64; a = a + 1) begin
                want = s == 0 ? 4'h0 : s == 1 ? 4'hF : s == 2 ? a[3:0] : ~a[3:0];
                axi_write(R_RAM_ADDR, a, 4'hF);
                axi_read(R_CHECK, 1);
                check(got === {20'd0, 4'h0, want, want}, "every site holds the state: one at a site is one at all, and 110 alike have even parity");
                axi_read(R_RAM_DATA, 1); check(got === {28'd0, want}, "and the site the number names reads it");
                others = 0;
                for (k = 0; k < N; k = k + 1)
                    if ({m3[k][a], m2[k][a], m1[k][a], m0[k][a]} !== want) others = others + 1;
                check(others == 0, "inside the models: every site, bit k in memory k");
            end
        end
        // and one site made to differ: CHECK shows it in all three ways
        axi_write(R_SITE, 32'd109, 4'hF);
        axi_write(R_RAM_ADDR, 32'd5, 4'hF);
        axi_write(R_RAM_DATA, 32'h0, 4'hF);                 // the last state has ~5 = 4'hA at address 5: bits 3 and 1 go from one to zero at one site
        axi_read(R_CHECK, 1);    check(got === {20'd0, 4'hA, 4'h0, 4'hA}, "one site otherwise: a one somewhere still, not everywhere, and the parity odd");
        axi_read(R_WRITES, 1);   check(got === 32'd260, "the design counted 260 writes: one to a site, two to no site, 256 to all, one more");
        repeat (50) @(negedge clk);
        remember; repeat (50) @(negedge clk);
        check(changed_elsewhere(-1) == 0, "no memory is written while nothing is asked");

        // what is no register: reads zero, takes a write and does nothing — and answers
        axi_read(32'h0000_0020, 1); check(got === 32'h0, "an address above the eight registers reads zero");
        axi_read(32'h0000_8004, 1); check(got === 32'h0, "a far address does not read the site register");
        axi_write(32'h0000_8004, 32'h00000155, 4'hF);
        axi_read(R_SITE, 1);        check(got === 32'd109, "nor does a write there reach it");
        axi_read(R_ID, 2);          check(got === 32'd109, "a read of two beats: the second beat is the next register");

        if (failures == 0) $display("S2B BENCH PASS: %0d checks", checks);
        else               $display("S2B BENCH FAIL: %0d of %0d checks", failures, checks);
        $finish;
    end

    initial begin #400_000_000; $display("S2B BENCH FAIL: the bench did not come to its end"); $finish; end
endmodule

`default_nettype wire
