PYTHON ?= python3
KERNEL ?=
DISASM ?=

.PHONY: help test check-source check-disassembly

help:
	@printf '%s\n' \
	  'make test' \
	  '    Run the source-contract and objdump-checker fixture tests.' \
	  'make check-source KERNEL=/path/to/linux-5.10' \
	  '    Check startup_32 and verify_cpu source contracts in a v5.10 tree.' \
	  'make check-disassembly DISASM=/path/to/combined-objdump.txt' \
	  '    Check machine-code contracts. DISASM must contain startup_32 and verify_cpu.'

test:
	$(PYTHON) test_verify_startup32_contract.py
	$(PYTHON) test_verify_startup32_disassembly.py

check-source:
	@test -n "$(KERNEL)" || { echo 'KERNEL=/path/to/linux-5.10 is required' >&2; exit 2; }
	$(PYTHON) verify_startup32_contract.py "$(KERNEL)"

check-disassembly:
	@test -n "$(DISASM)" || { echo 'DISASM=/path/to/combined-objdump.txt is required' >&2; exit 2; }
	$(PYTHON) verify_startup32_disassembly.py "$(DISASM)"
