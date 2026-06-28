# Agents

This directory contains the agent implementations for the Radical Red battle benchmark. Here's a short overview of each one:

## SimpleAgent

`SimpleAgent` treats every "step" as a separate LLM call, and progressively builds context as the battle and battle attempts progress. Context includes:

- the user's team (Pokemon, stats, abilities, move info, etc.)
- known information about Giovanni's team
- move/attempt history

from this, the agent must decide at each step whether to fight or switch Pokemon. At the start of each attempt, it also has a choice in choosing the lead Pokemon.