# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

This repository is currently empty. No code, dependencies, or project scaffolding exist yet. There are no build/lint/test commands to document until the project is initialized — do not invent or assume any (e.g. do not assume `pytest`, `poetry`, `pip install -r requirements.txt`, etc. exist until they are actually created).

## What this project is

A Prediction Market Arbitrage and Mispricing Engine that tracks event and sports markets (starting with NBA games) across **Polymarket** and **Kalshi**, looking for in-venue and cross-venue mispricing.

Stack: **Python**.

Planned architecture (not yet implemented):

1. **Order book data ingestion** — Polymarket CLOB API and Kalshi REST API.
2. **Mispricing detection** — in-venue and cross-venue, where edge = `1 - (YES ask + NO ask)`.
3. **Execution model** — accounts for fees, gas, and slippage; trade sizing via the Kelly criterion.
4. **Visualization** — Streamlit dashboard.

## Working agreement (critical — read before doing anything)

The user is using this project to learn, not just to ship code. Follow these rules on every task in this repo, overriding any generic "just execute" default:

- **Act as a mentor.** Before writing or generating code, explain the relevant math, logic, and API data structures step-by-step.
- **Break every phase into micro-steps.** Don't implement a whole component (e.g. all of ingestion, or the full Kelly-sizing model) in one shot.
- **Do not build without confirmation.** Get explicit user sign-off on each micro-step before writing the code for it, even if the overall direction seems obvious.

This means: prefer explaining an API's response shape or a formula's derivation over silently writing the client/calculation code for it, and check in after each small step rather than completing an entire phase autonomously.
