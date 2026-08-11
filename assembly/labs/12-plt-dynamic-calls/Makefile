CC ?= gcc
CFLAGS := -O0
RPATH := -Wl,-rpath,'$$ORIGIN'

.PHONY: all run inspect trace clean

all: libprovider.so caller.o main.o plt_demo plt_demo_now

libprovider.so: provider.c
	$(CC) $(CFLAGS) -fPIC -shared $< -o $@

caller.o: caller.c
	$(CC) $(CFLAGS) -fPIE -c $< -o $@

main.o: main.c
	$(CC) $(CFLAGS) -fPIE -c $< -o $@

plt_demo: caller.o main.o libprovider.so
	$(CC) -pie caller.o main.o -L. $(RPATH) -lprovider -o $@

plt_demo_now: caller.o main.o libprovider.so
	$(CC) -pie caller.o main.o -L. $(RPATH) -Wl,-z,now -lprovider -o $@

run: all
	./plt_demo
	./plt_demo_now

inspect: all
	@echo '== caller.o symbols =='
	nm caller.o
	@echo '== caller.o relocations =='
	readelf -Wr caller.o
	@echo '== caller.o disassembly =='
	objdump -dr caller.o
	@echo '== final sections =='
	readelf -SW plt_demo | grep -E '\.plt|\.got'
	@echo '== final relocations =='
	readelf -Wr plt_demo
	@echo '== .plt disassembly =='
	objdump -d --section=.plt plt_demo
	@echo '== call_external =='
	objdump -d plt_demo | sed -n '/<call_external>:/,/^$$/p'
	@echo '== default dynamic flags =='
	readelf -d plt_demo | grep -E 'BIND_NOW|FLAGS|JMPREL|PLTRELSZ|PLTREL' || true
	@echo '== -z now dynamic flags =='
	readelf -d plt_demo_now | grep -E 'BIND_NOW|FLAGS|JMPREL|PLTRELSZ|PLTREL' || true

trace: all
	@echo '== default binding order =='
	LD_DEBUG=bindings ./plt_demo 2>&1 | grep -E 'transferring control|external_add' | tail -5
	@echo '== eager binding order =='
	LD_DEBUG=bindings ./plt_demo_now 2>&1 | grep -E 'transferring control|external_add' | tail -5

clean:
	rm -f *.o *.so plt_demo plt_demo_now
