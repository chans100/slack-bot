# This file marks the src directory as a Python package.

"""
Slack Standup Bot Package

A comprehensive Slack bot for daily standup management with escalation workflows.
"""

__version__ = "1.0.0"
__author__ = "Your Name"
__email__ = "your.email@example.com"

from .bot import DailyStandupBot
from .config import BotConfig

__all__ = ["DailyStandupBot", "BotConfig"] 