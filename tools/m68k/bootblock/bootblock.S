/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Copyright (C) 2026 The meta-amiga authors */

/*
 * A boot block stub: the code from offset 12 of a bootable floppy's first sector, followed
 * by the whole program blob. It copies the blob to its link address and jumps there. It
 * never returns, so it never needs the operating system's cooperation, and the machine is
 * left to the program afterwards.
 *
 * Preprocessor inputs (set by build-program.sh): BLOB, a quoted path to the raw blob, and
 * LOAD_ADDR, the address the blob was linked at. The stub is position independent: it
 * finds the blob with a PC-relative LEA, because the ROM loads the boot block wherever
 * memory happens to be free.
 *
 * Only absolute stores to the custom registers go through a register, because the M68k
 * assembler (22.1.8 and the distro 18 alike) rejects a 16-bit store to a 24-bit absolute
 * address. SPIKE-S3 section 4 has the detail.
 */
	.text
	.globl	boot
boot:
	lea	0xDFF000, %a5
	move.w	#0x7FFF, (0x9A,%a5)		/* INTENA: no interrupt may run while we copy */
	lea	(blob,%pc), %a0
	move.l	#LOAD_ADDR, %a1
	move.l	%a1, %a2
	move.w	#((blob_end - blob) / 2 - 1), %d0
1:	move.w	(%a0)+, (%a1)+
	.short	0x51C8				/* dbra d0, 1b */
	.short	1b - .
	jmp	(%a2)
blob:
	.incbin	BLOB
blob_end:
