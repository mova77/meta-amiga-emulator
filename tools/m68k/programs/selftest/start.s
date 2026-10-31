/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Copyright (C) 2026 The meta-amiga authors */

	.section .text.start,"ax",@progbits
	.globl	_start
_start:
	bsr.w	run_selftest
1:	bra	1b			/* park */
