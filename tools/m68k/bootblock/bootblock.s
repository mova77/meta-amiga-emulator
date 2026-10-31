/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Copyright (C) 2026 The meta-amiga authors */

/*
 * A boot block stub: the code from offset 12 of a bootable floppy's first sector. The program
 * blob follows it directly (build-program.sh appends it), and the stub copies the blob to its
 * link address and jumps there. It never returns, so it never needs the operating system's
 * cooperation, and the machine is left to the program afterwards.
 *
 * Assembled by GNU as with two symbols defined on the command line (build-program.sh):
 * LOAD_ADDR, the address the blob was linked at, and BLOB_WORDS, the blob's length in 16-bit
 * words. The stub is position independent: it finds the blob with a PC-relative LEA, because
 * the ROM loads the boot block wherever memory happens to be free.
 */
	.text
	.globl	boot
boot:
	move.w	#0x7FFF, 0xDFF09A		/* INTENA: no interrupt may run while we copy */
	lea	(blob,%pc), %a0
	move.l	#LOAD_ADDR, %a1
	move.l	%a1, %a2
	move.w	#(BLOB_WORDS - 1), %d0
1:	move.w	(%a0)+, (%a1)+
	dbra	%d0, 1b
	jmp	(%a2)
blob:						/* the blob starts here */
