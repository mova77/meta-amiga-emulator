/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Copyright (C) 2026 The meta-amiga authors */

/* One flat region at a known address. LOAD_ADDR is set by build-program.sh. */
SECTIONS
{
  . = LOAD_ADDR;
  .text : { *(.text.start) *(.text .text.*) }
  .rodata : { *(.rodata .rodata.*) }
  /DISCARD/ : { *(.comment) *(.eh_frame) *(.note*) *(.data .bss) }
}
