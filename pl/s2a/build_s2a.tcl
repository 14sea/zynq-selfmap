# Build the probe design s2a: synthesis, placement, routing, the bitstream, and a record.
#
#   vivado -mode batch -source build_s2a.tcl -tclargs <outdir>
#
# What this script asks Vivado beyond building (docs/s2_plan.md, section 12, point 5), and it stops
# with an error unless each holds:
#   1. the design has exactly eight memory primitives — the four of the LUT RAM and the four shift
#      registers — and no other RAM, shift register, block RAM or FIFO, inferred or instantiated;
#   2. each of the eight sits on the site the constraints name — the shift registers on the LUT positions they
#      name as well, the four memories of the LUT RAM on four different positions, which the record states
#      (Vivado does not keep a position given to them: s2a.xdc);
#   3. every net is routed, and setup and hold timing are met.
# It writes the bitstream and the record, and nothing else that describes the design: no logic
# location file, no mask file, no readback file, no report. The bitstream is an opaque file to
# everything in this repository; its hash says which design was loaded.

set outdir [lindex $argv 0]
set part   xc7z010clg400-1
set here   [file dirname [file normalize [info script]]]
set repo   [file dirname [file dirname $here]]
file mkdir $outdir

# cell -> {site, LUT position}: as in s2a.xdc and in design.json (a test holds the three alike). `any`: the position
# is not constrained; the four cells of that site must come out on four different ones.
set placed {
    regs/ram0 {SLICE_X16Y30 any}    regs/ram1 {SLICE_X16Y30 any}    regs/ram2 {SLICE_X16Y30 any}    regs/ram3 {SLICE_X16Y30 any}
    regs/srl0 {SLICE_X34Y70 A6LUT}  regs/srl1 {SLICE_X34Y70 B6LUT}  regs/srl2 {SLICE_X34Y70 C6LUT}  regs/srl3 {SLICE_X34Y70 D6LUT}
}

set srcs [list $here/s2a_top.v $here/s2a_regs.v $repo/imported/fabricmap/carrier_axi3_lite.v]
create_project -in_memory -part $part
add_files -norecurse $srcs
add_files -fileset constrs_1 -norecurse $here/s2a.xdc

# no shift register is made of flip-flops, anywhere; the hierarchy is kept so that the cells have their names
synth_design -top s2a_top -part $part -flatten_hierarchy none -no_srlextract
opt_design

# ---- 1. the memory primitives of the design, whatever made them
# Leaf cells only. Vivado keeps RAM64X1S as a cell that holds one leaf (RAMS64E, named SP); the leaf is what is
# placed. So a memory leaf must be one of the eight instantiated cells or the one leaf inside one of them.
proc memory_cells {} {
    set out {}
    foreach c [get_cells -hierarchical -filter {IS_PRIMITIVE && PRIMITIVE_LEVEL != MACRO}] {
        set ref [get_property REF_NAME $c]
        if {[regexp {^(RAM|SRL|FIFO|ROM)} $ref]} { lappend out [list [get_property NAME $c] $ref] }
    }
    return [lsort $out]
}
proc leaf_of {cell mem} {
    set found {}
    foreach m $mem {
        set name [lindex $m 0]
        if {$name eq $cell || [file dirname $name] eq $cell} { lappend found $name }
    }
    if {[llength $found] != 1} { error "$cell: [llength $found] memory leaf cell(s): $found" }
    return [lindex $found 0]
}
set mem [memory_cells]
set leaves {}
foreach {cell where} $placed { lappend leaves [leaf_of $cell $mem] }
if {[llength $mem] != [llength $leaves]} {
    error "the memory primitives of the design are not the eight that were instantiated: $mem"
}

place_design
route_design

# ---- 1 again, after everything that could have changed the netlist
if {[memory_cells] ne $mem} { error "the memory primitives changed during implementation: [memory_cells]" }

# ---- 2. where the eight are
set where_json {}
set misplaced {}
foreach {cell where} $placed {
    set c [get_cells [leaf_of $cell $mem]]
    if {[llength $c] != 1} { error "$cell: [llength $c] cells of that name" }
    set loc [get_property LOC $c]
    set bel [lindex [split [get_property BEL $c] .] end]
    if {$loc ne [lindex $where 0] || ([lindex $where 1] ne "any" && $bel ne [lindex $where 1])} {
        lappend misplaced "$cell is on $loc $bel, not on [lindex $where 0] [lindex $where 1]"
    }
    if {![regexp {^[ABCD]6LUT$} $bel] || [info exists taken($loc,$bel)]} {
        lappend misplaced "$cell is on $loc $bel: not a LUT position of its own"
    }
    set taken($loc,$bel) $cell
    lappend where_json "    \"$cell\": {\"site\": \"$loc\", \"bel\": \"$bel\", \"leaf\": \"[get_property NAME $c]\", \"primitive\": \"[get_property REF_NAME $c]\"}"
}
if {[llength $misplaced] != 0} { error "not where the constraints put them: [join $misplaced {; }]" }

# ---- 3. routed, and in time
set unrouted [get_nets -hierarchical -quiet -filter {ROUTE_STATUS == UNROUTED || ROUTE_STATUS == PARTIAL || ROUTE_STATUS == CONFLICTS || ROUTE_STATUS == ANTENNAS}]
if {[llength $unrouted] != 0} { error "[llength $unrouted] net(s) not routed: [lrange $unrouted 0 4]" }
set setup [get_timing_paths -max_paths 1 -nworst 1 -setup]
set hold  [get_timing_paths -max_paths 1 -nworst 1 -hold]
if {[llength $setup] != 1 || [llength $hold] != 1} { error "no timing path found: the clock constraint did not take" }
set wns [get_property SLACK $setup]
set whs [get_property SLACK $hold]
if {$wns < 0 || $whs < 0} { error "timing is not met: setup slack $wns ns, hold slack $whs ns" }

write_bitstream -force $outdir/s2a.bit

# ---- the record
set src_json {}
foreach f [concat $srcs [list $here/s2a.xdc $here/build_s2a.tcl]] {
    set rel [string range $f [expr {[string length $repo] + 1}] end]
    lappend src_json "    \"$rel\": \"[lindex [exec sha256sum $f] 0]\""
}
set fh [open $outdir/build.json w]
puts $fh "{"
puts $fh " \"schema\": \"probe_design_build\","
puts $fh " \"schema_version\": 1,"
puts $fh " \"name\": \"s2a\","
puts $fh " \"part\": \"$part\","
puts $fh " \"vivado\": \"[version -short]\","
puts $fh " \"memory_primitives\": {"
puts $fh [join $where_json ",\n"]
puts $fh " },"
puts $fh " \"setup_slack_ns\": $wns,"
puts $fh " \"hold_slack_ns\": $whs,"
puts $fh " \"clock_period_ns\": [get_property PERIOD [get_clocks fclk0]],"
puts $fh " \"bitstream\": {\"file\": \"s2a.bit\", \"sha256\": \"[lindex [exec sha256sum $outdir/s2a.bit] 0]\", \"bytes\": [file size $outdir/s2a.bit]},"
puts $fh " \"sources\": {"
puts $fh [join $src_json ",\n"]
puts $fh " }"
puts $fh "}"
close $fh
puts "S2A BUILD OK -> $outdir/s2a.bit"
