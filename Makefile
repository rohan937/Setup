# QuantFidelity local development helpers
#
# Usage:
#   make sdk-test                  # run all SDK tests
#   make sdk-validate-example      # validate ci_bundle.json locally
#   make sdk-ingest-example-dry-run  # parse and print bundle, no server call
#   make qf-buffer-list            # list locally buffered records

.PHONY: sdk-test sdk-validate-example sdk-ingest-example-dry-run qf-buffer-list

# Run the full SDK test suite
sdk-test:
	cd sdk/python && python3 -m pytest -v

# Validate the CI example bundle without sending to the server
sdk-validate-example:
	cd sdk/python && qf validate --file examples/ci_bundle.json

# Dry-run ingest: parse the CI bundle and print it, no server call
# Requires QUANTFIDELITY_STRATEGY_ID to be set.
sdk-ingest-example-dry-run:
	@if [ -z "$(QUANTFIDELITY_STRATEGY_ID)" ]; then \
		echo "Error: QUANTFIDELITY_STRATEGY_ID is not set."; \
		echo "  Run: QUANTFIDELITY_STRATEGY_ID=<uuid> make sdk-ingest-example-dry-run"; \
		exit 1; \
	fi
	cd sdk/python && qf ingest \
		--strategy-id "$(QUANTFIDELITY_STRATEGY_ID)" \
		--file examples/ci_bundle.json \
		--dry-run

# List locally buffered evidence bundle records
qf-buffer-list:
	qf buffer list
