test:
	coverage run --concurrency=eventlet --source nameko_entrypoint_logger.py -m pytest test_nameko_entrypoint_logger.py -x
	coverage report -m
