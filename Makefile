.PHONY: help install install-dev test lint format clean build deploy

# Default target
help:
	@echo "Available commands:"
	@echo "  install      - Install production dependencies"
	@echo "  install-dev  - Install development dependencies"
	@echo "  test         - Run tests with coverage"
	@echo "  lint         - Run linting checks"
	@echo "  format       - Format code with black and isort"
	@echo "  clean        - Clean build artifacts"
	@echo "  build        - Build package"
	@echo "  deploy       - Deploy to production"
	@echo "  run          - Run the bot locally"
	@echo "  check        - Run all checks (lint, test, format)"

# Install production dependencies
install:
	pip install -r requirements.txt

# Install development dependencies
install-dev:
	pip install -r requirements.txt
	pip install -e .[dev]

# Run tests
test:
	pytest tests/ --cov=src --cov-report=term-missing --cov-report=html

# Run linting
lint:
	flake8 src/ tests/ --count --select=E9,F63,F7,F82 --show-source --statistics
	flake8 src/ tests/ --count --exit-zero --max-complexity=10 --max-line-length=88 --statistics
	black --check src/ tests/
	isort --check-only src/ tests/
	bandit -r src/ -f json -o bandit-report.json || true

# Format code
format:
	black src/ tests/
	isort src/ tests/

# Clean build artifacts
clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf bandit-report.json
	find . -type d -name __pycache__ -delete
	find . -type f -name "*.pyc" -delete

# Build package
build:
	python setup.py sdist bdist_wheel

# Deploy (placeholder - customize for your deployment)
deploy:
	@echo "Deploying to production..."
	# Add your deployment commands here
	# Example: docker build -t slack-standup-bot .
	# Example: docker push your-registry/slack-standup-bot:latest

# Run the bot locally
run:
	python src/slack_healthcheck_bot.py

# Run all checks
check: lint test format

# Setup development environment
setup-dev: install-dev
	@echo "Setting up development environment..."
	@if [ ! -f .env ]; then \
		echo "Creating .env file from template..."; \
		cp env.example .env; \
		echo "Please edit .env with your Slack credentials"; \
	else \
		echo ".env file already exists"; \
	fi

# Create a new feature branch
feature:
	@read -p "Enter feature name: " feature_name; \
	git checkout develop; \
	git pull origin develop; \
	git checkout -b feature/$$feature_name; \
	echo "Created feature branch: feature/$$feature_name"

# Create a new release branch
release:
	@read -p "Enter version (e.g., 1.2.0): " version; \
	git checkout develop; \
	git pull origin develop; \
	git checkout -b release/$$version; \
	echo "Created release branch: release/$$version"

# Create a new hotfix branch
hotfix:
	@read -p "Enter hotfix name: " hotfix_name; \
	git checkout main; \
	git pull origin main; \
	git checkout -b hotfix/$$hotfix_name; \
	echo "Created hotfix branch: hotfix/$$hotfix_name"

# Tag a release
tag-release:
	@read -p "Enter version (e.g., 1.2.0): " version; \
	git tag -a v$$version -m "Release v$$version"; \
	git push origin v$$version; \
	echo "Tagged and pushed release v$$version"

# Security check
security:
	safety check --json --output safety-report.json || true
	@echo "Security check completed. Check safety-report.json for details."

# Update dependencies
update-deps:
	pip install --upgrade pip
	pip install --upgrade -r requirements.txt
	pip install --upgrade -e .[dev]

# Show project status
status:
	@echo "=== Project Status ==="
	@echo "Python version: $(shell python --version)"
	@echo "Installed packages:"
	@pip list --format=freeze | grep -E "(slack|flask|schedule|pytest|black|flake8)" || echo "No relevant packages found"
	@echo ""
	@echo "Git status:"
	@git status --short || echo "Not a git repository"
	@echo ""
	@echo "Environment file:"
	@if [ -f .env ]; then echo "✅ .env file exists"; else echo "❌ .env file missing"; fi 