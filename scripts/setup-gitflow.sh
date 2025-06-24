#!/bin/bash

# Git Flow Setup Script for Slack Standup Bot
# This script sets up the initial Git Flow branching structure

set -e

echo "🚀 Setting up Git Flow for Slack Standup Bot..."

# Check if we're in a git repository
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo "❌ Error: Not in a git repository"
    exit 1
fi

# Check if develop branch already exists
if git show-ref --verify --quiet refs/heads/develop; then
    echo "⚠️  Develop branch already exists"
else
    echo "📝 Creating develop branch..."
    git checkout -b develop
    git push -u origin develop
fi

# Set up branch protection (if using GitHub)
echo "🔒 Setting up branch protection..."
echo "Please configure branch protection rules in GitHub:"
echo "1. Go to Settings > Branches"
echo "2. Add rule for 'main' branch:"
echo "   - Require pull request reviews"
echo "   - Require status checks to pass"
echo "   - Require branches to be up to date"
echo "3. Add rule for 'develop' branch:"
echo "   - Require pull request reviews"
echo "   - Require status checks to pass"

# Create initial tags
echo "🏷️  Creating initial tags..."
git tag -a v1.0.0 -m "Initial release v1.0.0"
git push origin v1.0.0

echo "✅ Git Flow setup complete!"
echo ""
echo "📋 Next steps:"
echo "1. Configure branch protection in GitHub"
echo "2. Set up GitHub Secrets for CI/CD"
echo "3. Create your first feature branch:"
echo "   git checkout develop"
echo "   git checkout -b feature/your-feature-name"
echo ""
echo "📚 For more information, see CONTRIBUTING.md" 