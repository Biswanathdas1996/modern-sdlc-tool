"""Test script to demonstrate verbose agent execution."""
import asyncio
import sys
import logging

# Setup logging FIRST before any imports
from core.logging import setup_logging

# Set to DEBUG level for maximum verbosity
logger = setup_logging(level=logging.DEBUG)

print("\n" + "="*80)
print("JIRA AGENT VERBOSE TEST")
print("="*80 + "\n")

from agents.jira_agent import jira_agent

async def test_agent():
    """Test the agent with verbose output."""
    
    test_query = "login authentication user stories"
    
    print(f"Testing JIRA Agent with query: '{test_query}'")
    print(f"Watch for detailed logs below...")
    print("\n" + "-"*80 + "\n")
    
    result = await jira_agent.find_related_tickets(test_query)
    
    print("\n" + "-"*80)
    print("RESULT:")
    print("-"*80)
    print(f"Success: {result.get('success')}")
    print(f"Response: {result.get('response')}")
    print(f"Tickets found: {len(result.get('tickets', []))}")
    print("\n" + "="*80 + "\n")

if __name__ == "__main__":
    asyncio.run(test_agent())
