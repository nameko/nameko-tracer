coverage:
	coverage run --concurrency=eventlet --source nameko_entrypoint_logger -m pytest tests -x
	coverage report -m
