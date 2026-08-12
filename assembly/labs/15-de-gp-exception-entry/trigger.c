#define _GNU_SOURCE
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ucontext.h>
#include <ucontext.h>

static volatile sig_atomic_t seen_fpe;
static volatile sig_atomic_t seen_segv;

static void dump_context(const char *name, int sig, siginfo_t *si, void *opaque)
{
    ucontext_t *uc = opaque;
    greg_t *g = uc->uc_mcontext.gregs;

    printf("%s: signal=%d code=%d RIP=%#llx RSP=%#llx EFL=%#llx\n",
           name, sig, si->si_code,
           (unsigned long long)g[REG_RIP],
           (unsigned long long)g[REG_RSP],
           (unsigned long long)g[REG_EFL]);
}

static void handler(int sig, siginfo_t *si, void *opaque)
{
    if (sig == SIGFPE) {
        seen_fpe = 1;
        dump_context("#DE candidate", sig, si, opaque);
        /* idivq below is exactly 3 bytes: 48 f7 f9. */
        ((ucontext_t *)opaque)->uc_mcontext.gregs[REG_RIP] += 3;
        return;
    }

    if (sig == SIGSEGV) {
        seen_segv = 1;
        dump_context("#GP candidate", sig, si, opaque);
        /* mov %rax,%ds below is exactly 2 bytes: 8e d8. */
        ((ucontext_t *)opaque)->uc_mcontext.gregs[REG_RIP] += 2;
        return;
    }

    _Exit(128 + sig);
}

__attribute__((noinline)) static void trigger_de(void)
{
    asm volatile(
        "mov $1, %%rax\n\t"
        "xor %%rdx, %%rdx\n\t"
        "xor %%ecx, %%ecx\n\t"
        "idivq %%rcx\n\t"
        : : : "rax", "rcx", "rdx", "cc");
}

__attribute__((noinline)) static void trigger_gp(void)
{
    asm volatile(
        "mov $0xffff, %%eax\n\t"
        "mov %%ax, %%ds\n\t"
        : : : "rax", "memory");
}

int main(void)
{
    struct sigaction sa;
    memset(&sa, 0, sizeof(sa));
    sa.sa_sigaction = handler;
    sa.sa_flags = SA_SIGINFO;
    sigemptyset(&sa.sa_mask);

    if (sigaction(SIGFPE, &sa, NULL) || sigaction(SIGSEGV, &sa, NULL)) {
        perror("sigaction");
        return 1;
    }

    trigger_de();
    trigger_gp();

    printf("seen_fpe=%d seen_segv=%d\n", seen_fpe, seen_segv);
    return !(seen_fpe && seen_segv);
}
