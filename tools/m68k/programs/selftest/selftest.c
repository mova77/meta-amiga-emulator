/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Copyright (C) 2026 The meta-amiga authors */

/*
 * C that stresses the M68k backend the way a measurement harness would: byte stores
 * through a pointer, 16-bit loads with sign extension, shifts by more than the 1..8 an
 * immediate shift can encode, bit tests, a loop with a data-dependent exit, a switch.
 * No multiply, divide or modulo: the 68000 has no 32-bit forms of them, the compiler would
 * call a runtime library, and there is none (SPIKE-S3 section 4).
 *
 * It does nothing observable on its own. oracle/observe_blob.py selftest runs the blob under
 * an independent 68000 model and compares RESULTS with what oracle/expected_selftest.py
 * computes in Python.
 */

#define RESULTS ((volatile unsigned int *)0x00050000u)
#define TEXT    ((volatile char *)0x00050100u)

#define NOINLINE __attribute__((noinline))

/* Inputs are read through volatile so that -O2 cannot fold the whole program to constants. */
static const volatile unsigned int in_hex = 0x00DFF180u;
static const volatile unsigned int in_pop = 0xF0F0A5C3u;
static const volatile unsigned int in_xs = 0xDEADBEEFu;
static const volatile unsigned int in_sel = 5u;
static const volatile int in_count = 7;
static const short samples[] = { -1, 2, -3, 1000, 0x7FFF, -0x8000, 5 };
static const short *const volatile in_samples = samples;

/* Eight upper-case hex digits and a NUL, most significant first. */
NOINLINE static void format_hex32(unsigned int value, volatile char *out)
{
    static const char digits[] = "0123456789ABCDEF";
    for (int i = 7; i >= 0; i--) {
        out[i] = digits[value & 15u];
        value >>= 4;
    }
    out[8] = 0;
}

NOINLINE static int sum_samples(const short *p, int n)
{
    int s = 0;
    for (int i = 0; i < n; i++)
        s += p[i]; /* each element sign-extends */
    return s;
}

NOINLINE static unsigned int popcount32(unsigned int v)
{
    unsigned int n = 0;
    while (v) { /* exit depends on the data */
        n += v & 1u;
        v >>= 1;
    }
    return n;
}

/* Marsaglia xorshift32: shifts by 13, 17 and 5, two of which exceed an immediate's range. */
NOINLINE static unsigned int xorshift32(unsigned int x)
{
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    return x;
}

NOINLINE static int classify(unsigned int v)
{
    switch (v & 7u) {
    case 0: return 10;
    case 1: return 21;
    case 2: return 32;
    case 3: return 43;
    case 5: return 65;
    case 7: return 87;
    default: return -1;
    }
}

void run_selftest(void)
{
    format_hex32(in_hex, TEXT);
    RESULTS[0] = (unsigned int)sum_samples(in_samples, in_count);
    RESULTS[1] = popcount32(in_pop);
    RESULTS[2] = xorshift32(in_sel - 4u);
    RESULTS[3] = xorshift32(in_xs);
    RESULTS[4] = (unsigned int)classify(in_sel) + 1000u;
    RESULTS[5] = (unsigned int)classify(in_sel - 1u);
    RESULTS[6] = 0xA5A5A5A5u; /* last: proves the run got this far */
}
