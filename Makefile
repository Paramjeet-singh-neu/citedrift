PYTHON ?= python3

.PHONY: collect test

collect:
	$(PYTHON) -m citedrift.collect

test:
	$(PYTHON) -m unittest discover -s tests -v
