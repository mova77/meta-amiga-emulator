/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Copyright (C) 2026 The meta-amiga authors */

/*
 * The instruction kernel for oracle 1 (encodings against the 68000 Programmer's Reference
 * Manual) and oracle 3 (behaviour under an independent CPU model).
 *
 * It is a program as well as a table: entered with a0 = $100 and sp = $8000 it ends parked
 * at `done` with the registers kernel.expected states. Covers MOVE in several effective
 * address modes, MOVEQ, ADD, ADDQ, LEA, Bcc, DBRA, MOVEM both ways, JSR and RTS.
 *
 * It is assembled by GNU as (check_encodings.py); every instruction is the real mnemonic.
 * Branches carry explicit sizes: GNU as encodes an unsized Bcc, BRA or BSR as the word form
 * whatever the distance, and the expected encodings are the short ones.
 */
	.text
	.globl	kernel
kernel:
	moveq	#9, %d4
	move.w	#0x00F0, %d0
	move.l	%d0, %d2
	move.w	%d0, %d1
	add.w	%d1, %d0
	add.l	%d2, %d0
	addq.l	#1, %d3
	move.l	%d0, -(%sp)
	move.l	(%sp)+, %d3
	lea	(8,%a0), %a1
	moveq	#0, %d5
loop:
	add.w	%d4, %d5
	dbra	%d4, loop
	cmp.l	%d1, %d1
	beq.s	skip
	move.w	#0xDEAD, %d7
skip:
	bne.s	skip2
	moveq	#1, %d7
skip2:
	movem.l	%d0-%d2/%a0, -(%sp)
	moveq	#0, %d0
	moveq	#0, %d1
	moveq	#0, %d2
	move.l	%d0, %a0
	movem.l	(%sp)+, %d0-%d2/%a0
	lea	(sub,%pc), %a1
	jsr	(%a1)
done:
	bra.s	done
sub:
	move.w	#0xBEEF, %d6
	rts
