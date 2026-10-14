# AirLang — raccourcis de développement.   make help
PY ?= python3

.PHONY: help test test-py test-rust test-ruby air docs docs-check fmt fmt-check sanitize clean

help:
	@echo "make test        tous les tests (Python, Rust, Ruby)"
	@echo "make air         compile la CLI Rust (tools/air/target/release/air)"
	@echo "make docs        régénère docs/stdlib/*.md (Ruby)"
	@echo "make fmt         formate les .air (examples, tests/programs)"
	@echo "make sanitize    exécute les programmes de test avec ASan + UBSan"

test: air test-py test-rust test-ruby

test-py:
	$(PY) -m pytest -q

test-rust:
	cd tools/air && cargo test --quiet

test-ruby:
	ruby tools/test_airdoc.rb

air:
	cd tools/air && cargo build --release --quiet

docs:
	ruby tools/airdoc.rb stdlib/*.air

docs-check:
	ruby tools/airdoc.rb --check stdlib/*.air

fmt: air
	tools/air/target/release/air fmt examples tests/programs

fmt-check: air
	tools/air/target/release/air fmt --check examples tests/programs

# Mémoire : détecte accès hors limites et comportements indéfinis (les fuites sont connues : pas encore de comptage de références).
sanitize:
	@mkdir -p build/san
	@for f in tests/programs/collections tests/programs/inheritance tests/programs/loops examples/students; do \
	  n=$$(basename $$f); \
	  $(PY) -m compiler build --emit-c $$f.air > build/san/$$n.c 2>/dev/null || $(PY) -c "import sys;sys.path.insert(0,'.');from compiler import driver;print(driver.compile_to_c(open('$$f.air').read(),'$$n.air'))" > build/san/$$n.c; \
	  gcc -std=gnu11 -g -O1 -fsanitize=address,undefined -w -Iruntime build/san/$$n.c runtime/air_runtime.c runtime/air_stdlib.c -lm -o build/san/$$n && \
	  ASAN_OPTIONS=detect_leaks=0 build/san/$$n > /dev/null && echo "ok  $$n"; \
	done

clean:
	rm -rf build tools/air/target .pytest_cache
