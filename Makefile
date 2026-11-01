PY ?= python3

.PHONY: cases text naive score site all test serve clean

all: cases text naive site

cases:
	$(PY) -m crtest.gen --out cases

text:
	$(PY) -m crtest.dump_text --cases cases

naive:
	$(PY) -m crtest.extract_naive --cases cases --out results/naive_text.json
	$(PY) -m crtest.score --cases cases --pred results/naive_text.json

score:
	for f in results/*.json; do case $$f in *.scored.json) ;; *) $(PY) -m crtest.score --cases cases --pred $$f ;; esac; done

site:
	$(PY) -m crtest.site --cases cases --results results --out site/dist

test:
	$(PY) -m pytest -q tests

serve:
	$(PY) -m crtest.server --root . --store submissions --port 8765

clean:
	rm -rf site/dist
