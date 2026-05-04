.PHONY: api worker

api:
	uv run api

worker:
	uv run worker
