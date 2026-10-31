/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Copyright (C) 2026 The meta-amiga authors */

/* Entry point, placed first by link.ld so the blob can be entered at its load address. */
	.section .text.start,"ax",@progbits
	.globl	_start
_start:
	bsr.w	c_main
1:	bra	1b			/* c_main never returns; park if it ever does */
