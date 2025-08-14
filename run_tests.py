#!/usr/bin/env python3
"""
Test Runner Script for Slack Standup Bot

This script provides an easy way to run different types of tests:
- Unit tests
- Integration tests
- Aggression tests
- Coverage reports
- Performance tests
"""

import sys
import os
import subprocess
import argparse
from pathlib import Path

def run_command(command, description):
    """Run a command and handle errors."""
    print(f"\n🚀 {description}")
    print(f"Command: {' '.join(command)}")
    print("-" * 50)
    
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        print("✅ Command completed successfully")
        if result.stdout:
            print("Output:")
            print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Command failed with exit code {e.returncode}")
        if e.stdout:
            print("Stdout:")
            print(e.stdout)
        if e.stderr:
            print("Stderr:")
            print(e.stderr)
        return False

def install_test_dependencies():
    """Install test dependencies."""
    print("📦 Installing test dependencies...")
    return run_command([
        sys.executable, "-m", "pip", "install", "-r", "requirements-test.txt"
    ], "Installing test dependencies")

def run_unit_tests():
    """Run unit tests."""
    return run_command([
        sys.executable, "-m", "pytest", "tests/test_bot_core.py", "-v"
    ], "Running unit tests")

def run_integration_tests():
    """Run integration tests."""
    return run_command([
        sys.executable, "-m", "pytest", "tests/test_slack_integration.py", "-v"
    ], "Running integration tests")

def run_aggression_tests():
    """Run aggression tests."""
    return run_command([
        sys.executable, "-m", "pytest", "tests/test_aggression.py", "-v"
    ], "Running aggression tests")

def run_all_tests():
    """Run all tests."""
    return run_command([
        sys.executable, "-m", "pytest", "tests/", "-v"
    ], "Running all tests")

def run_tests_with_coverage():
    """Run tests with coverage report."""
    return run_command([
        sys.executable, "-m", "pytest", "tests/", 
        "--cov=src", "--cov-report=html", "--cov-report=term-missing", "-v"
    ], "Running tests with coverage")

def run_performance_tests():
    """Run performance tests."""
    return run_command([
        sys.executable, "-m", "pytest", "tests/test_aggression.py::test_memory_usage", "-v"
    ], "Running performance tests")

def run_lint_checks():
    """Run code quality checks."""
    print("🔍 Running code quality checks...")
    
    # Run flake8
    flake8_success = run_command([
        sys.executable, "-m", "flake8", "src/", "--max-line-length=100"
    ], "Running flake8 linting")
    
    # Run black check
    black_success = run_command([
        sys.executable, "-m", "black", "--check", "src/"
    ], "Checking code formatting with black")
    
    # Run isort check
    isort_success = run_command([
        sys.executable, "-m", "isort", "--check-only", "src/"
    ], "Checking import sorting with isort")
    
    return flake8_success and black_success and isort_success

def run_security_checks():
    """Run security checks."""
    print("🔒 Running security checks...")
    
    # Run bandit
    bandit_success = run_command([
        sys.executable, "-m", "bandit", "-r", "src/", "-f", "json", "-o", "bandit-report.json"
    ], "Running security scan with bandit")
    
    # Run safety
    safety_success = run_command([
        sys.executable, "-m", "safety", "check", "--json", "--output", "safety-report.json"
    ], "Checking dependencies with safety")
    
    return bandit_success and safety_success

def generate_test_report():
    """Generate comprehensive test report."""
    print("📊 Generating test report...")
    
    # Run tests with coverage and generate HTML report
    success = run_command([
        sys.executable, "-m", "pytest", "tests/",
        "--cov=src",
        "--cov-report=html:htmlcov",
        "--cov-report=json:coverage.json",
        "--junitxml=test-results.xml",
        "--html=test-report.html",
        "--self-contained-html"
    ], "Generating comprehensive test report")
    
    if success:
        print("\n📁 Test reports generated:")
        print("  - HTML coverage: htmlcov/index.html")
        print("  - JSON coverage: coverage.json")
        print("  - JUnit XML: test-results.xml")
        print("  - HTML report: test-report.html")
    
    return success

def main():
    """Main function to parse arguments and run tests."""
    parser = argparse.ArgumentParser(description="Slack Standup Bot Test Runner")
    parser.add_argument(
        "--install-deps", 
        action="store_true", 
        help="Install test dependencies"
    )
    parser.add_argument(
        "--unit", 
        action="store_true", 
        help="Run unit tests only"
    )
    parser.add_argument(
        "--integration", 
        action="store_true", 
        help="Run integration tests only"
    )
    parser.add_argument(
        "--aggression", 
        action="store_true", 
        help="Run aggression tests only"
    )
    parser.add_argument(
        "--coverage", 
        action="store_true", 
        help="Run tests with coverage report"
    )
    parser.add_argument(
        "--performance", 
        action="store_true", 
        help="Run performance tests only"
    )
    parser.add_argument(
        "--lint", 
        action="store_true", 
        help="Run code quality checks"
    )
    parser.add_argument(
        "--security", 
        action="store_true", 
        help="Run security checks"
    )
    parser.add_argument(
        "--report", 
        action="store_true", 
        help="Generate comprehensive test report"
    )
    parser.add_argument(
        "--all", 
        action="store_true", 
        help="Run all tests and checks"
    )
    
    args = parser.parse_args()
    
    # Change to script directory
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    print("🧪 Slack Standup Bot Test Runner")
    print("=" * 50)
    
    if args.install_deps:
        install_test_dependencies()
    
    if args.unit:
        run_unit_tests()
    
    if args.integration:
        run_integration_tests()
    
    if args.aggression:
        run_aggression_tests()
    
    if args.coverage:
        run_tests_with_coverage()
    
    if args.performance:
        run_performance_tests()
    
    if args.lint:
        run_lint_checks()
    
    if args.security:
        run_security_checks()
    
    if args.report:
        generate_test_report()
    
    if args.all:
        print("\n🎯 Running comprehensive test suite...")
        install_test_dependencies()
        run_lint_checks()
        run_security_checks()
        run_all_tests()
        run_tests_with_coverage()
        generate_test_report()
    
    # If no specific tests specified, run all tests
    if not any([args.unit, args.integration, args.aggression, args.coverage, 
                args.performance, args.lint, args.security, args.report, args.all]):
        print("\n🎯 No specific tests specified, running all tests...")
        run_all_tests()
    
    print("\n🏁 Test runner completed!")

if __name__ == "__main__":
    main() 