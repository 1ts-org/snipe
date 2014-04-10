all:
	nosetests

coverage:
	nosetests --with-coverage
	python-coverage html

clean:
	$(RM) -r .coverage profiling htmlcov

install:

.PHONY: all clean install
