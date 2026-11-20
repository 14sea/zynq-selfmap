// zynq-selfmap probe design s2a — the register file, and the memories it stands in front of.
// docs/s2_plan.md, section 5; the registers are listed in pl/s2a/design.json.
//
// An AXI4-Lite slave of eight registers. It is driven by the AXI3 front copied from
// zynq-fabricmap (imported/fabricmap/carrier_axi3_lite.v), which presents the write address
// and the write data together and passes the read channel through.
//
// EVERY TRANSFER IS ANSWERED. A write is taken whenever no response is pending and answered
// in the next cycle; a read likewise. No address, no strobe and no value can leave a channel
// waiting: an address that is no register reads zero and a write to it does nothing. A slave
// that does not answer stalls the processor until the board is switched off and on.
//
// THE ONLY CHANGEABLE MEMORY CELLS OF THE DESIGN ARE THE EIGHT PRIMITIVES BELOW: four
// RAM64X1S and four SRLC32E, each instantiated by name and placed by the constraints. There
// is no array in this file, and every register is kept from being turned into a shift
// register (`shreg_extract`), so that what the configuration readback shows to change with
// the memories' content can only be these.

`default_nettype none

module s2a_regs #(
    parameter [31:0] ID_WORD = 32'h5332_4131,          // "S2A1"
    parameter [31:0] SRL0_INIT = 32'hA5C3_0F69,
    parameter [31:0] SRL1_INIT = 32'h0F1E_2D3C,
    parameter [31:0] SRL2_INIT = 32'h1357_9BDF,
    parameter [31:0] SRL3_INIT = 32'hFEDC_BA98
) (
    input  wire        clk,
    input  wire        rst_n,

    input  wire [15:0] s_awaddr,
    input  wire        s_awvalid,
    output wire        s_awready,
    input  wire [31:0] s_wdata,
    input  wire [3:0]  s_wstrb,
    input  wire        s_wvalid,
    output wire        s_wready,
    output wire [1:0]  s_bresp,
    output reg         s_bvalid,
    input  wire        s_bready,

    input  wire [15:0] s_araddr,
    input  wire        s_arvalid,
    output wire        s_arready,
    output reg  [31:0] s_rdata,
    output wire [1:0]  s_rresp,
    output reg         s_rvalid,
    input  wire        s_rready
);
    localparam [2:0] R_ID = 3'd0, R_SCRATCH = 3'd1, R_COUNT = 3'd2, R_RAM_ADDR = 3'd3,
                     R_RAM_DATA = 3'd4, R_SRL_ADDR = 3'd5, R_SRL_DATA = 3'd6, R_WRITES = 3'd7;

    (* shreg_extract = "no" *) reg [31:0] scratch;
    (* shreg_extract = "no" *) reg [31:0] count;
    (* shreg_extract = "no" *) reg [5:0]  ram_addr;
    (* shreg_extract = "no" *) reg [4:0]  srl_addr;
    (* shreg_extract = "no" *) reg [3:0]  ram_d, srl_d;
    (* shreg_extract = "no" *) reg        ram_we, srl_ce;
    (* shreg_extract = "no" *) reg [15:0] ram_writes, srl_shifts;

    wire [3:0] ram_o, srl_q;

    // ---------------------------------------------------------------- the two channels
    // A write is taken when the address and the data are both there and no response waits.
    // The front holds both valid until both are ready, so nothing is lost by waiting for both.
    wire wr = s_awvalid && s_wvalid && !s_bvalid;
    assign s_awready = wr;
    assign s_wready  = wr;
    assign s_bresp   = 2'b00;

    wire rd = s_arvalid && !s_rvalid;
    assign s_arready = rd;
    assign s_rresp   = 2'b00;

    // only the eight words at the bottom of the address space are registers, and only a write
    // of the whole word is one
    wire        wr_reg = wr && (s_awaddr[15:5] == 11'd0) && (s_awaddr[1:0] == 2'b00) && (s_wstrb == 4'hF);
    wire [2:0]  wr_sel = s_awaddr[4:2];
    wire        rd_reg = (s_araddr[15:5] == 11'd0) && (s_araddr[1:0] == 2'b00);
    wire [2:0]  rd_sel = s_araddr[4:2];

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            s_bvalid   <= 1'b0;
            s_rvalid   <= 1'b0;
            s_rdata    <= 32'd0;
            scratch    <= 32'd0;
            count      <= 32'd0;
            ram_addr   <= 6'd0;
            srl_addr   <= 5'd0;
            ram_d      <= 4'd0;
            srl_d      <= 4'd0;
            ram_we     <= 1'b0;
            srl_ce     <= 1'b0;
            ram_writes <= 16'd0;
            srl_shifts <= 16'd0;
        end else begin
            count  <= count + 32'd1;
            ram_we <= 1'b0;                              // one clock each, and only when asked
            srl_ce <= 1'b0;

            if (s_bvalid && s_bready) s_bvalid <= 1'b0;
            if (wr) begin
                s_bvalid <= 1'b1;
                if (wr_reg) begin
                    case (wr_sel)
                        R_SCRATCH:  scratch  <= s_wdata;
                        R_RAM_ADDR: ram_addr <= s_wdata[5:0];
                        R_RAM_DATA: begin ram_d <= s_wdata[3:0]; ram_we <= 1'b1; ram_writes <= ram_writes + 16'd1; end
                        R_SRL_ADDR: srl_addr <= s_wdata[4:0];
                        R_SRL_DATA: begin srl_d <= s_wdata[3:0]; srl_ce <= 1'b1; srl_shifts <= srl_shifts + 16'd1; end
                        default: ;
                    endcase
                end
            end

            if (s_rvalid && s_rready) s_rvalid <= 1'b0;
            if (rd) begin
                s_rvalid <= 1'b1;
                s_rdata  <= 32'd0;
                if (rd_reg) begin
                    case (rd_sel)
                        R_ID:       s_rdata <= ID_WORD;
                        R_SCRATCH:  s_rdata <= scratch;
                        R_COUNT:    s_rdata <= count;
                        R_RAM_ADDR: s_rdata <= {26'd0, ram_addr};
                        R_RAM_DATA: s_rdata <= {28'd0, ram_o};
                        R_SRL_ADDR: s_rdata <= {27'd0, srl_addr};
                        R_SRL_DATA: s_rdata <= {28'd0, srl_q};
                        R_WRITES:   s_rdata <= {srl_shifts, ram_writes};
                        default:    s_rdata <= 32'd0;
                    endcase
                end
            end
        end
    end

    // ------------------------------------------------------------------ the LUT RAM
    // Four memories of 64 bits with one address, one clock and one write enable; bit k of the
    // data register goes into memory k. The address serves reading and writing alike. The
    // write happens on the clock edge at which ram_we is seen set: the edge after the one
    // that took the register write.
    (* DONT_TOUCH = "yes" *) RAM64X1S #(.INIT(64'h0)) ram0 (.O(ram_o[0]), .D(ram_d[0]), .WCLK(clk), .WE(ram_we),
        .A0(ram_addr[0]), .A1(ram_addr[1]), .A2(ram_addr[2]), .A3(ram_addr[3]), .A4(ram_addr[4]), .A5(ram_addr[5]));
    (* DONT_TOUCH = "yes" *) RAM64X1S #(.INIT(64'h0)) ram1 (.O(ram_o[1]), .D(ram_d[1]), .WCLK(clk), .WE(ram_we),
        .A0(ram_addr[0]), .A1(ram_addr[1]), .A2(ram_addr[2]), .A3(ram_addr[3]), .A4(ram_addr[4]), .A5(ram_addr[5]));
    (* DONT_TOUCH = "yes" *) RAM64X1S #(.INIT(64'h0)) ram2 (.O(ram_o[2]), .D(ram_d[2]), .WCLK(clk), .WE(ram_we),
        .A0(ram_addr[0]), .A1(ram_addr[1]), .A2(ram_addr[2]), .A3(ram_addr[3]), .A4(ram_addr[4]), .A5(ram_addr[5]));
    (* DONT_TOUCH = "yes" *) RAM64X1S #(.INIT(64'h0)) ram3 (.O(ram_o[3]), .D(ram_d[3]), .WCLK(clk), .WE(ram_we),
        .A0(ram_addr[0]), .A1(ram_addr[1]), .A2(ram_addr[2]), .A3(ram_addr[3]), .A4(ram_addr[4]), .A5(ram_addr[5]));

    // ------------------------------------------------------------ the shift registers
    // Four of 32 bits, loaded with four different words. One shift moves bit k of the data
    // register into shift register k. Nothing shifts them unless SRL_DATA is written.
    // The output of the last stage (Q31) is left unconnected on all four: a slice brings that
    // output out for one of its LUT positions only (Vivado refused the other three when it was
    // connected), and the last stage can be read like any other, at address 31.
    (* DONT_TOUCH = "yes" *) SRLC32E #(.INIT(SRL0_INIT)) srl0 (.Q(srl_q[0]), .Q31(), .A(srl_addr), .CE(srl_ce), .CLK(clk), .D(srl_d[0]));
    (* DONT_TOUCH = "yes" *) SRLC32E #(.INIT(SRL1_INIT)) srl1 (.Q(srl_q[1]), .Q31(), .A(srl_addr), .CE(srl_ce), .CLK(clk), .D(srl_d[1]));
    (* DONT_TOUCH = "yes" *) SRLC32E #(.INIT(SRL2_INIT)) srl2 (.Q(srl_q[2]), .Q31(), .A(srl_addr), .CE(srl_ce), .CLK(clk), .D(srl_d[2]));
    (* DONT_TOUCH = "yes" *) SRLC32E #(.INIT(SRL3_INIT)) srl3 (.Q(srl_q[3]), .Q31(), .A(srl_addr), .CE(srl_ce), .CLK(clk), .D(srl_d[3]));
endmodule

`default_nettype wire
