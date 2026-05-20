.PHONY: dev clean gpt grok espn mohit test scrape scrape-web scrape-test scraper-install scraper-zip

dev:
	venv/bin/uvicorn app.server:app --host 0.0.0.0 --port 8000 --reload

clean:
	@echo "Cleaning up..."
	@find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	@rm -f data/videos/*.mp4
	@echo "Cleanup complete."

# ---- LLM workflow agents (app/visitors/) ---------------------------------
gpt:
	venv/bin/python3 -m app.visitors.chatgpt_visitor

grok:
	venv/bin/python3 -m app.visitors.grok_visitor

# ---- Specialized scrapers (scrapers/) ------------------------------------
# Run the CricHeroes scorecard scraper. Defaults to match 24495442.
# Usage: make mohit [MATCH=24495442]
mohit:
	venv/bin/python3 -m scrapers.cricheroes $(if $(MATCH),$(MATCH),24495442)

# Run the ESPN Cricinfo squad scraper
espn:
	venv/bin/python3 -m scrapers.espn

# Install every dependency used anywhere under scrapers/ + browser binary.
scraper-install:
	venv/bin/pip install -r scrapers/requirements.txt
	venv/bin/playwright install chromium

# Bundle the entire scraping component (cricheroes + espn + hub) for sharing.
scraper-zip:
	@echo "Packaging all scraper technology..."
	@zip -r scrapers.zip scrapers/ -x "*/__pycache__*" "*.pyc" "*.pyo"
	@echo "Done! Created scrapers.zip containing CricHeroes, ESPN, and the Scraper Hub."

# ---- Scraper Hub (progressive L1/L2/L3 + web UI) -------------------------
# CLI:   make scrape URL="https://example.com"
# Extra flags via ARGS, e.g. ARGS="--max-level 1 --timeout 30 --include-raw"
scrape:
	@if [ -z "$(URL)" ]; then \
		echo 'usage: make scrape URL="<url>" [ARGS="--max-level 1 --timeout 30"]'; \
		exit 2; \
	fi
	venv/bin/python3 -m scrapers.hub "$(URL)" $(ARGS)

# Launch the web UI at http://127.0.0.1:8765/
# Override host/port with HOST/PORT, e.g. make scrape-web PORT=9000
scrape-web:
	venv/bin/python3 -m scrapers.hub.web \
		$(if $(HOST),--host $(HOST)) \
		$(if $(PORT),--port $(PORT))

# Unit tests for the hub (pure logic, no network)
scrape-test:
	venv/bin/pytest scrapers/hub/tests/ -q

# ---- Project-wide tests --------------------------------------------------
test:
	venv/bin/pytest tests/
