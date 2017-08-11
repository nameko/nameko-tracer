test: flake8 pylint pytest

flake8:
	flake8 nameko_tracer tests

pylint:
	pylint nameko_tracer -E

pytest:
	coverage run --concurrency=eventlet --source nameko_tracer --branch -m pytest tests
	coverage report --show-missing --fail-under=100
