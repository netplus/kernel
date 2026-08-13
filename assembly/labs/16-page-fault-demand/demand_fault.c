#define _GNU_SOURCE
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <unistd.h>

static long minflt(void)
{
    struct rusage ru;
    if (getrusage(RUSAGE_SELF, &ru) != 0) {
        perror("getrusage");
        exit(EXIT_FAILURE);
    }
    return ru.ru_minflt;
}

static int resident(void *addr, size_t len)
{
    unsigned char vec = 0;
    if (mincore(addr, len, &vec) != 0) {
        perror("mincore");
        exit(EXIT_FAILURE);
    }
    return !!(vec & 1);
}

__attribute__((noinline)) static void faulting_store(volatile unsigned char *p)
{
    *p = 0x5a;
}

int main(void)
{
    long page_size = sysconf(_SC_PAGESIZE);
    if (page_size <= 0) {
        fprintf(stderr, "invalid page size\n");
        return EXIT_FAILURE;
    }

    unsigned char *p = mmap(NULL, (size_t)page_size,
                            PROT_READ | PROT_WRITE,
                            MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (p == MAP_FAILED) {
        perror("mmap");
        return EXIT_FAILURE;
    }

    long before = minflt();
    int resident_before = resident(p, (size_t)page_size);

    faulting_store(p);

    long after = minflt();
    int resident_after = resident(p, (size_t)page_size);

    printf("page_size=%ld\n", page_size);
    printf("mapping=%p\n", (void *)p);
    printf("resident_before=%d\n", resident_before);
    printf("resident_after=%d\n", resident_after);
    printf("minor_fault_delta=%ld\n", after - before);
    printf("value=0x%02x\n", p[0]);

    if (munmap(p, (size_t)page_size) != 0) {
        perror("munmap");
        return EXIT_FAILURE;
    }
    return 0;
}
