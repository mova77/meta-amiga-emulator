/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Copyright (C) 2026 The meta-amiga authors */

/*
 * The colour-loop program written the way it would be written without a C compiler: all
 * assembly. It exists only as the baseline for the effort measurement in
 * docs/spikes/SPIKE-S3-m68k-toolchain.md section 9, and is built by measure.sh, not shipped.
 * Same behaviour as programs/colour-loop: same register writes, same delay.
 */
	.text
	.globl	_start
_start:
	lea	0xDFF000, %a5
	move.w	#0x7FFF, (0x9A,%a5)		/* INTENA */
	move.w	#0x7FFF, (0x9C,%a5)		/* INTREQ */
	move.w	#0x7FFF, (0x96,%a5)		/* DMACON */
again:
	move.w	#0x0F00, (0x180,%a5)		/* COLOR00 */
	moveq	#7, %d0
	bsr.w	delay
	move.w	#0x00F0, (0x180,%a5)
	moveq	#7, %d0
	bsr.w	delay
	bra	again
delay:
1:	move.w	#0xFFFF, %d1
2:	.short	0x51C9				/* dbra %d1, 2b */
	.short	2b - .
	.short	0x51C8				/* dbra %d0, 1b */
	.short	1b - .
	rts
