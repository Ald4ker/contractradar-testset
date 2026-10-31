PY ?= python3

.PHONY: cases naive score site all test clean

all: cases naive site

cases:
	$(PY) -m crtest.gen --out cases

naive:
	$(PY) -m crtest.extract_naive --cases cases --out results/naive_text.json
	$(PY) -m crtest.score --cases cases --pred results/naive_text.json

score:
	for f in results/*.json; do case $$f in *.scored.json) ;; *) $(PY) -m crtest.score --cases cases --pred $$f ;; esac; done

site:
	$(PY) -m crtest.site --cases cases --results results --out site/dist

test:
	$(PY) -m pytest -q tests

clean:
	rm -rf site/dist
