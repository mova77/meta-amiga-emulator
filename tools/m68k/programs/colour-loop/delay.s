/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Copyright (C) 2026 The meta-amiga authors */

/*
 * void colour_delay(unsigned int n): n + 1 passes of a 65536-iteration DBRA loop.
 *
 * Assembled by GNU as, which knows the whole 68000 instruction set; the LLVM M68k assembler
 * does not implement the DBcc family (docs/spikes/SPIKE-S3-m68k-toolchain.md section 4).
 * The encoding, from the 68000 Programmer's Reference Manual, is 0101 cccc 11001 rrr
 * followed by a 16-bit displacement relative to the address of that extension word;
 * condition F is "DBRA". Oracle 1 checks that GNU as emits exactly that.
 *
 * Clobbers d0 and d1 only, both scratch in the C ABI.
 */
	.text
	.globl	colour_delay
colour_delay:
	move.l	(4,%sp), %d0		/* first stack argument, above the return address */
1:	move.w	#0xFFFF, %d1
2:	dbra	%d1, 2b			/* the inner loop is this one instruction */
	dbra	%d0, 1b
	rts
