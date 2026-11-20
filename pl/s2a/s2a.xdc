# zynq-selfmap probe design s2a — constraints. docs/s2_plan.md, section 5 and section 12, point 5.
#
# The clock: FCLK0 as the boot loader leaves it is 50 MHz on the board; the design is held to twice
# that, so that the margin does not rest on the measured value being exact.
create_clock -period 10.000 -name fclk0 [get_pins ps7/FCLKCLK[0]]

# The LUT RAM: four memories on one SLICEM site. The site is named by hand from
# pl/s2a/slicem_sites.txt; the one rule is that its column of sites is numbered 10 or above
# (pl/s2a/design.json says why). XDC takes no loop here, so the lines are written out.
#
# Vivado keeps each RAM64X1S as a cell holding one leaf, SP, and the leaf is what is placed.
# Only the site is constrained. Which of the site's four LUT positions each memory gets is
# Vivado's to say: a position given here is not kept — tried on 2026-11-20 with the position
# before the site and after it, on the leaf and on the cell around it; each time the four came
# out in Vivado's own order. The build script requires the four on four different positions of
# this site and writes down which is where (build.json); nothing else may assume it.
set_property LOC SLICE_X16Y30 [get_cells regs/ram0/SP]
set_property LOC SLICE_X16Y30 [get_cells regs/ram1/SP]
set_property LOC SLICE_X16Y30 [get_cells regs/ram2/SP]
set_property LOC SLICE_X16Y30 [get_cells regs/ram3/SP]

# The shift registers: four on the four LUT positions of a second SLICEM site, under the same rule.
# Here a position is kept, if it is given before the site: a cell given its site first is put on the
# site's first free position, and the next cell of the same site is then refused.
set_property BEL A6LUT        [get_cells regs/srl0]
set_property LOC SLICE_X34Y70 [get_cells regs/srl0]
set_property BEL B6LUT        [get_cells regs/srl1]
set_property LOC SLICE_X34Y70 [get_cells regs/srl1]
set_property BEL C6LUT        [get_cells regs/srl2]
set_property LOC SLICE_X34Y70 [get_cells regs/srl2]
set_property BEL D6LUT        [get_cells regs/srl3]
set_property LOC SLICE_X34Y70 [get_cells regs/srl3]
