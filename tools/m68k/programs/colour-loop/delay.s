/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Copyright (C) 2026 The meta-amiga authors */

/*
 * void colour_delay(unsigned int n): n + 1 passes of a 65536-iteration DBRA loop.
 *
 * DBRA is encoded by hand with .short. The M68k backend does not implement the DBcc
 * family: neither the assembler nor the disassembler knows it (docs/spikes/
 * SPIKE-S3-m68k-toolchain.md section 4). The encoding is from the 68000 Programmer's
 * Reference Manual: DBcc is 0101 cccc 11001 rrr followed by a 16-bit displacement that
 * is relative to the address of that extension word; condition F is "DBRA".
 *
 * Clobbers d0 and d1 only, both scratch in the C ABI.
 */
	.text
	.globl	colour_delay
colour_delay:
	move.l	(4,%sp), %d0		/* first stack argument, above the return address */
1:	move.w	#0xFFFF, %d1
2:	.short	0x51C9			/* dbra d1, 2b: the loop is this one instruction */
	.short	2b - .			/* displacement from this word back to 2b: -2 */
	.short	0x51C8			/* dbra d0, 1b */
	.short	1b - .
	rts
