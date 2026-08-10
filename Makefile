PID_FILE := .streamlit/.dev.pid
LOG_FILE := .streamlit/.dev.log

.PHONY: dev stop

dev:
	@if [ -f "$(PID_FILE)" ] && kill -0 "$$(cat $(PID_FILE))" 2>/dev/null; then \
		echo "Streamlit draait al (pid $$(cat $(PID_FILE)))."; \
	else \
		uv run streamlit run app/main.py > "$(LOG_FILE)" 2>&1 & \
		echo $$! > "$(PID_FILE)"; \
		echo "Streamlit gestart (pid $$(cat $(PID_FILE)))"; \
		for i in 1 2 3 4 5; do \
			grep -qE "(Local URL|Network URL|External URL)" "$(LOG_FILE)" && break; \
			sleep 1; \
		done; \
		if grep -qE "(Local URL|Network URL|External URL)" "$(LOG_FILE)"; then \
			grep -E "(Local URL|Network URL|External URL)" "$(LOG_FILE)"; \
		else \
			echo "Server start niet — zie $(LOG_FILE)."; \
			exit 1; \
		fi \
	fi

stop:
	@if [ -f "$(PID_FILE)" ] && kill -0 "$$(cat $(PID_FILE))" 2>/dev/null; then \
		kill "$$(cat $(PID_FILE))"; \
		rm -f "$(PID_FILE)"; \
		echo "Streamlit gestopt."; \
	else \
		rm -f "$(PID_FILE)"; \
		echo "Geen draaiende Streamlit gevonden."; \
	fi
