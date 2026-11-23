// zynq-selfmap probe design s2b — the register file, and the memories it stands in front of.
// docs/s2_plan.md, sections 45 and 46; the registers and the sites are listed in pl/s2b/design.json.
//
// LUT RAM at N_SITES sites, four RAM64X1S each, behind the eight registers of s2a at the same
// offsets — so that the prober's image, which knows the design by its offsets alone, runs this
// design too. Their meaning is not s2a's:
//
//   0x00 ID        the fixed word "S2B1"
//   0x04 SITE      bits 6..0: which site a read of RAM_DATA answers for, and which site a write of
//                  RAM_DATA goes to; bit 8: a write of RAM_DATA goes to every site
//   0x08 COUNT     a counter of the clock, free running
//   0x0c RAM_ADDR  the address of every memory, six bits
//   0x10 RAM_DATA  write: one write of bit k into memory k, at the site SITE names or at every
//                  site; read: the four outputs of the site SITE names
//   0x14 —         no register: reads zero, a write does nothing
//   0x18 CHECK     read only: at the address set, over all sites, for each memory k —
//                  bit k: one site at least holds a one; bit 4+k: every site holds a one;
//                  bit 8+k: the parity of what the sites hold
//   0x1c WRITES    writes of RAM_DATA since the design was loaded (bits 15..0)
//
// What a read of RAM_DATA and of CHECK gives is taken from the memories at every clock edge and
// kept one edge: the address and the site must have stood for two edges before the read, which
// they have behind any master that takes a transfer at a time.
//
// EVERY TRANSFER IS ANSWERED, as in s2a: a write is taken whenever no response is pending and
// answered in the next cycle; a read likewise; what is no register reads zero and takes a write
// that does nothing.
//
// THE ONLY CHANGEABLE MEMORY CELLS OF THE DESIGN ARE THE 4 x N_SITES RAM64X1S BELOW, each
// instantiated by name and placed by the constraints. There is no array of registers in this
// file, and every register is kept from being turned into a shift register.
//
// EVERY MEMORY IS LOADED WITH A WORD OF ITS OWN (init_of): memory k of site s with the word of
// the number 4 s + k + 1. pl/s2b/make_s2b.py makes the same words and writes them into
// design.json; a test holds the two alike.

`default_nettype none

module s2b_regs #(
    parameter [31:0] ID_WORD = 32'h5332_4231,          // "S2B1"
    parameter integer N_SITES = 110
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
    localparam [2:0] R_ID = 3'd0, R_SITE = 3'd1, R_COUNT = 3'd2, R_RAM_ADDR = 3'd3,
                     R_RAM_DATA = 3'd4, R_NONE = 3'd5, R_CHECK = 3'd6, R_WRITES = 3'd7;

    // the word memory number n is loaded with: the same arithmetic as pl/s2b/make_s2b.py
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

    (* shreg_extract = "no" *) reg [6:0]  site;
    (* shreg_extract = "no" *) reg        every;
    (* shreg_extract = "no" *) reg [31:0] count;
    // The address is one register and one net for every memory: the four memories of a site share their write
    // address, and a slice takes them only if it is the same net at all four (Vivado made copies of this register
    // for its 2,640 loads, gave the memories of a site different copies, and then refused the sites: 2026-11-23).
    (* shreg_extract = "no", DONT_TOUCH = "yes" *) reg [5:0]  ram_addr;
    (* shreg_extract = "no" *) reg [3:0]  ram_d;
    (* shreg_extract = "no" *) reg        ram_we;
    (* shreg_extract = "no" *) reg [15:0] ram_writes;
    (* shreg_extract = "no" *) reg [3:0]  ram_o_r;
    (* shreg_extract = "no" *) reg [11:0] check_r;

    // the outputs of memory k at every site, a bus for each k
    wire [N_SITES-1:0] o0, o1, o2, o3;
    wire [N_SITES-1:0] we;

    // ---------------------------------------------------------------- the two channels
    wire wr = s_awvalid && s_wvalid && !s_bvalid;
    assign s_awready = wr;
    assign s_wready  = wr;
    assign s_bresp   = 2'b00;

    wire rd = s_arvalid && !s_rvalid;
    assign s_arready = rd;
    assign s_rresp   = 2'b00;

    wire        wr_reg = wr && (s_awaddr[15:5] == 11'd0) && (s_awaddr[1:0] == 2'b00) && (s_wstrb == 4'hF);
    wire [2:0]  wr_sel = s_awaddr[4:2];
    wire        rd_reg = (s_araddr[15:5] == 11'd0) && (s_araddr[1:0] == 2'b00);
    wire [2:0]  rd_sel = s_araddr[4:2];

    wire        a_site = site < N_SITES;               // the number names a site there is
    wire [3:0]  here = a_site ? {o3[site], o2[site], o1[site], o0[site]} : 4'd0;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            s_bvalid   <= 1'b0;
            s_rvalid   <= 1'b0;
            s_rdata    <= 32'd0;
            site       <= 7'd0;
            every      <= 1'b0;
            count      <= 32'd0;
            ram_addr   <= 6'd0;
            ram_d      <= 4'd0;
            ram_we     <= 1'b0;
            ram_writes <= 16'd0;
            ram_o_r    <= 4'd0;
            check_r    <= 12'd0;
        end else begin
            count   <= count + 32'd1;
            ram_we  <= 1'b0;                             // one clock, and only when asked
            ram_o_r <= here;
            check_r <= {^o3, ^o2, ^o1, ^o0, &o3, &o2, &o1, &o0, |o3, |o2, |o1, |o0};

            if (s_bvalid && s_bready) s_bvalid <= 1'b0;
            if (wr) begin
                s_bvalid <= 1'b1;
                if (wr_reg) begin
                    case (wr_sel)
                        R_SITE:     begin site <= s_wdata[6:0]; every <= s_wdata[8]; end
                        R_RAM_ADDR: ram_addr <= s_wdata[5:0];
                        R_RAM_DATA: begin ram_d <= s_wdata[3:0]; ram_we <= 1'b1; ram_writes <= ram_writes + 16'd1; end
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
                        R_SITE:     s_rdata <= {23'd0, every, 1'b0, site};
                        R_COUNT:    s_rdata <= count;
                        R_RAM_ADDR: s_rdata <= {26'd0, ram_addr};
                        R_RAM_DATA: s_rdata <= {28'd0, ram_o_r};
                        R_CHECK:    s_rdata <= {20'd0, check_r};
                        R_WRITES:   s_rdata <= {16'd0, ram_writes};
                        default:    s_rdata <= 32'd0;
                    endcase
                end
            end
        end
    end

    // ------------------------------------------------------------------ the LUT RAM
    // At every site four memories of 64 bits with the one address and the one clock; bit k of
    // the data register goes into memory k of the site that is written — the one SITE names,
    // or every one. The write happens on the clock edge at which ram_we is seen set.
    genvar s;
    generate
        for (s = 0; s < N_SITES; s = s + 1) begin : at
            assign we[s] = ram_we && (every || site == s);
            (* DONT_TOUCH = "yes" *) RAM64X1S #(.INIT(init_of(4 * s + 1))) ram0 (.O(o0[s]), .D(ram_d[0]), .WCLK(clk), .WE(we[s]),
                .A0(ram_addr[0]), .A1(ram_addr[1]), .A2(ram_addr[2]), .A3(ram_addr[3]), .A4(ram_addr[4]), .A5(ram_addr[5]));
            (* DONT_TOUCH = "yes" *) RAM64X1S #(.INIT(init_of(4 * s + 2))) ram1 (.O(o1[s]), .D(ram_d[1]), .WCLK(clk), .WE(we[s]),
                .A0(ram_addr[0]), .A1(ram_addr[1]), .A2(ram_addr[2]), .A3(ram_addr[3]), .A4(ram_addr[4]), .A5(ram_addr[5]));
            (* DONT_TOUCH = "yes" *) RAM64X1S #(.INIT(init_of(4 * s + 3))) ram2 (.O(o2[s]), .D(ram_d[2]), .WCLK(clk), .WE(we[s]),
                .A0(ram_addr[0]), .A1(ram_addr[1]), .A2(ram_addr[2]), .A3(ram_addr[3]), .A4(ram_addr[4]), .A5(ram_addr[5]));
            (* DONT_TOUCH = "yes" *) RAM64X1S #(.INIT(init_of(4 * s + 4))) ram3 (.O(o3[s]), .D(ram_d[3]), .WCLK(clk), .WE(we[s]),
                .A0(ram_addr[0]), .A1(ram_addr[1]), .A2(ram_addr[2]), .A3(ram_addr[3]), .A4(ram_addr[4]), .A5(ram_addr[5]));
        end
    endgenerate
endmodule

`default_nettype wire
