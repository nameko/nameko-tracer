test: flake8 pylint pytest

flake8:
	flake8 nameko_entrypoint_logger tests

pylint:
	pylint nameko_entrypoint_logger -E

pytest:
	coverage run --concurrency=eventlet --source nameko_entrypoint_logger --branch -m pytest tests
	coverage report --show-missing --fail-under=100
