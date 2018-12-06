NOSE=nosetests3
NOSETESTS=TZ=GMT $(NOSE) -v -w tests

all check: flake8 mypy nosetests 

flake8:
	flake8 rooster.py setup.py snipe.py swearing.py snipe tests

nosetests:
	$(NOSETESTS) --processes=8 --process-timeout=300

mypy:
	mypy --ignore-missing-imports rooster.py setup.py swearing.py snipe tests

coverage:
	python3-coverage erase
	$(NOSETESTS) --with-coverage
	python3-coverage html

clean:
	$(RM) -r .coverage profiling htmlcov parser.out tests/parser.out

install:

.PHONY: all clean install check flake8 nosetests
