/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Copyright (C) 2026 The meta-amiga authors */

/*
 * The smallest program that proves a 68000 is running our code: set the background
 * colour and keep it alive. It writes COLOR00 from C, calls an assembly delay, writes a
 * second colour and repeats, so the screen flips between two colours on real hardware
 * and the write sequence is observable from outside on anything that models the bus.
 *
 * Register addresses are from the Amiga Hardware Reference Manual, appendix A.
 */

#define CUSTOM_BASE 0x00DFF000u
#define DMACON  0x096u /* write: DMA control, bit 15 = set/clear */
#define INTENA  0x09Au /* write: interrupt enable, bit 15 = set/clear */
#define INTREQ  0x09Cu /* write: interrupt request, bit 15 = set/clear */
#define COLOR00 0x180u /* background colour, 0x0RGB */

#define CUSTOM16(off) (*(volatile unsigned short *)(CUSTOM_BASE + (off)))

#ifndef COLOUR_A
#define COLOUR_A 0x0F00u /* red */
#endif
#ifndef COLOUR_B
#define COLOUR_B 0x00F0u /* green */
#endif
#ifndef DELAY_OUTER
#define DELAY_OUTER 8u /* ~0.7 s per half period at 7.09 MHz, 10 cycles per DBRA */
#endif

/*
 * delay.s: burns (outer + 1) * 65536 DBRA iterations. Hand-written assembly, because its
 * cycle count is the point; the argument is a 32-bit long on the stack (C ABI).
 */
extern void colour_delay(unsigned int outer);

void c_main(void)
{
    /* Take the machine over: nothing may interrupt or steal the bus from here on. */
    CUSTOM16(INTENA) = 0x7FFFu;
    CUSTOM16(INTREQ) = 0x7FFFu;
    CUSTOM16(DMACON) = 0x7FFFu;

    for (;;) {
        CUSTOM16(COLOR00) = COLOUR_A;
        colour_delay(DELAY_OUTER - 1u);
        CUSTOM16(COLOR00) = COLOUR_B;
        colour_delay(DELAY_OUTER - 1u);
    }
}
