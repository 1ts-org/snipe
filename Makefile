all:
	nosetests3

coverage:
	nosetests3 --with-coverage
	python3-coverage html

clean:
	$(RM) -r .coverage profiling htmlcov

install:

.PHONY: all clean install
