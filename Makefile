.PHONY: up down logs migrate revision test lint format seed shell enrich domain-age demo demo-replace demo-export

up:
	docker compose up --build

down:
	docker compose down -v

logs:
	docker compose logs -f api worker

migrate:  ## migrations also run automatically when the api starts
	docker compose run --rm api alembic upgrade head

revision:
	docker compose run --rm api alembic revision --autogenerate -m "$(m)"

test:
	docker compose run --rm api pytest -q

lint:
	docker compose run --rm api sh -c "ruff check . && ruff format --check . && mypy src"

format:
	docker compose run --rm api sh -c "ruff format . && ruff check --fix ."

enrich:  ## read websites with Claude: make enrich LIMIT=5
	docker compose run --rm api python -m dealsignal.scripts.enrich websites --limit $(LIMIT)

domain-age:  ## date company domains: make domain-age LIMIT=100
	docker compose run --rm api python -m dealsignal.scripts.enrich domain-age --limit $(LIMIT)

seed:
	docker compose run --rm api python -m dealsignal.scripts.seed --region $(REGION) --industry $(INDUSTRY)

shell:
	docker compose exec api sh

demo:  ## load the committed demo dataset into an empty database
	docker compose exec api python -m dealsignal.scripts.demo_data load

demo-replace:  ## load the demo dataset over whatever is there
	docker compose exec api python -m dealsignal.scripts.demo_data load --replace

demo-export:  ## refresh the committed demo dataset and lead CSVs from this database
	docker compose exec api python -m dealsignal.scripts.demo_data export
