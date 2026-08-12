#define _GNU_SOURCE
#include <errno.h>
#include <stdio.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <unistd.h>

struct syscall_state {
    unsigned long rflags_before;
    unsigned long rcx_after;
    unsigned long r11_after;
    unsigned long rflags_after;
};

long raw_getpid(void);
long raw_invalid_syscall(void);
void *raw_mmap(void *addr, size_t len, int prot, int flags, int fd, off_t off);
void raw_getpid_state(struct syscall_state *state, long *result);

int main(void)
{
    long libc_pid = (long)getpid();
    long libc_syscall_pid = syscall(SYS_getpid);
    long raw_pid = raw_getpid();
    long raw_bad = raw_invalid_syscall();

    errno = 0;
    long libc_bad = syscall(0x7fffffffL);
    int libc_errno = errno;

    void *p = raw_mmap(NULL, 4096, PROT_READ | PROT_WRITE,
                       MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    int mmap_ok = ((long)p >= 0);
    if (mmap_ok) {
        *(volatile unsigned char *)p = 0x5a;
        munmap(p, 4096);
    }

    struct syscall_state state = {0};
    long state_pid = -1;
    raw_getpid_state(&state, &state_pid);

    printf("getpid: libc=%ld libc_syscall=%ld raw=%ld state=%ld\n",
           libc_pid, libc_syscall_pid, raw_pid, state_pid);
    printf("invalid: raw=%ld libc=%ld errno=%d\n",
           raw_bad, libc_bad, libc_errno);
    printf("raw_mmap: %s\n", mmap_ok ? "success" : "failure");
    printf("state: rflags_before=0x%lx rcx_after=0x%lx "
           "r11_after=0x%lx rflags_after=0x%lx\n",
           state.rflags_before, state.rcx_after, state.r11_after,
           state.rflags_after);

    return !((libc_pid == libc_syscall_pid) &&
             (libc_pid == raw_pid) &&
             (libc_pid == state_pid) &&
             (raw_bad == -ENOSYS) &&
             (libc_bad == -1) &&
             (libc_errno == ENOSYS) && mmap_ok);
}
