install:
	@if command -v pipx >/dev/null 2>&1; then \
		pipx install --force . ; \
	else \
		pip install . ; \
	fi

install-dev:
	@if command -v pipx >/dev/null 2>&1; then \
		pipx install --force -e . ; \
	else \
		pip install -e . ; \
	fi

update-config:
	cp .sophy/config.json ~/.sophy/config.json
