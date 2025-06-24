# Contributing to Slack Standup Bot

Thank you for your interest in contributing to the Slack Standup Bot! This document outlines our development workflow and contribution guidelines.

## Git Flow Branching Model

We follow a lightweight Git Flow-inspired model, adapted for simplicity and CI/CD. This includes three main types of branches:

### Branch Types and Naming

| Branch Name | Use Case | Base Branch | Merge Into |
|-------------|----------|-------------|------------|
| `main` | Production code only (stable, deployed) | — | — |
| `develop` | Active development branch | `main` | `main` (via releases) |
| `feature/xyz` | New features or enhancements | `develop` | `develop` |
| `release/x.y.z` | Final polish before a release | `develop` | `main`, `develop` |
| `hotfix/urgent-fix` | Emergency production fixes | `main` | `main`, `develop` |

## Development Workflow

### A. Creating a Feature Branch

```bash
git checkout develop
git pull origin develop
git checkout -b feature/short-description
```

**Guidelines:**
- Keep changes small and focused
- Push regularly
- Open a PR into `develop` when complete

### B. Preparing a Release

```bash
git checkout develop
git checkout -b release/1.3.0
```

**Guidelines:**
- Final bug fixes, documentation, version bumping
- Open a PR into both `main` and `develop`

### C. Hotfixing a Production Bug

```bash
git checkout main
git checkout -b hotfix/fix-crash-issue
```

**Guidelines:**
- Commit fix
- Merge into both `main` and `develop` via PRs

### D. Merging

All changes must be merged via Pull Requests. Each PR must:

- ✅ Pass all CI tests (unit tests, linting, builds)
- ✅ Be reviewed by at least one other developer
- ✅ Use a descriptive title and link to a relevant issue/task

## Setup Instructions

### Prerequisites

- Python 3.8 or higher
- Git
- Slack Bot Token and Channel ID

### Local Development Setup

1. **Clone the repository:**
   ```bash
   git clone <repo-url>
   cd slack-standup-bot
   ```

2. **Set up environment:**
   ```bash
   cp env.example .env
   # Edit .env with your Slack credentials
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   pip install -e .[dev]  # Install development dependencies
   ```

4. **Run tests:**
   ```bash
   python -m pytest tests/
   ```

5. **Run linting:**
   ```bash
   flake8 src/ tests/
   black --check src/ tests/
   isort --check-only src/ tests/
   ```

## Code Quality Standards

### Python Code Style

We use the following tools to maintain code quality:

- **Black**: Code formatting
- **isort**: Import sorting
- **flake8**: Linting
- **bandit**: Security checks
- **pytest**: Testing

### Pre-commit Hooks

Before committing, ensure your code passes:

```bash
# Format code
black src/ tests/

# Sort imports
isort src/ tests/

# Run tests
pytest tests/

# Run linting
flake8 src/ tests/
```

### Testing

- Write tests for all new features
- Maintain test coverage above 80%
- Use descriptive test names
- Test both success and failure cases

## Pull Request Process

1. **Create a feature branch** from `develop`
2. **Make your changes** following the coding standards
3. **Write/update tests** for your changes
4. **Update documentation** if needed
5. **Run the test suite** locally
6. **Push your branch** and create a PR
7. **Request review** from at least one team member
8. **Address feedback** and make necessary changes
9. **Merge** once approved and CI passes

## Commit Message Guidelines

Use conventional commit format:

```
type(scope): description

[optional body]

[optional footer]
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

**Examples:**
```
feat(bot): add escalation workflow for blockers
fix(config): resolve environment variable parsing issue
docs(readme): update setup instructions
test(parsing): add test cases for malformed responses
```

## Release Process

1. **Create release branch:**
   ```bash
   git checkout develop
   git checkout -b release/1.2.0
   ```

2. **Update version:**
   - Update version in `setup.py`
   - Update version in `src/__init__.py`
   - Update CHANGELOG.md

3. **Final testing:**
   - Run full test suite
   - Test in staging environment
   - Update documentation

4. **Merge to main:**
   - Create PR to `main`
   - Create PR to `develop`
   - Merge both after review

5. **Tag release:**
   ```bash
   git tag -a v1.2.0 -m "Release v1.2.0"
   git push origin v1.2.0
   ```

## Cleanup

After merging any branch (feature, release, or hotfix), delete the branch:

```bash
git branch -d feature/short-description
git push origin --delete feature/short-description
```

## Best Practices

- ✅ Use descriptive branch names: `feature/login-form`, `hotfix/payment-timeout`
- ✅ Keep branches short-lived (ideally < 5 days)
- ✅ Merge changes frequently to avoid conflicts
- ✅ Never commit directly to `main` or `develop`
- ✅ Run tests locally before pushing
- ✅ Write clear commit messages
- ✅ Update documentation for new features

## Getting Help

If you have questions or need help:

1. Check the [README.md](README.md) for setup instructions
2. Review existing issues and PRs
3. Create a new issue for bugs or feature requests
4. Ask questions in the project discussions

## Code of Conduct

Please be respectful and inclusive in all interactions. We welcome contributions from people of all backgrounds and experience levels.

---

Thank you for contributing to the Slack Standup Bot! 🚀 