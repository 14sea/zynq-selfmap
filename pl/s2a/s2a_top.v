// zynq-selfmap probe design s2a — top level. docs/s2_plan.md, section 5.
//
//   PS7 (M_AXI_GP0, FCLK0) -> AXI3 front (copied, unchanged) -> the register file -> the memories
//
// No ports: the design has no pin. The PS reaches it through M_AXI_GP0 and through nothing else.
// M_AXI_GP0 is an AXI3 master; every one of its inputs that it waits for is driven by the front
// (zynq-fabricmap's erratum 002: RLAST left low stalls the processor until a power cycle).

`default_nettype none

module s2a_top ();
    wire [3:0]  fclkclk;                                // PS7 outputs, four bits each; bit 0 is used
    wire [3:0]  fclkresetn;
    wire        clk;
    wire        rst_n = fclkresetn[0];

    BUFG fclk0_buf (.I(fclkclk[0]), .O(clk));

    wire [31:0] ps_awaddr, ps_wdata, ps_araddr, ps_rdata;
    wire        ps_awvalid, ps_awready, ps_wvalid, ps_wready, ps_bvalid, ps_bready;
    wire        ps_arvalid, ps_arready, ps_rvalid, ps_rready, ps_wlast, ps_rlast;
    wire [1:0]  ps_bresp, ps_rresp, ps_awsize, ps_arsize, ps_awburst, ps_arburst;
    wire [3:0]  ps_wstrb, ps_awlen, ps_arlen;
    wire [11:0] ps_awid, ps_wid, ps_bid, ps_arid, ps_rid;

    PS7 ps7 (
        .FCLKCLK        (fclkclk),
        .FCLKRESETN     (fclkresetn),
        .MAXIGP0ACLK    (clk),
        .MAXIGP0ARESETN (),
        .MAXIGP0AWID    (ps_awid),    .MAXIGP0AWADDR  (ps_awaddr),  .MAXIGP0AWLEN   (ps_awlen),
        .MAXIGP0AWSIZE  (ps_awsize),  .MAXIGP0AWBURST (ps_awburst), .MAXIGP0AWVALID (ps_awvalid),
        .MAXIGP0AWREADY (ps_awready),
        .MAXIGP0WID     (ps_wid),     .MAXIGP0WDATA   (ps_wdata),   .MAXIGP0WSTRB   (ps_wstrb),
        .MAXIGP0WLAST   (ps_wlast),   .MAXIGP0WVALID  (ps_wvalid),  .MAXIGP0WREADY  (ps_wready),
        .MAXIGP0BID     (ps_bid),     .MAXIGP0BRESP   (ps_bresp),   .MAXIGP0BVALID  (ps_bvalid),
        .MAXIGP0BREADY  (ps_bready),
        .MAXIGP0ARID    (ps_arid),    .MAXIGP0ARADDR  (ps_araddr),  .MAXIGP0ARLEN   (ps_arlen),
        .MAXIGP0ARSIZE  (ps_arsize),  .MAXIGP0ARBURST (ps_arburst), .MAXIGP0ARVALID (ps_arvalid),
        .MAXIGP0ARREADY (ps_arready),
        .MAXIGP0RID     (ps_rid),     .MAXIGP0RDATA   (ps_rdata),   .MAXIGP0RRESP   (ps_rresp),
        .MAXIGP0RLAST   (ps_rlast),   .MAXIGP0RVALID  (ps_rvalid),  .MAXIGP0RREADY  (ps_rready)
    );

    wire [15:0] m_awaddr, m_araddr;
    wire [31:0] m_wdata, m_rdata;
    wire [3:0]  m_wstrb;
    wire [1:0]  m_bresp, m_rresp;
    wire        m_awvalid, m_awready, m_wvalid, m_wready, m_bvalid, m_bready;
    wire        m_arvalid, m_arready, m_rvalid, m_rready;

    // the size fields are two bits wide on PS7 and three on the front: extended here
    carrier_axi3_lite #(.ID_W(12), .ADDR_W(16)) front (
        .clk(clk), .rst_n(rst_n),
        .s_awid(ps_awid), .s_awaddr(ps_awaddr), .s_awlen(ps_awlen), .s_awsize({1'b0, ps_awsize}),
        .s_awburst(ps_awburst), .s_awvalid(ps_awvalid), .s_awready(ps_awready),
        .s_wid(ps_wid), .s_wdata(ps_wdata), .s_wstrb(ps_wstrb), .s_wlast(ps_wlast),
        .s_wvalid(ps_wvalid), .s_wready(ps_wready),
        .s_bid(ps_bid), .s_bresp(ps_bresp), .s_bvalid(ps_bvalid), .s_bready(ps_bready),
        .s_arid(ps_arid), .s_araddr(ps_araddr), .s_arlen(ps_arlen), .s_arsize({1'b0, ps_arsize}),
        .s_arburst(ps_arburst), .s_arvalid(ps_arvalid), .s_arready(ps_arready),
        .s_rid(ps_rid), .s_rdata(ps_rdata), .s_rresp(ps_rresp), .s_rlast(ps_rlast),
        .s_rvalid(ps_rvalid), .s_rready(ps_rready),
        .m_awaddr(m_awaddr), .m_awvalid(m_awvalid), .m_awready(m_awready),
        .m_wdata(m_wdata), .m_wstrb(m_wstrb), .m_wvalid(m_wvalid), .m_wready(m_wready),
        .m_bresp(m_bresp), .m_bvalid(m_bvalid), .m_bready(m_bready),
        .m_araddr(m_araddr), .m_arvalid(m_arvalid), .m_arready(m_arready),
        .m_rdata(m_rdata), .m_rresp(m_rresp), .m_rvalid(m_rvalid), .m_rready(m_rready)
    );

    s2a_regs regs (
        .clk(clk), .rst_n(rst_n),
        .s_awaddr(m_awaddr), .s_awvalid(m_awvalid), .s_awready(m_awready),
        .s_wdata(m_wdata), .s_wstrb(m_wstrb), .s_wvalid(m_wvalid), .s_wready(m_wready),
        .s_bresp(m_bresp), .s_bvalid(m_bvalid), .s_bready(m_bready),
        .s_araddr(m_araddr), .s_arvalid(m_arvalid), .s_arready(m_arready),
        .s_rdata(m_rdata), .s_rresp(m_rresp), .s_rvalid(m_rvalid), .s_rready(m_rready)
    );
endmodule

`default_nettype wire
