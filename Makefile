VBIN=venv/bin
FLAKE8=$(VBIN)/flake8
NOSE=$(VBIN)/nosetests
MYPY=$(VBIN)/mypy
COVERAGE=$(VBIN)/coverage

NOSETESTS=TZ=GMT $(NOSE) -v -w tests
TEST=

all check: flake8 mypy nosetests 

flake8: venv
	$(FLAKE8) rooster.py setup.py snipe.py swearing.py snipe tests

nosetests: venv
	$(NOSETESTS) --processes=8 --process-timeout=300 $(TEST)

mypy: venv
	$(MYPY) --ignore-missing-imports rooster.py setup.py swearing.py snipe tests

coverage: venv
	$(COVERAGE) erase
	$(NOSETESTS) --with-coverage $(TEST)
	$(COVERAGE) html

clean::
	$(RM) -r .coverage profiling htmlcov parser.out snipe/parser.out tests/parser.out

venv:	venv-stamp

venv-stamp:
	$(MAKE) venv-clean
	python3 -m venv venv
	venv/bin/pip install -U pip
	venv/bin/pip install -r ./requirements.txt
	venv/bin/pip install mypy flake8 nose coverage
	venv/bin/pip install -e .
	touch venv-stamp

venv-clean:
	$(RM) -rf venv venv-stamp

clean:: venv-clean

install:

.PHONY: all clean install check flake8 nosetests venv venv-clean
