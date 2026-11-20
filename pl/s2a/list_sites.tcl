# The one thing this project asks Vivado about the device itself: the names of its SLICEM sites
# (docs/s2_plan.md, section 12, point 5). A LUT RAM can be placed on no other kind of site, and there
# is no other source for the name of a site than Vivado's model of the part. Nothing else is asked:
# no tile, no column type, no coordinate but the one in the name.
#
#   vivado -mode batch -source list_sites.tcl -tclargs <out.txt>
#
# The device model is only loaded with a design, so an empty module is synthesised first.
set out  [lindex $argv 0]
set part xc7z010clg400-1
set here [file dirname [file normalize [info script]]]
set stub [file join [file dirname $out] s2a_stub.v]
set fh [open $stub w]
puts $fh "module s2a_stub (input wire a, output wire y); assign y = a; endmodule"
close $fh
create_project -in_memory -part $part
add_files -norecurse $stub
synth_design -top s2a_stub -part $part -mode out_of_context
set names {}
foreach s [get_sites -filter {SITE_TYPE == SLICEM}] { lappend names [get_property NAME $s] }
if {[llength $names] == 0} { error "no SLICEM site found: the filter is wrong" }
proc by_xy {a b} {
    regexp {^SLICE_X(\d+)Y(\d+)$} $a -> ax ay
    regexp {^SLICE_X(\d+)Y(\d+)$} $b -> bx by
    if {$ax != $bx} { return [expr {$ax - $bx}] }
    return [expr {$ay - $by}]
}
foreach n $names { if {![regexp {^SLICE_X\d+Y\d+$} $n]} { error "a SLICEM site with an unexpected name: $n" } }
set fh [open $out w]
puts $fh "# SLICEM sites of $part, as Vivado [version -short] names them; [llength $names] sites. Written by pl/s2a/list_sites.tcl."
foreach n [lsort -command by_xy $names] { puts $fh $n }
close $fh
file delete $stub
puts "LIST OK: [llength $names] SLICEM sites -> $out"
